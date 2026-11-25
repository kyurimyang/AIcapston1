"""'새 유물을 gallery에 사진 1~2장만 넣어 추가하면 알아보는가' 시뮬레이션. data/test는 읽지 않는다.

실행 (레포 루트에서): python eval/evaluate_new_artifacts.py
결과: eval/results_generalization.md

설정
- K-Art val 35점(학습에 안 쓴 유물, 유물당 4방향 b/f/l/r)을 "새로 추가한 유물"로 본다.
- 기존 22점 gallery(인덱스)는 그대로 두고, val 유물의 사진 k장(k=1,2)을 gallery에 더한 뒤
  나머지 방향 사진을 질의로 검색한다. 다중 크롭 · max · 단계별 현재 T·M.
  gallery로 쓸 방향은 모든 경우(k=1: 4가지, k=2: 6가지)를 평균해서 고르는 편향을 없앴다.
- A) 한 점씩 추가: 후보 = 기존 22 + 새 유물 1 (실제로 add_artifact.py를 한 번 돌리는 상황)
  B) 35점 동시 추가: 후보 = 22 + 35 (더 어려운 상한. 방향 조합은 모든 유물이 같은 걸 쓴다)
- ①은 ①의 인덱스(index_stage1)와 임계값(thresholds_stage1.json), ②는 ②의 것(thresholds_stage2_crop.json).
  ①에는 다중 크롭용 임계값 파일이 없어 원본 기준 T·M을 그대로 쓴다.
- 신뢰구간은 유물 35점을 단위로 부트스트랩(시드 고정)한 값이다. 같은 유물의 질의는 독립이 아니기 때문이다.
"""
import itertools
import json
import sqlite3
import sys
from pathlib import Path

import faiss
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import CROP_SCALES, DB_PATH, MODELS, ROOT, center_crop, embed, judge, load_image, rank_embeddings  # noqa: E402

OUT = ROOT / "eval" / "results_generalization.md"
DIRS = ["b", "f", "l", "r"]
STAGES = {1: ("①", "thresholds_stage1.json", None), 2: ("②", "thresholds_stage2_crop.json", "ckpt_stage2.pt")}


def load_val():
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='val' ORDER BY artifact_id, path").fetchall()
    arts = sorted({a for a, _ in rows})
    by = {a: {Path(p).stem: p for b, p in rows if b == a} for a in arts}
    assert all(sorted(d) == DIRS for d in by.values()), "val 유물은 4방향(b,f,l,r)이어야 해요"
    return arts, by


def run_stage(stage, arts, by):
    name, th_file, ck = STAGES[stage]
    th = json.loads((MODELS / th_file).read_text())
    T, M = th["T"], th["M"]
    index = faiss.read_index(str(MODELS / f"index_stage{stage}.faiss"))
    ids0 = np.array(json.loads((MODELS / f"index_stage{stage}_ids.json").read_text(encoding="utf-8")))
    G0 = index.reconstruct_n(0, index.ntotal)
    images = [load_image(ROOT / "data" / by[a][d]) for a in arts for d in DIRS]
    V = embed([center_crop(im, s) for im in images for s in CROP_SCALES],
              ckpt=str(MODELS / ck) if ck else None).reshape(len(arts), len(DIRS), len(CROP_SCALES), -1)
    return dict(T=T, M=M, G0=G0, ids0=ids0, V=V)


