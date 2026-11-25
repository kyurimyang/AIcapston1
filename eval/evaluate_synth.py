"""합성 검증셋(data/synth_val)으로 현재 인식 방식을 평가해 기준선을 기록한다. data/test는 읽지 않는다.

실행 (레포 루트에서): python eval/make_synth_val.py && python eval/evaluate_synth.py
결과: eval/results_synth_val.md

- 방식: 앱과 같다. 현재 STAGE(기본 ②)의 인덱스·체크포인트, 다중 크롭(CROP_SCALES) + 유물 점수 max,
  임계값은 recognize._stage()가 읽는 파일(②: thresholds_stage2_crop.json). 재학습·재튜닝 없음.
- 누수 방지 (leave-one-out): 양성 질의는 gallery 사진을 합성한 것이므로, 검색할 때
  ① 그 질의의 원본 gallery 이미지와 ② 그 이미지와 같은 사진의 중복본(pHash 거리 <= DUP_MAX_DIST)을
  검색 대상에서 뺀다 (rank_leave_one_out). 음성 질의는 gallery에서 온 게 아니라 빼지 않는다.
- LOO 뒤에 그 유물의 gallery 사진이 하나도 안 남는 질의(사진 1장뿐이거나 전부 중복본인 유물)는
  정답이 검색 대상에 없으므로 '답할 수 있는 양성'에서 빼고, "등록 안 된 유물" 줄에 따로 보고한다.
"""
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import recognize  # noqa: E402
from app.recognize import CROP_SCALES, DB_PATH, ROOT, center_crop, embed, judge, load_image, rank_embeddings  # noqa: E402

DATA = ROOT / "data"
SYNTH = DATA / "synth_val"
SYNTH_CUT = DATA / "synth_val_cut"
OUT = ROOT / "eval" / "results_synth_val.md"
HASH_N = 16  # 16x16 = 256비트 pHash
# gallery 안의 pHash 거리 분포로 정했다 (test는 보지 않음): 완전 중복 0~2, 연속 촬영 거의-같은 컷 36·48,
# 서로 다른 유물끼리는 최소 60. 그 사이인 50을 경계로 둔다.
DUP_MAX_DIST = 50
BINS = ["20-30%", "30-40%", "40-50%"]
AB = {"A01": "B01", "B01": "A01"}


# --- 중복 판정 · leave-one-out ------------------------------------------------

def phash(img: np.ndarray, n: int = HASH_N) -> np.ndarray:
    """RGB 배열 -> n*n 비트 perceptual hash (DCT 저주파가 중앙값보다 큰가)."""
    g = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    d = cv2.dct(cv2.resize(g, (4 * n, 4 * n), interpolation=cv2.INTER_AREA))[:n, :n]
    return (d > np.median(d)).ravel()


def find_duplicates(paths: list[str], hashes: np.ndarray, max_dist: int = DUP_MAX_DIST) -> dict[str, set[str]]:
    """경로 -> 자기 자신을 뺀 중복본(pHash 거리 <= max_dist) 경로 집합."""
    H = np.asarray(hashes, bool)
    D = (H[:, None, :] != H[None, :, :]).sum(-1)
    return {p: {paths[j] for j in np.flatnonzero(D[i] <= max_dist) if j != i} for i, p in enumerate(paths)}


def loo_keep_mask(gallery_paths: list[str], source_path: str | None, dups: dict[str, set[str]]) -> np.ndarray:
    """검색 대상으로 남길 gallery 행 (True). source_path가 없으면(음성) 전부 남긴다."""
    keep = np.ones(len(gallery_paths), bool)
    if not source_path:
        return keep
    if source_path not in dups:
        raise KeyError(f"원본 gallery 경로가 gallery 목록에 없어요: {source_path}")
    drop = {source_path} | dups[source_path]
    for i, p in enumerate(gallery_paths):
        if p in drop:
            keep[i] = False
    return keep


def rank_leave_one_out(V: np.ndarray, G: np.ndarray, ids, gallery_paths: list[str],
                       source_path: str | None, dups: dict[str, set[str]], agg: str = "max"):
    """질의 크롭 임베딩 V로 검색하되, 원본 gallery 사진과 그 중복본은 검색 대상에서 뺀다."""
    keep = loo_keep_mask(gallery_paths, source_path, dups)
    return rank_embeddings(V, G[keep], np.asarray(ids)[keep], agg)


# --- 평가 ---------------------------------------------------------------------

