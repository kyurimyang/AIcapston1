"""합성 검증셋으로 유물 점수 집계 방식(max·top3·top5·proto·max_proto)을 비교하고, 미리 정한 기준으로 고른다.

max_proto 채택 규칙 (시드 확대 검증, --seeds 모드. 실행 전에 정함, 결과를 본 뒤 바꾸지 않는다)
  시드 4개(기존 + 새 3개) × 2버전(synth_val, synth_val_cut) = 8개 중 max_proto의 주 기준이
  max보다 작은 경우가 7개 이상이고, 8개 모두에서 기존 조건(Top-1 하락 없음, 정답인데 reject +5%p 이내,
  음성 오인식 증가 없음)을 만족하면 채택한다. test 결과는 이 결정을 바꾸지 않는다.
  - 주 기준 = A·B 40장의 (A↔B 혼동 + 확신 오답), 조건은 아래 "선택 기준"의 1)~3)과 같다.
  - 시드 0은 data/synth_val, data/synth_val_cut. 새 시드 s는 data/synth_val_s{s}, data/synth_val_cut_s{s}.
  - T·M은 방식마다 val + none_val로 메모리에서 정한다 (시드와 무관하게 한 번).

실행 (레포 루트에서): python eval/compare_agg_synth.py
결과: eval/results_agg_synth.md
data/test는 읽지 않는다. 재학습 없음. models/에 아무것도 쓰지 않는다 (임계값은 메모리에서만 계산).

임계값
- 집계 방식이 바뀌면 점수 분포가 달라지므로 방식마다 T·M을 val 계열 데이터로 다시 정한다.
  규칙은 pick_thresholds.py --crop과 같다:
    양성 = gallery LOO(자기 자신을 뺀 gallery로 검색, 사진 2장 이상인 유물), 음성 = none_val + gallery에 없는 val 유물
    T = max(none_val 최고 점수, val 최고 점수의 95퍼센타일) + 0.01,  M = min(0.05, 정답 LOO 질의 (1위-2위) 간격 5퍼센타일)
- 기준선(max)은 앱이 지금 쓰는 파일 값(thresholds_stage2_crop.json)이다. max를 위 규칙으로 다시 계산해 같은지 확인한다.

선택 기준 (실행 전에 정해 두고 결과를 본 뒤 바꾸지 않는다)
- 주 기준: synth_val의 A·B 부분 40장에서 (A↔B 혼동 수 + 확신 오답 수)가 가장 작은 방식.
  A↔B 혼동 = A01 질의의 1위가 B01이거나 그 반대. 확신 오답 = 상태 ok인데 1위가 정답이 아님.
  (ok인 A↔B 혼동은 두 항에 모두 들어간다. 정의대로 그냥 더한다.)
- 조건 (기준선 = 현재 max + 현재 T·M, 같은 합성셋에서 비교):
  1) 전체 Top-1이 기준선보다 낮지 않음
  2) 정답인데 reject 비율 증가가 5%p 이내
  3) 배경만 음성, val 유물 음성의 오인식률(reject가 아닌 비율)이 각각 기준선보다 높지 않음
- synth_val_cut이 있으면 두 버전 모두에서 조건을 만족하는 방식 중에서 고르고,
  주 기준은 두 버전의 (A↔B 혼동 + 확신 오답)을 더한 값으로 본다.
- 동률이면 max > top3 > top5 > max_proto > proto 순 (현재 방식과 단순한 쪽 우선).
  조건을 만족하는 방식이 기준선뿐이거나 기준선보다 나은 방식이 없으면 max를 유지한다.
- 보조 지표(선택에 넣지 않음): LOO 뒤 gallery에서 사라진 유물 9점의 질의 180장을 음성으로 보고 reject 비율.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import evaluate_synth as es  # noqa: E402
from app import recognize  # noqa: E402
from app.recognize import AGGS, CROP_SCALES, DB_PATH, center_crop, embed, load_image, rank_embeddings  # noqa: E402

DATA = es.DATA
OUT = es.ROOT / "eval" / "results_agg_synth.md"
PREF = ["max", "top3", "top5", "max_proto", "proto"]
MAX_RIGHT_REJECT_INCREASE = 0.05


def crop_embed(images):
    E = embed([center_crop(im, s) for im in images for s in CROP_SCALES], ckpt=recognize._ckpt())
    return E.reshape(len(images), len(CROP_SCALES), -1)


def pick_thresholds(agg, G, ids, Vg, Vn, Vv):
    """pick_thresholds.py --crop과 같은 규칙을 집계 방식 agg로 계산한다."""
    gaps_ok = []
    for i, a in enumerate(ids):
        if (ids == a).sum() < 2:
            continue
        keep = np.arange(len(ids)) != i
        r = rank_embeddings(Vg[i], G[keep], ids[keep], agg)
        if r[0][0] == a:
            gaps_ok.append(r[0][1] - r[1][1])
    nn = np.array([rank_embeddings(v, G, ids, agg)[0][1] for v in Vn])
    nv = np.array([rank_embeddings(v, G, ids, agg)[0][1] for v in Vv]) if len(Vv) else nn
    T = max(nn.max(), np.percentile(nv, 95)) + 0.01
    M = max(0.0, min(0.05, float(np.percentile(gaps_ok, 5)))) if gaps_ok else 0.0
    return round(float(T), 4), round(M, 4)


def summary(res) -> dict:
    p, ab, neg, orph = res["pos"]["전체"], res["pos"]["A·B"], res["neg"], res["orphan"]
    return dict(
        top1=p["top1"] / p["n"], right_reject=p["right_reject"] / p["n"], ok=p["ok"], cw=p["confident_wrong"],
        ab_confuse=ab["ab_confuse"], ab_cw=ab["confident_wrong"], ab_score=ab["ab_confuse"] + ab["confident_wrong"],
        ab_top1=ab["top1"] / ab["n"],
        fa_bg=(neg["neg_bg"]["n"] - neg["neg_bg"]["reject"]) / neg["neg_bg"]["n"],
        fa_val=(neg["neg_val"]["n"] - neg["neg_val"]["reject"]) / neg["neg_val"]["n"],
        orphan_reject=orph["reject"] / orph["n"] if orph["n"] else float("nan"),
    )


def passes(s, b) -> list[str]:
    """조건 위반 목록 (빈 목록이면 통과)."""
    bad = []
    if s["top1"] < b["top1"] - 1e-12:
        bad.append("Top-1 하락")
    if s["right_reject"] - b["right_reject"] > MAX_RIGHT_REJECT_INCREASE + 1e-12:
        bad.append("정답 reject +5%p 초과")
    if s["fa_bg"] > b["fa_bg"] + 1e-12:
        bad.append("배경 오인식 증가")
    if s["fa_val"] > b["fa_val"] + 1e-12:
        bad.append("val 오인식 증가")
    return bad


KEEP_MARK = "<!-- 아래는 compare_agg_synth.py 기본 실행이 다시 써도 보존된다 -->"
SEED_START, SEED_END = "<!-- seeds:results -->", "<!-- /seeds:results -->"


def setup(aggs):
    """gallery·중복본·방식별 T·M (val + none_val로 메모리에서). max는 앱 파일 값과 같은지 확인한다."""
    index, ids, T0, M0 = recognize._stage()
    if recognize.AGG != "max":
        raise RuntimeError("기준선은 AGG=max로 돌려야 해요 (.env의 AGG 확인)")
    ids = np.asarray(ids)
    paths, G = es.load_gallery(index, ids)
    dups = es.gallery_dups(paths)
    with sqlite3.connect(DB_PATH) as con:
        val = [p for a, p in con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='val'")
               if a not in set(ids)]
    Vg = crop_embed([load_image(DATA / p) for p in paths])
    Vn = crop_embed([load_image(p) for p in sorted((DATA / "none_val").glob("*.jpg"))])
    Vv = crop_embed([load_image(DATA / p) for p in val])
    th = {agg: pick_thresholds(agg, G, ids, Vg, Vn, Vv) for agg in aggs}
    print("다시 계산한 임계값:", th, "| 파일(max):", (T0, M0), flush=True)
    return ids, paths, G, dups, th, T0, M0


def _read_out() -> str:
    return OUT.read_bytes().decode("utf-8").replace("\r\n", "\n") if OUT.exists() else ""


def _write_out(md: str) -> None:
    OUT.write_text(md.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8", newline="")


def write_md(md: str) -> None:
    """기본 실행 결과를 쓰되, 기존 문서의 KEEP_MARK 아래(기준 변경 이유·시드 검증)는 보존한다."""
    old = _read_out()
    tail = "\n" + old[old.index(KEEP_MARK):] if KEEP_MARK in old else ""
    _write_out(md.rstrip("\n") + "\n" + tail)


def seed_dirs(seed: int) -> list[tuple[str, Path]]:
    suf = "" if seed == 0 else f"_s{seed}"
    return [("synth_val", DATA / f"synth_val{suf}"), ("synth_val_cut", DATA / f"synth_val_cut{suf}")]


SEED_KEYS = [("ab_score", "주 기준", "{:.1f}"), ("ab_confuse", "A↔B 혼동", "{:.1f}"), ("ab_cw", "A·B 확신 오답", "{:.1f}"),
             ("top1", "전체 Top-1", "{:.1%}"), ("ok", "ok", "{:.1f}"), ("cw", "확신 오답", "{:.1f}"),
             ("right_reject", "정답인데 reject", "{:.1%}"), ("fa_bg", "배경 오인식", "{:.1%}"),
             ("fa_val", "val 오인식", "{:.1%}"), ("orphan_reject", "(보조) 미등록 9점 reject", "{:.1%}")]


def seeds_main(seeds: list[int]) -> None:
    """max vs max_proto를 시드 x 2버전에서 비교하고 맨 위 채택 규칙으로 판정한다."""
    doc = _read_out()
    if SEED_START not in doc or SEED_END not in doc:
        raise RuntimeError("results_agg_synth.md에 채택 규칙 절(seeds:results 표시)이 없어요. 규칙을 먼저 적어야 해요")
    for seed in seeds:
        for name, d in seed_dirs(seed):
            if not (d / "synth_val.csv").exists():
                raise FileNotFoundError(f"{d}가 없어요: python eval/make_synth_val.py --seed {seed}"
                                        + (" --cutout" if "cut" in name else ""))
    ids, paths, G, dups, th, T0, M0 = setup(["max", "max_proto"])
    if th["max"] != (round(T0, 4), round(M0, 4)):
        raise RuntimeError(f"max 임계값 재계산 {th['max']}이 파일 값 {(T0, M0)}과 달라요")
    T1, M1 = th["max_proto"]
    rows_out = []
    per = {"max": [], "max_proto": []}
    for seed in seeds:
        for name, d in seed_dirs(seed):
            rows, V = es.load_synth(d)
            b = summary(es.score_synth(rows, V, G, ids, paths, dups, "max", T0, M0))
            c = summary(es.score_synth(rows, V, G, ids, paths, dups, "max_proto", T1, M1))
            per["max"].append(b)
            per["max_proto"].append(c)
            bad = passes(c, b)
            rows_out.append((seed, name, b, c, c["ab_score"] < b["ab_score"], bad))
            print(f"seed {seed} {name}: max {b['ab_score']} / max_proto {c['ab_score']} {bad or '통과'}", flush=True)

    n = len(rows_out)
    wins = sum(r[4] for r in rows_out)
    n_ok = sum(not r[5] for r in rows_out)
    adopt = wins >= n - 1 and n_ok == n

    def arrow(b, c, k, f="{}"):
        return f"{f.format(b[k])} → {f.format(c[k])}"

    head = ("| 시드 | 버전 | 주 기준 max → max_proto | 작아짐 | A↔B 혼동 | A·B 확신 오답 | 전체 Top-1 | ok | 확신 오답 | "
            "정답인데 reject | 배경 오인식 | val 오인식 | (보조) 미등록 9점 reject | 조건 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    lines = [f"| {seed} | {name} | **{b['ab_score']} → {c['ab_score']}** | {'예' if win else '아니오'} | "
             f"{arrow(b, c, 'ab_confuse')} | {arrow(b, c, 'ab_cw')} | {arrow(b, c, 'top1', '{:.1%}')} | "
             f"{arrow(b, c, 'ok')} | {arrow(b, c, 'cw')} | {arrow(b, c, 'right_reject', '{:.1%}')} | "
             f"{arrow(b, c, 'fa_bg', '{:.1%}')} | {arrow(b, c, 'fa_val', '{:.1%}')} | "
             f"{arrow(b, c, 'orphan_reject', '{:.1%}')} | {'통과' if not bad else ', '.join(bad)} |"
             for seed, name, b, c, win, bad in rows_out]
    agg_t = "| 지표 | max 평균 [최소, 최대] | max_proto 평균 [최소, 최대] |\n|---|---|---|\n"
    for k, lab, f in SEED_KEYS:
        cells = []
        for a in ("max", "max_proto"):
            v = np.array([x[k] for x in per[a]], float)
            cells.append(f"{f.format(v.mean())} [{f.format(v.min())}, {f.format(v.max())}]")
        agg_t += f"| {lab} | {cells[0]} | {cells[1]} |\n"
    res = f"""{SEED_START}