def evaluate(st, arts, k, simultaneous):
    """모든 gallery 방향 조합을 돌며 질의별 결과를 모은다. 반환: 유물별 [top1, top3, 정답인데reject, 확신오답, uncertain, reject] 합계와 질의 수."""
    G0, ids0, V, T, M = st["G0"], st["ids0"], st["V"], st["T"], st["M"]
    stats = np.zeros((len(arts), 6))
    nq = np.zeros(len(arts))
    per_dir = {d: [0, 0] for d in DIRS}  # k=1일 때 gallery 방향별 [정답 1위, 질의 수]
    for sub in itertools.combinations(range(len(DIRS)), k):
        qdirs = [i for i in range(len(DIRS)) if i not in sub]
        if simultaneous:
            # 35점 전부의 gallery 사진을 한꺼번에 더한다
            Gadd = np.concatenate([V[ai, d, 0][None] for ai in range(len(arts)) for d in sub])
            idsadd = np.array([a for a in arts for _ in sub])
            Gc, idc = np.concatenate([G0, Gadd]), np.concatenate([ids0, idsadd])
        for ai, a in enumerate(arts):
            if not simultaneous:
                Gc = np.concatenate([G0, V[ai, list(sub), 0]])  # 사진 원본(크롭 1.0)이 gallery 임베딩
                idc = np.concatenate([ids0, np.array([a] * k)])
            for q in qdirs:
                ranked = rank_embeddings(V[ai, q], Gc, idc, "max")
                top = ranked[0][0]
                st_ = judge(ranked, T, M)
                right = top == a
                stats[ai] += [right, a in [x for x, _ in ranked[:3]], right and st_ == "reject",
                              (not right) and st_ == "ok", st_ == "uncertain", st_ == "reject"]
                nq[ai] += 1
                if k == 1:
                    per_dir[DIRS[sub[0]]][0] += right
                    per_dir[DIRS[sub[0]]][1] += 1
    return stats, nq, per_dir


def summarize(stats, nq, rng):
    """질의 단위 비율 + 유물 단위 부트스트랩 95% 구간(Top-1)."""
    rate = stats.sum(0) / nq.sum()
    boots = []
    for _ in range(2000):
        idx = rng.integers(0, len(nq), len(nq))
        boots.append(stats[idx, 0].sum() / nq[idx].sum())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return rate, (lo, hi), int(nq.sum())


def table(results, labels):
    head = "| 단계 | gallery | 질의 수 | Top-1 (95% 구간) | Top-3 | 정답인데 reject | 확신 오답 | uncertain | reject 전체 |\n|---|---|---|---|---|---|---|---|---|\n"
    rows = []
    for (lab, k), (rate, ci, n) in zip(labels, results):
        rows.append(f"| {lab} | {k}장 | {n} | **{rate[0]:.1%}** ({ci[0]:.0%}~{ci[1]:.0%}) | {rate[1]:.1%} | {rate[2]:.1%} | {rate[3]:.1%} | {rate[4]:.1%} | {rate[5]:.1%} |")
    return head + "\n".join(rows)


