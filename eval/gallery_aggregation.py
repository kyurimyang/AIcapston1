"""유물 점수 집계 방식 비교 (max / top3 / top5 / proto / max_proto). val 계열 데이터만 쓴다. data/test는 읽지 않는다.

실행: python eval/gallery_aggregation.py [단계=2]

질의 = gallery 이미지 하나(leave-one-out: 그 이미지를 gallery·프로토타입에서 뺀다). 앱과 같은 다중 크롭.
음성 = none_val + val(gallery에 없는 유물 사진) -> T 재산정 (pick_thresholds.py와 같은 규칙).

B-1) A01<->B01 혼동 방향, 그리고 A01 gallery를 B01과 같은 장수로 줄였을 때(시드 5개 평균) 혼동이 줄어드는지
B-3) 선택 기준 (결과를 보기 전에 정함):
  탈락: LOO 전체 Top-1이 max보다 1.0%p 넘게 낮음 / 재산정 T에서 LOO 양성 통과율이 max보다 5%p 넘게 낮음
  1순위: min(A01 LOO 정확도, B01 LOO 정확도)가 큰 방식
  동률(1%p 이내): A01·B01 질의의 (정답 1위 - 2위) 간격 5퍼센타일이 큰 방식
  그래도 동률: max > top3 > top5 > max_proto > proto
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import AGGS, CROP_SCALES, DB_PATH, MODELS, ROOT, center_crop, embed, load_image, rank_embeddings  # noqa: E402

DATA = ROOT / "data"
PREF = ["max", "top3", "top5", "max_proto", "proto"]


def crop_embed(images, ck):
    E = embed([center_crop(im, s) for im in images for s in CROP_SCALES], ckpt=ck)
    return E.reshape(len(images), len(CROP_SCALES), -1)


def loo(Vq, G, ids, agg, drop=None):
    """질의 i마다 자기 자신을 뺀 gallery로 순위. drop(i) -> 추가로 뺄 gallery 인덱스 집합."""
    out = []
    for i in range(len(ids)):
        if (ids == ids[i]).sum() < 2:
            continue
        rm = {i} | (drop(i) if drop else set())
        keep = np.array([j for j in range(len(ids)) if j not in rm])
        out.append((ids[i], rank_embeddings(Vq[i], G[keep], ids[keep], agg)))
    return out


def main(stage: int) -> None:
    ck = MODELS / f"ckpt_stage{stage}.pt"
    ck = str(ck) if ck.exists() else None
    with sqlite3.connect(DB_PATH) as con:
        gal = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='gallery'").fetchall()
        val = con.execute("SELECT path FROM artifact_images WHERE split='val'").fetchall()
    ids = np.array([a for a, _ in gal])
    g_imgs = [load_image(DATA / p) for _, p in gal]
    G = embed(g_imgs, ckpt=ck)
    Vg = crop_embed(g_imgs, ck)
    Vn = crop_embed([load_image(p) for p in sorted((DATA / "none_val").glob("*.jpg"))], ck)
    Vv = crop_embed([load_image(DATA / p) for (p,) in val], ck)
    print(f"gallery {len(ids)}장 (A01 {(ids == 'A01').sum()}, B01 {(ids == 'B01').sum()}), val {len(Vv)}, none_val {len(Vn)}\n")

    # ---- B-1: 장수 편향 가설 (max) ----
    base = loo(Vg, G, ids, "max")

    def confusion(res):
        ab = [r[0][0] != "A01" and r[0][0] == "B01" for t, r in res if t == "A01"]  # A01 질의가 B01로
        ba = [r[0][0] == "A01" for t, r in res if t == "B01"]  # B01 질의가 A01로
        return sum(ab), sum(ba)

    ab, ba = confusion(base)
    nA, nB = (ids == "A01").sum(), (ids == "B01").sum()
    print("[B-1] max, gallery LOO: A01 질의 %d장 중 B01로 %d / B01 질의 %d장 중 A01로 %d" % (nA, ab, nB, ba))
    a_idx = np.where(ids == "A01")[0]
    tot_ab, tot_ba = [], []
    for seed in range(5):
        rng = np.random.default_rng(seed)

        def drop(i, rng=rng):
            # A01 gallery를 B01 장수(20장)로 맞춘다. 질의 자신은 이미 뺐으므로 남은 A01 중 20장만 쓴다
            cand = [j for j in a_idx if j != i]
            keep = set(rng.choice(cand, size=min(int(nB), len(cand)), replace=False).tolist())
            return {j for j in cand if j not in keep}

        r = loo(Vg, G, ids, "max", drop)
        x, y = confusion(r)
        tot_ab.append(x); tot_ba.append(y)
    print("      A01을 %d장으로 무작위 축소(시드 5개 평균): A01->B01 %.1f / B01->A01 %.1f\n" % (nB, np.mean(tot_ab), np.mean(tot_ba)))

    # ---- B-3: 집계 방식 비교 ----
    rows = {}
    for agg in AGGS:
        res = loo(Vg, G, ids, agg)
        top = np.array([r[0][1] for _, r in res])
        ok = np.array([r[0][0] == t for t, r in res])
        gap = np.array([r[0][1] - r[1][1] for _, r in res])
        acc = lambda a: np.mean([r[0][0] == t for t, r in res if t == a])
        ab_gap = [r[0][1] - r[1][1] for t, r in res if t in ("A01", "B01") and r[0][0] == t]
        ab_cnt = confusion(res)
        neg = np.array([rank_embeddings(v, G, ids, agg)[0][1] for v in np.concatenate([Vn, Vv])])
        nn = np.array([rank_embeddings(v, G, ids, agg)[0][1] for v in Vn])
        nv = neg[len(Vn):]
        T = max(nn.max(), np.percentile(nv, 95)) + 0.01
        rows[agg] = dict(top1=ok.mean(), A=acc("A01"), B=acc("B01"), ab=ab_cnt,
                         gap5=float(np.percentile(ab_gap, 5)), gapmed=float(np.median(ab_gap)),
                         T=T, rej_none=(nn < T).mean(), rej_val=(nv < T).mean(), keep=(top >= T).mean(),
                         M=min(0.05, float(np.percentile(gap[ok], 5))))
    print("| 집계 | LOO Top-1 | A01 | B01 | A→B/B→A 오류 | A·B 간격 5% | 간격 중앙 | T | none 거절 | val 거절 | 양성 통과 | M |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for a, r in rows.items():
        print(f"| {a} | {r['top1']:.1%} | {r['A']:.1%} | {r['B']:.1%} | {r['ab'][0]}/{r['ab'][1]} | {r['gap5']:.3f} | {r['gapmed']:.3f} "
              f"| {r['T']:.3f} | {r['rej_none']:.0%} | {r['rej_val']:.0%} | {r['keep']:.1%} | {r['M']:.3f} |")

    # ---- 기준 적용 ----
    m = rows["max"]
    ok_aggs = [a for a, r in rows.items() if r["top1"] >= m["top1"] - 0.01 and r["keep"] >= m["keep"] - 0.05]
    print("\n필수 조건 통과:", ok_aggs, "| 탈락:", [a for a in rows if a not in ok_aggs])
    best_min = max(min(rows[a]["A"], rows[a]["B"]) for a in ok_aggs)
    tie = [a for a in ok_aggs if min(rows[a]["A"], rows[a]["B"]) >= best_min - 0.01]
    best_gap = max(rows[a]["gap5"] for a in tie)
    pick = sorted(tie, key=lambda a: (-(rows[a]["gap5"] >= best_gap - 1e-9), PREF.index(a)))[0]
    print("1순위 동률권(min(A,B) 1%p 이내):", tie, "-> 선택:", pick)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
