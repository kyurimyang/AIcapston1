"""비슷한 금동불상(C01~C20)과의 구분을 따로 본다. 결과만 보고하고 튜닝에는 쓰지 않는다.

실행 (레포 루트에서): python eval/evaluate_distractors.py [단계=2]

1) A/B → ? (test 사진 89장): 오답이 'A↔B 혼동'인지 'C 불상으로 착각'인지 나눈다.
   그리고 정답 점수와 가장 비슷한 C 불상 점수의 간격(여유)을 본다.
2) C → ? (gallery leave-one-out): C 불상 사진 하나를 빼고 나머지 gallery로 검색했을 때
   A/B로 착각하는 비율. C 불상은 사유의 방에 없어 test 사진이 없으므로 이 방법만 가능하다.
   같은 촬영 세트의 비슷한 사진이 gallery에 남아 있어 점수가 과대하게 나온다 (참고용).
   gallery 사진이 2장 이상인 유물만 쓴다.
원본(1장)과 다중 크롭(recognize.rank_multicrop과 같은 방식)을 같이 본다.
"""
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import CROP_SCALES, DB_PATH, MODELS, ROOT, center_crop, embed, load_image  # noqa: E402

AB = {"A01", "B01"}
LABEL_TO_ID = {"A": "A01", "B": "B01"}
METHODS = {"원본": (1.0,), "다중 크롭": CROP_SCALES}


def ranked_from(sims: np.ndarray, g_ids: np.ndarray, mask=None) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for s, a, m in zip(sims, g_ids, mask if mask is not None else np.ones(len(g_ids), bool)):
        if m and s > best.get(a, -9):
            best[a] = float(s)
    return sorted(best.items(), key=lambda kv: -kv[1])


def main(stage: int) -> None:
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    ck = str(ckpt) if ckpt.exists() else None
    with sqlite3.connect(DB_PATH) as con:
        gal = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='gallery'").fetchall()
        names = dict(con.execute("SELECT id, name FROM artifacts"))
    g_ids = np.array([a for a, _ in gal])
    g_imgs = [load_image(ROOT / "data" / p) for _, p in gal]
    G = embed(g_imgs, ckpt=ck)

    test_dir = ROOT / "data" / "test"
    with open(test_dir / "test_images.csv", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] in LABEL_TO_ID]
    t_imgs = [load_image(test_dir / r["path"]) for r in rows]

    for name, scales in METHODS.items():
        def sims(images):
            E = embed([center_crop(im, s) for im in images for s in scales], ckpt=ck)
            return (E @ G.T).reshape(len(images), len(scales), -1).max(axis=1)

        print(f"\n========== stage{stage} · {name} {scales} ==========")

        # 1) A/B 사진 → ?
        kinds, c_hits, margins = Counter(), Counter(), []
        for r, s in zip(rows, sims(t_imgs)):
            ranked = ranked_from(s, g_ids)
            truth = LABEL_TO_ID[r["label"]]
            top = ranked[0][0]
            kinds["정답" if top == truth else ("A↔B 혼동" if top in AB else "C로 착각")] += 1
            if top not in AB:
                c_hits[top] += 1
            score = dict(ranked)
            best_c = max(v for a, v in ranked if a not in AB)
            margins.append(score[truth] - best_c)
        n = len(rows)
        m = np.array(margins)
        print(f"[A/B 사진 {n}장 → ?] " + " / ".join(f"{k} {v}장({v / n:.1%})" for k, v in kinds.items()))
        if c_hits:
            print("  C로 착각한 대상: " + ", ".join(f"{a} {names.get(a, '')} {v}장" for a, v in c_hits.most_common()))
        print(f"  정답 점수 - 가장 비슷한 C 점수: 중앙 {np.median(m):+.3f}, 5% {np.percentile(m, 5):+.3f}, "
              f"C가 더 높음 {int((m < 0).sum())}장")

        # 2) C 사진 → ? (gallery LOO)
        S = sims(g_imgs)
        counts = Counter(g_ids)
        per = defaultdict(Counter)
        for i, a in enumerate(g_ids):
            if a in AB or counts[a] < 2:
                continue
            mask = np.ones(len(g_ids), bool)
            mask[i] = False
            top = ranked_from(S[i], g_ids, mask)[0][0]
            per[a]["n"] += 1
            per[a]["정답" if top == a else ("A/B로 착각" if top in AB else "다른 C")] += 1
        tot = Counter()
        for c in per.values():
            tot.update(c)
        print(f"[C 사진 {tot['n']}장(LOO, {len(per)}점) → ?] 정답 {tot['정답'] / tot['n']:.1%} / "
              f"A/B로 착각 {tot['A/B로 착각']}장 / 다른 C {tot['다른 C']}장")
        for a in sorted(per):
            c = per[a]
            if c["정답"] < c["n"]:
                print(f"  {a} {names.get(a, '')}: {c['정답']}/{c['n']} 정답, "
                      f"A/B로 {c['A/B로 착각']}, 다른 C로 {c['다른 C']}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
