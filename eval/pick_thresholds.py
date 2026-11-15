"""val 계열 데이터로만 임계값 T·M을 정한다. data/test는 읽지 않는다.

실행: python eval/pick_thresholds.py [단계=1] [--write]
- 양성: gallery 이미지를 하나씩 빼고(leave-one-out) 나머지 gallery로 검색. 이미지가 2장 이상인 유물만.
- 음성: none_val(유물 없는 사진) + val(gallery에 없는 다른 유물 사진)
- T: 음성 최고 유사도의 상한 바로 위. LOO 양성은 gallery 중복 사진 때문에 점수가 과대하므로
  양성 쪽으로 끌어올리지 않는다 (실제 촬영 사진을 과하게 reject하지 않기 위해)
- M: 양성 중 정답인 것들의 (1위-2위) 간격 5퍼센타일, 상한 0.05
- --write를 주면 models/thresholds_stage{N}.json에 저장한다 (recognize.py가 읽는다)
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import DB_PATH, MODELS, ROOT, embed, load_image  # noqa: E402

DATA = ROOT / "data"


def best_by_artifact(sims: np.ndarray, ids: np.ndarray, mask: np.ndarray | None = None):
    """한 질의의 유물별 최고 유사도 -> (정렬된 [(id, score)])."""
    best: dict[str, float] = {}
    for s, a, m in zip(sims, ids, mask if mask is not None else np.ones(len(ids), bool)):
        if m and s > best.get(a, -9):
            best[a] = float(s)
    return sorted(best.items(), key=lambda kv: -kv[1])


def main(stage: int, write: bool) -> None:
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    ck = str(ckpt) if ckpt.exists() else None
    with sqlite3.connect(DB_PATH) as con:
        gal = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='gallery'").fetchall()
        val = con.execute("SELECT path FROM artifact_images WHERE split='val'").fetchall()
    g_ids = np.array([a for a, _ in gal])
    G = embed([load_image(DATA / p) for _, p in gal], ckpt=ck)
    none_paths = sorted((DATA / "none_val").glob("*.jpg"))
    N = embed([load_image(p) for p in none_paths], ckpt=ck)
    V = embed([load_image(DATA / p) for (p,) in val], ckpt=ck)

    counts = {a: int((g_ids == a).sum()) for a in set(g_ids)}
    pos_top, pos_gap, pos_ok = [], [], []
    S = G @ G.T
    for i, a in enumerate(g_ids):
        if counts[a] < 2:
            continue
        mask = np.ones(len(g_ids), bool)
        mask[i] = False
        r = best_by_artifact(S[i], g_ids, mask)
        pos_top.append(r[0][1])
        pos_gap.append(r[0][1] - r[1][1])
        pos_ok.append(r[0][0] == a)

    def neg(Q):
        out = []
        for q in Q:
            r = best_by_artifact(G @ q, g_ids)
            out.append((r[0][1], r[0][1] - r[1][1]))
        return np.array(out)

    nn, nv = neg(N), neg(V)
    pos_top, pos_gap, pos_ok = np.array(pos_top), np.array(pos_gap), np.array(pos_ok)
    pct = lambda x, p: float(np.percentile(x, p))
    print(f"== stage{stage} ==")
    print(f"양성(LOO) {len(pos_top)}장, Top-1 {pos_ok.mean():.1%}, 점수 5%={pct(pos_top,5):.3f} 중앙={pct(pos_top,50):.3f}")
    print(f"음성 none_val {len(nn)}장: 최고 점수 max={nn[:,0].max():.3f} 중앙={np.median(nn[:,0]):.3f}")
    print(f"음성 val {len(nv)}장: 최고 점수 max={nv[:,0].max():.3f} 95%={pct(nv[:,0],95):.3f} 중앙={np.median(nv[:,0]):.3f}")

    neg_max = max(nn[:, 0].max(), pct(nv[:, 0], 95))
    T = neg_max + 0.01
    M = min(0.05, pct(pos_gap[pos_ok], 5)) if pos_ok.any() else 0.0
    M = max(M, 0.0)
    rej_none = (nn[:, 0] < T).mean()
    rej_val = (nv[:, 0] < T).mean()
    keep_pos = (pos_top >= T).mean()
    print(f"-> T={T:.3f} M={M:.3f} | none 거절 {rej_none:.0%}, val 거절 {rej_val:.0%}, 양성 통과 {keep_pos:.0%}"
          f"{'' if pct(pos_top, 5) > neg_max else '  (주의: 양성·음성 분포가 겹침)'}")
    if write:
        p = MODELS / f"thresholds_stage{stage}.json"
        p.write_text(json.dumps({"T": round(T, 4), "M": round(M, 4)}), encoding="utf-8")
        print("저장:", p)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 1, "--write" in sys.argv)