### 결과 (시드 {', '.join(map(str, seeds))} × 2버전 = {n}개)
- T·M: max {T0} / {M0} (앱 파일 값 = 재계산 값), max_proto {T1} / {M1} (val + none_val, 메모리)
- 실행: `python eval/compare_agg_synth.py --seeds {','.join(map(str, seeds))}`

{head}{chr(10).join(lines)}

**시드·버전 {n}개 요약**

{agg_t}
### 판정
- max_proto의 주 기준이 max보다 작은 경우: **{wins}/{n}** (규칙: {n - 1}개 이상)
- 기존 조건을 모두 만족한 경우: **{n_ok}/{n}** (규칙: {n}개 전부)
- **판정: {'채택' if adopt else '불채택'}**
{SEED_END}"""
    doc = _read_out()
    i, j = doc.index(SEED_START), doc.index(SEED_END) + len(SEED_END)
    _write_out(doc[:i] + res + doc[j:])
    print(res)


def main() -> None:
    ids, paths, G, dups, th, T0, M0 = setup(AGGS)
    th_check = th["max"] == (round(T0, 4), round(M0, 4))

    sets = es.available_sets()
    data = {name: es.load_synth(d) for name, d in sets}
    S = {}  # (방식, 셋) -> summary
    for agg in ["max"] + [a for a in AGGS if a != "max"]:
        for name, (rows, V) in data.items():
            if agg == "max":  # 기준선 = 현재 앱 파일 값
                S[("max", name)] = summary(es.score_synth(rows, V, G, ids, paths, dups, "max", T0, M0))
            else:
                T, M = th[agg]
                S[(agg, name)] = summary(es.score_synth(rows, V, G, ids, paths, dups, agg, T, M))
        print(agg, "완료", flush=True)

    names = [n for n, _ in sets]
    verdict = {}
    for agg in AGGS:
        bad = {n: passes(S[(agg, n)], S[("max", n)]) for n in names}
        score = sum(S[(agg, n)]["ab_score"] for n in names)
        verdict[agg] = (bad, score)
    eligible = [a for a in AGGS if not any(verdict[a][0].values())]
    best = min(verdict[a][1] for a in eligible)
    pick = sorted([a for a in eligible if verdict[a][1] == best], key=PREF.index)[0]

    def row(agg, n):
        s = S[(agg, n)]
        T, M = (T0, M0) if agg == "max" else th[agg]
        bad = verdict[agg][0][n]
        return (f"| {agg} | {T:.4f} / {M:.4f} | **{s['ab_score']}** | {s['ab_confuse']} | {s['ab_cw']} | {s['ab_top1']:.1%} | "
                f"{s['top1']:.1%} | {s['ok']} | {s['cw']} | {s['right_reject']:.1%} | {s['fa_bg']:.1%} | {s['fa_val']:.1%} | "
                f"{s['orphan_reject']:.1%} | {'통과' if not bad else ', '.join(bad)} |")

    head = ("| 집계 | T / M | A·B 혼동+확신오답 | A↔B 혼동 | A·B 확신 오답 | A·B Top-1 | 전체 Top-1 | ok | 확신 오답 | "
            "정답인데 reject | 배경 오인식 | val 오인식 | (보조) 미등록 9점 reject | 조건 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    tables = "\n\n".join(f"## {n}\n\n" + head + "\n".join(row(a, n) for a in AGGS) for n in names)
    summ = "| 집계 | " + " | ".join(f"{n} 주 기준" for n in names) + " | 합 | 조건 |\n|---|" + "---|" * (len(names) + 2) + "\n"
    for a in AGGS:
        bad, sc = verdict[a]
        summ += (f"| {a} | " + " | ".join(str(S[(a, n)]["ab_score"]) for n in names) + f" | **{sc}** | "
                 + ("통과" if not any(bad.values()) else "; ".join(f"{n}: {', '.join(b)}" for n, b in bad.items() if b)) + " |\n")

    doc = __doc__.split("선택 기준 (실행 전에")[1].split('"""')[0]
    md = f"""# 집계 방식 비교 — 합성 검증셋 (test 미사용)

실행: `python eval/compare_agg_synth.py` · data/test는 읽지 않았다 · 재학습 없음 · models/는 바꾸지 않았다.
방식: STAGE={recognize.STAGE}, 다중 크롭 {CROP_SCALES}, 질의는 leave-one-out(원본 gallery 사진 + pHash 중복본 제외, `evaluate_synth.py`와 같음).

## 선택 기준 (실행 전에{doc.rstrip()}

## 임계값
- 기준선 max: 앱 파일 값 T={T0} · M={M0}. 같은 규칙으로 다시 계산한 값 {th['max']} → {'일치' if th_check else '**불일치 — 규칙 확인 필요**'}.
- 다른 방식은 val + none_val로 같은 규칙을 적용해 다시 정했다 (메모리에서만, 파일 안 씀): """ + ", ".join(
        f"{a} T={th[a][0]}·M={th[a][1]}" for a in AGGS if a != "max") + f"""

{tables}

## 선택
{summ}
- 조건을 만족한 방식: {', '.join(eligible)}
- **선택: `{pick}`**{' (현재 방식 유지)' if pick == 'max' else ''}

## 해석 시 주의
- 주 기준은 A01·B01 두 유물에서 나온 40장(버전당)뿐이고, 같은 gallery 사진에서 여러 질의가 나와 서로 독립이 아니다. 차이가 1~2장이면 우연일 수 있다.
- 합성셋과 현장(사유의 방)의 차이는 `results_synth_val.md` 주의 절 참고. 이 비교가 현장 결과를 보장하지 않는다.
- 임계값은 val·none_val로 정했고, val 유물은 val 음성 오인식률 계산에도 쓰이므로 그 수치는 낙관적일 수 있다.
- 선택한 방식을 앱에 쓰려면 같은 규칙으로 `models/thresholds_stage{recognize.STAGE}_crop_{{AGG}}.json`을 만들고 `AGG`를 바꿔야 한다. 이 스크립트는 그 파일을 쓰지 않는다.
- test로 결과를 보고하는 것은 방식을 고정한 뒤에 한 번만 한다.
"""
    write_md(md)
    print(md)


if __name__ == "__main__":
    if "--seeds" in sys.argv:
        seeds_main([int(x) for x in sys.argv[sys.argv.index("--seeds") + 1].split(",")])
    else:
        main()