def load_gallery(index, ids):
    """인덱스 행 순서와 같은 gallery 경로 (build_index.py와 같은 쿼리). 순서가 맞는지 임베딩으로 확인한다."""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='gallery' "
                           "ORDER BY artifact_id, path").fetchall()
    if [a for a, _ in rows] != list(ids):
        raise RuntimeError("DB의 gallery 목록과 인덱스 ids 순서가 달라요 (build_index.py를 다시 돌렸나요?)")
    paths = [p for _, p in rows]
    G = index.reconstruct_n(0, index.ntotal)
    probe = [0, len(paths) // 2, len(paths) - 1]
    e = embed([load_image(DATA / paths[i]) for i in probe], ckpt=recognize._ckpt())
    if not np.all((e * G[probe]).sum(1) > 0.999):
        raise RuntimeError("gallery 경로와 인덱스 벡터가 맞지 않아요")
    return paths, G


def load_synth(d: Path = SYNTH):
    """합성셋 폴더 d의 synth_val.csv 행과 질의 크롭 임베딩 (N, 크롭 수, D)."""
    with open(d / "synth_val.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ims = [load_image(d / r["path"]) for r in rows]
    V = embed([center_crop(im, s) for im in ims for s in CROP_SCALES], ckpt=recognize._ckpt())
    return rows, V.reshape(len(rows), len(CROP_SCALES), -1)


def gallery_dups(paths):
    hashes = np.array([phash(np.asarray(load_image(DATA / p))) for p in paths])
    return find_duplicates(paths, hashes)


def score_synth(rows, V, G, ids, paths, dups, agg, T, M):
    """질의마다 LOO 검색 + 판정을 해 지표를 모은다.

    반환 dict: pos(구간 -> 지표), orphan, neg(종류 -> 지표), per_art(유물 -> [정답, 수]),
    vb(크기 구간 -> [val 음성 오인식, 수]), orphan_arts
    """
    pos = defaultdict(lambda: defaultdict(int))   # 구간 -> 지표
    orphan = defaultdict(int)
    neg = {k: defaultdict(int) for k in ("neg_bg", "neg_val")}
    per_art = defaultdict(lambda: [0, 0])
    vb = defaultdict(lambda: [0, 0])  # 크기 구간 -> [val 음성 오인식, 장수]
    orphan_arts = set()
    for r, v in zip(rows, V):
        src = r["source_gallery_path"] or None
        ranked = rank_leave_one_out(v, G, ids, paths, src, dups, agg)
        st = judge(ranked, T, M)
        top = ranked[0][0]
        if r["kind"] == "pos":
            a = r["artifact_id"]
            keep = loo_keep_mask(paths, src, dups)
            if not (keep & (ids == a)).any():  # 정답이 검색 대상에 없음
                orphan_arts.add(a)
                orphan["n"] += 1
                orphan[st] += 1
                continue
            right = top == a
            for key in ("전체", r["size_bin"]) + (("A·B",) if a in AB else ()):
                d = pos[key]
                d["n"] += 1
                d["top1"] += right
                d["top3"] += a in [x for x, _ in ranked[:3]]
                d[st] += 1
                d["ok_right"] += st == "ok" and right
                d["confident_wrong"] += st == "ok" and not right
                d["right_reject"] += right and st == "reject"
                if a in AB:
                    d["ab_confuse"] += top == AB[a]
                    d["ab_confuse_ok"] += top == AB[a] and st == "ok"
            per_art[a][0] += right
            per_art[a][1] += 1
        else:
            d = neg[r["kind"]]
            d["n"] += 1
            d[st] += 1
            if r["kind"] == "neg_val":  # 붙인 val 유물 크기별 오인식
                vb[r["size_bin"]][0] += st != "reject"
                vb[r["size_bin"]][1] += 1
    return dict(pos=pos, orphan=orphan, neg=neg, per_art=per_art, vb=vb, orphan_arts=orphan_arts)


def pct(x, n):
    return f"{x / n:.1%}" if n else "-"


def tables(res) -> str:
    """score_synth 결과 -> 1~4절 마크다운."""
    pos, orphan, neg, per_art, vb, orphan_arts = (res[k] for k in ("pos", "orphan", "neg", "per_art", "vb", "orphan_arts"))
    head = ("| 구간 | 질의 | Top-1 | Top-3 | ok | ok 중 정답 | 확신 오답 | uncertain | reject | 정답인데 reject |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n")
    lines = []
    for key in ["전체"] + BINS + ["A·B"]:
        d = pos[key]
        n = d["n"]
        lines.append(f"| {key} | {n} | **{pct(d['top1'], n)}** | {pct(d['top3'], n)} | {d['ok']} ({pct(d['ok'], n)}) | "
                     f"{d['ok_right']} | {d['confident_wrong']} ({pct(d['confident_wrong'], n)}) | {d['uncertain']} | "
                     f"{d['reject']} | {d['right_reject']} ({pct(d['right_reject'], n)}) |")
    t_pos = head + "\n".join(lines)
    ab = pos["A·B"]
    t_ab = ("| A·B 질의 | 1위가 상대(A↔B) | 그중 ok(확신 혼동) |\n|---|---|---|\n"
            f"| {ab['n']} | {ab['ab_confuse']} ({pct(ab['ab_confuse'], ab['n'])}) | {ab['ab_confuse_ok']} |")
    t_neg = "| 음성 종류 | 장수 | ok | uncertain | reject | 오인식률 (reject 아님) |\n|---|---|---|---|---|---|\n"
    for k, lab in (("neg_bg", "배경만"), ("neg_val", "gallery에 없는 K-Art val 유물")):
        d = neg[k]
        t_neg += f"| {lab} | {d['n']} | {d['ok']} | {d['uncertain']} | {d['reject']} | **{pct(d['n'] - d['reject'], d['n'])}** |\n"
    d = orphan
    t_neg += (f"| LOO 뒤 gallery에서 사라진 유물 ({', '.join(sorted(orphan_arts))}) | {d['n']} | {d['ok']} | "
              f"{d['uncertain']} | {d['reject']} | {pct(d['n'] - d['reject'], d['n'])} |")
    t_vb = "| 크기 구간 | " + " | ".join(BINS) + " |\n|---|" + "---|" * len(BINS) + "\n" \
           "| val 유물 음성 오인식률 | " + " | ".join(f"{pct(*vb[b])} ({vb[b][1]})" for b in BINS) + " |"
    t_art = "| 유물 | " + " | ".join(sorted(per_art)) + " |\n|---|" + "---|" * len(per_art) + "\n| Top-1 | " + \
            " | ".join(f"{per_art[a][0]}/{per_art[a][1]}" for a in sorted(per_art)) + " |"
    return f"""### 1. 양성 (답할 수 있는 질의) — 크기 구간별
{t_pos}

- ok 중 정답 = 상태 ok이면서 1위가 정답. 확신 오답 = ok인데 1위가 다른 유물. 정답인데 reject = 1위는 맞았지만 T 미만.

### 2. A↔B 혼동
{t_ab}

### 3. 음성 (유물 없음) — 오인식률
{t_neg}

{t_vb}

### 4. 유물별 Top-1 (양성, 답할 수 있는 질의)
{t_art}
"""


def available_sets() -> list[tuple[str, Path]]:
    """평가할 합성셋. synth_val은 필수, synth_val_cut(--cutout)은 있으면 같이."""
    sets = [("synth_val", SYNTH)]
    if (SYNTH_CUT / "synth_val.csv").exists():
        sets.append(("synth_val_cut", SYNTH_CUT))
    return sets


def main() -> None:
    index, ids, T, M = recognize._stage()
    ids = np.asarray(ids)
    paths, G = load_gallery(index, ids)
    dups = gallery_dups(paths)
    n_dup = sum(bool(v) for v in dups.values())
    sections, counts = [], ""
    for name, d in available_sets():
        rows, V = load_synth(d)
        res = score_synth(rows, V, G, ids, paths, dups, recognize.AGG, T, M)
        desc = ("gallery 사진 전체(스튜디오 배경 사각형 포함)를 붙임" if name == "synth_val"
                else "GrabCut으로 스튜디오 배경을 지우고 불상만 붙임 (`make_synth_val.py --cutout`)")
        sections.append(f"## {name} — {desc}\n\n" + tables(res))
        if not counts:
            neg = res["neg"]
            counts = (f"양성 {sum(r['kind'] == 'pos' for r in rows)}장 (gallery 22점 x 20장, 유물의 gallery 사진을 돌아가며 원본으로 씀)"
                      f" / 음성: 배경만 {neg['neg_bg']['n']}장 + gallery에 없는 K-Art val 유물 {neg['neg_val']['n']}장")
    body = "\n".join(sections)
    md = f"""# 합성 검증셋 기준선 (불상이 작고 배경이 큰 사진, test 미사용)

목적: test를 보지 않고 "현장처럼 불상이 작고 배경이 큰 사진"에서 인식 방법을 비교할 기준선.
**data/test·data/none_val은 읽지 않았다.** 재학습·임계값 재튜닝 없음.
실행: `python eval/make_synth_val.py && python eval/make_synth_val.py --cutout && python eval/evaluate_synth.py`

## 설정
- 방식(현재 앱과 같음): STAGE={recognize.STAGE} 인덱스·체크포인트, 다중 크롭 {CROP_SCALES} + 유물 점수 `{recognize.AGG}`, T={T} · M={M}
- 질의: {counts}. 두 버전은 시드·크기·위치·배경·변형 파라미터가 같고, 붙이는 물체만 다르다.
- 합성 규칙은 `eval/make_synth_val.py` 맨 위 주석. 붙인 물체 크기 s = 캔버스 대비 20~50% (긴 쪽 기준), 긴 변 768px, 시드 0.
  synth_val은 사진 전체가 s, synth_val_cut은 오려 낸 불상의 경계 상자가 s다.
- **누수 방지 (leave-one-out)**: 양성 질의를 검색할 때 원본 gallery 사진과 그 중복본(256비트 pHash 거리 ≤ {DUP_MAX_DIST})을 검색 대상에서 뺐다. 중복본이 하나 이상 있는 gallery 사진은 {n_dup}장.
  경계 {DUP_MAX_DIST}는 gallery 안의 거리 분포로 정했다: 완전 중복 0~2, 연속 촬영의 거의 같은 컷 36·48, 서로 다른 유물끼리 최소 60.
- LOO 뒤 정답 유물의 gallery 사진이 하나도 안 남는 질의(사진 1장뿐이거나 전부 중복본인 유물)는 정답이 검색 대상에 없으므로 양성 표에서 빼고, 음성 표의 마지막 줄("사라진 유물")에 따로 적었다. 올바른 동작은 reject다.

{body}
## 해석 시 주의
- **현장과 차이가 있을 수 있다.** 이 검증셋이 사유의 방 사진과 얼마나 비슷한지는 test로 확인하지 않았다(확인하면 test를 방법 선택에 쓰는 셈이 된다). 알려진 차이:
  - synth_val은 gallery 사진 전체(스튜디오 배경 사각형 포함)를 붙였다. synth_val_cut은 GrabCut으로 오렸지만 자동 분할이라 경계에 배경이 남거나 불상 일부가 잘릴 수 있다 (분할 실패 시 사진 전체를 붙이고 csv `cutout=fail`로 표시). 시드 0에서 gallery(양성)는 전부 성공, val 음성은 140장 중 27장이 실패해 사각형째 붙었다. 이 비대칭 때문에 synth_val_cut의 val 음성 수치는 순수한 '오려 낸 불상' 조건이 아니다.
  - 배경은 절차 생성(단색·그라데이션·노이즈)이라 실제 전시실의 벽·조명·받침대·진열장 반사·다른 관람객이 없다. A·B 공통 배경 같은 '헷갈리게 하는 공통 요소'도 없다.
  - 실제 촬영의 시점 변화(측면·뒤·상하 각도)는 gallery에 있는 시점만큼만 있다. 원근 변형은 약하게(꼭짓점 0~6%)만 줬다.
  - 같은 gallery 사진에서 여러 질의가 나오므로 질의끼리 독립이 아니다. 실제 표본 크기는 질의 수보다 작다.
- **음성 val 유물은 T를 정할 때 쓴 데이터다** (pick_thresholds.py가 val을 음성으로 씀). 합성으로 모양은 달라졌지만 같은 유물이라 오인식률이 낙관적일 수 있다.
- 중복 판정은 pHash만 쓴다. 각도만 조금 다른 연속 촬영 컷(예: B01 83-1과 83-5, 거리 78)은 중복으로 잡히지 않아 검색 대상에 남는다. 그만큼 양성 점수가 조금 높게 나올 수 있다.
- 이 표는 방법끼리 비교하는 기준선이다. 다른 방법을 시험할 때는 같은 합성셋(같은 시드)과 같은 지표로 비교하고, 방법을 고른 뒤에만 test로 결과를 보고한다.
"""
    OUT.write_text(md.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8", newline="")
    print(md)


if __name__ == "__main__":
    main()