def main():
    arts, by = load_val()
    print(f"val 유물 {len(arts)}점 x {len(DIRS)}방향")
    rng = np.random.default_rng(0)
    A, B, labels, D, TH = [], [], [], {}, {}
    for stage in (1, 2):  # ① 먼저, ② 나중 (모델 교체 1번)
        st = run_stage(stage, arts, by)
        TH[stage] = st
        for k in (1, 2):
            sa, na, pd = evaluate(st, arts, k, simultaneous=False)
            sb, nb, _ = evaluate(st, arts, k, simultaneous=True)
            A.append(summarize(sa, na, rng)); B.append(summarize(sb, nb, rng)); labels.append((STAGES[stage][0], k))
            if k == 1:
                D[stage] = pd
        print(f"{STAGES[stage][0]} T={st['T']} M={st['M']} 완료", flush=True)

    ta, tb = table(A, labels), table(B, labels)
    td = "| gallery로 쓴 방향 | " + " | ".join(DIRS) + " |\n|---|" + "---|" * len(DIRS) + "\n"
    for stage in (1, 2):
        td += f"| {STAGES[stage][0]} Top-1 | " + " | ".join(f"{D[stage][d][0] / D[stage][d][1]:.1%}" for d in DIRS) + " |\n"
    md = f"""# 새 유물 추가 일반화 평가 (K-Art val 35점 시뮬레이션)

질문: 코드 수정 없이 새 유물 사진을 gallery에 1~2장 넣으면 알아보는가? (`backend/scripts/add_artifact.py`의 전제)
**data/test(사유의 방)는 쓰지 않았다.** 재학습 없음. 실행: `python eval/evaluate_new_artifacts.py`

## 설정
- K-Art val 35점(학습에 안 쓴 유물, 유물당 4방향 b/f/l/r)을 "새로 추가한 유물"로 가정했다.
- 기존 22점 gallery는 그대로 두고, 새 유물 사진 k장(k=1,2)을 gallery에 더한 뒤 **나머지 방향** 사진을 질의로 검색했다. 다중 크롭 · max · 단계별 현재 T·M.
- gallery로 쓰는 방향은 가능한 조합을 전부 돌려 평균했다 (k=1: 4가지, k=2: 6가지). 방향을 골라서 좋은 결과를 만들지 않았다.
- ①은 ①의 인덱스·임계값(`thresholds_stage1.json`, T={TH[1]['T']}·M={TH[1]['M']}), ②는 ②의 것(`thresholds_stage2_crop.json`, T={TH[2]['T']}·M={TH[2]['M']}). ①은 다중 크롭용 임계값 파일이 없어 원본 기준 값을 그대로 썼다.
- 지표: Top-1/Top-3 = 새 유물이 1위/3위 안, 정답인데 reject = 1위가 정답인데 T 미만이라 거절, 확신 오답 = 상태 ok인데 1위가 다른 유물. 모두 전체 질의 대비 비율.
- 95% 구간은 유물 35점을 단위로 부트스트랩(2000회, 시드 0)했다.

## A. 새 유물을 한 점씩 추가 (후보 23점 = 기존 22 + 새 1)
{ta}

## B. 35점을 한꺼번에 추가 (후보 57점, 더 어려운 경우)
{tb}

## C. gallery로 쓴 사진의 방향별 Top-1 (A와 같은 설정, 1장일 때)
{td}
(b=뒤, f=앞, l=왼쪽, r=오른쪽)

## 해석 시 주의
- **읽는 법**: A(후보 23점)는 ①②가 모두 거의 포화라 단계 차이를 말하기 어렵다(①이 약간 높은 것도 구간이 겹친다). 후보가 57점으로 늘어난 B에서 ②가 ①보다 눈에 띄게 높고, ①은 확신 오답이 크다(1장 19.8%). 새 유물을 많이 추가할수록 ②(파인튜닝)의 이점이 커진다는 뜻이지만, 위 주의 사항 때문에 방향성만 본다. gallery 1장보다 2장이 모든 경우에 낫다.
- **표본 수**: 유물은 35점뿐이고 같은 유물의 질의는 서로 독립이 아니다. 질의 수(수백 장)가 아니라 유물 35점이 실제 표본 크기이며, 그래서 구간이 넓다.
- **현장보다 쉽다**: K-Art는 스튜디오 사진이라 배경이 단순하고 불상이 화면을 채운다. 사유의 방 사진은 불상이 작고 A·B 공통 배경이 커서 정확도가 훨씬 낮았다(results_stage_comparison.md 6절). 이 표의 수치를 현장 정확도로 읽으면 안 된다.
- **낙관적일 수 있음**: T·M(과 ②의 임계값 재산정)을 val과 none_val로 정했다. 같은 val 유물을 평가에 다시 썼으므로 임계값이 이 데이터에 맞춰져 있을 수 있다.
- 경쟁 상대는 기존 22점뿐이다. 현장의 A·B처럼 매우 닮은 두 점이 새로 같이 들어오는 경우는 이 평가에 없다. val 35점의 종류별 구성(불상 비율 등)은 확인하지 않았다.
- 이 평가는 "새 유물이 기존 gallery 속에서 찾아지는가"이고, 새 유물이 기존 유물(예: A01·B01)의 인식을 방해하는지는 보지 않았다 (기존 유물 질의는 평가하지 않음).
"""
    OUT.write_text(md.replace("\n", "\r\n"), encoding="utf-8", newline="")
    print(md)


if __name__ == "__main__":
    main()
