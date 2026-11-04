"""test(사유의 방 촬영본)로 단계별 정확도 계산. 결과만 보고하고, 임계값 튜닝에는 쓰지 않는다.

실행: python eval/evaluate.py [단계=1]
- A/B: Top-1 정확도 (전체, 조건별)
- AB(동시 촬영): 1위가 A 또는 B면 정답으로 센다
- none: 오인식 판정은 val로 정한 T가 있어야 하므로, 여기서는 최고 점수 분포만 출력한다
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import MODELS, ROOT, embed, judge, load_image, search  # noqa: E402

import faiss  # noqa: E402

LABEL_TO_ID = {"A": "A01", "B": "B01"}


def main(stage: int) -> None:
    index = faiss.read_index(str(MODELS / f"index_stage{stage}.faiss"))
    ids = json.loads((MODELS / f"index_stage{stage}_ids.json").read_text(encoding="utf-8"))
    th_path = MODELS / f"thresholds_stage{stage}.json"
    th = json.loads(th_path.read_text()) if th_path.exists() else None
    ckpt = MODELS / f"ckpt_stage{stage}.pt"

    test_dir = ROOT / "data" / "test"
    with open(test_dir / "test_images.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    vecs = embed([load_image(test_dir / r["path"]) for r in rows], ckpt=str(ckpt) if ckpt.exists() else None)

    hit1, hit3 = defaultdict(list), defaultdict(list)
    ab_hits, none_scores, confusions = [], [], []
    for r, v in zip(rows, vecs):
        ranked = search(index, ids, v[None])
        top3 = [a for a, _ in ranked[:3]]
        label = r["label"]
        if label in LABEL_TO_ID:
            ok1, ok3 = top3[0] == LABEL_TO_ID[label], LABEL_TO_ID[label] in top3
            for key in ("전체", r["condition"]):
                hit1[key].append(ok1)
                hit3[key].append(ok3)
            if not ok1:
                confusions.append((r["path"], top3[0], round(ranked[0][1], 3)))
        elif label == "AB":
            ab_hits.append(top3[0] in LABEL_TO_ID.values())
        else:
            none_scores.append(ranked[0][1])

    print(f"== stage{stage} ==")
    print(f"{'조건':<10}{'장수':>5}{'Top-1':>8}{'Top-3':>8}")
    for key in ["전체"] + sorted(k for k in hit1 if k != "전체"):
        n = len(hit1[key])
        print(f"{key:<10}{n:>5}{sum(hit1[key]) / n:>8.1%}{sum(hit3[key]) / n:>8.1%}")
    print(f"\nAB {len(ab_hits)}장: 1위가 A 또는 B인 비율 {sum(ab_hits) / len(ab_hits):.1%}")
    s = sorted(none_scores)
    print(f"none {len(s)}장: 최고 유사도 min {s[0]:.3f} / 중앙 {s[len(s) // 2]:.3f} / max {s[-1]:.3f}")
    if th:
        rej = sum(judge([("x", x)], th["T"], th["M"]) == "reject" for x in none_scores)
        print(f"none 중 reject {rej}/{len(s)} (오인식률 {1 - rej / len(s):.1%}, T={th['T']})")
    print(f"\n오답 {len(confusions)}장 (파일, 1위, 점수):")
    for c in confusions:
        print("  ", *c)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
