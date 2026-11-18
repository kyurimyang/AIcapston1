"""test 사진별 인식 결과(② + 다중 크롭)를 CSV로 낸다. 결과만 보고하고 튜닝에는 쓰지 않는다.

실행 (레포 루트에서): python eval/per_photo.py [단계=2] [출력=eval/per_photo_stage2.csv]
범용 AI 비교(이슈 #16)의 15장은 이 CSV에서 파일명으로 골라 쓴다.
"""
import csv
import json
import sys
import time
from pathlib import Path

import faiss

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import MODELS, ROOT, judge, load_image, rank_multicrop  # noqa: E402


def main(stage: int, out: Path) -> None:
    index = faiss.read_index(str(MODELS / f"index_stage{stage}.faiss"))
    ids = json.loads((MODELS / f"index_stage{stage}_ids.json").read_text(encoding="utf-8"))
    th = json.loads((MODELS / f"thresholds_stage{stage}_crop.json").read_text())
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    ckpt = str(ckpt) if ckpt.exists() else None

    test_dir = ROOT / "data" / "test"
    with open(test_dir / "test_images.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rank_multicrop(index, ids, load_image(test_dir / rows[0]["path"]), ckpt)  # warmup

    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "label", "condition", "status", "top1", "score1", "top2", "score2", "sec"])
        for r in rows:
            t0 = time.perf_counter()
            ranked = rank_multicrop(index, ids, load_image(test_dir / r["path"]), ckpt)
            sec = time.perf_counter() - t0
            st = judge(ranked, th["T"], th["M"])
            w.writerow([r["path"], r["label"], r["condition"], st,
                        ranked[0][0], f"{ranked[0][1]:.3f}", ranked[1][0], f"{ranked[1][1]:.3f}", f"{sec:.2f}"])
    print(f"{len(rows)}장 -> {out}")


if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(s, Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / f"per_photo_stage{s}.csv")
