"""K-Art(AI Hub) 축소본을 유물 번호 기준으로 train/val에 나누고 manifest.csv를 만든다.

실행: python train/split_kart.py <1024px 축소본 폴더> [--val-ratio 0.2] [--seed 0]
- 입력 파일명: kart_3d{번호}_{f,b,l,r}.jpg  (유물당 4방향)
- 같은 유물의 4장은 항상 같은 split. 이미지는 data/train/K{번호}/, data/val/K{번호}/ 로 복사한다.
- AI Hub 약관상 원본·단순 가공본(축소본 포함)의 외부 공유는 금지다. data/는 git 제외를 유지한다.
"""
import argparse
import csv
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LICENSE = "AI Hub 디지털 K-Art 데이터(2022) 이용약관: 학습 활용 허용·출처 표기, 원본 재배포 금지, 공공누리 1·2유형(비상업 사용)"


def main(src: Path, val_ratio: float, seed: int) -> None:
    groups: dict[str, dict[str, Path]] = defaultdict(dict)
    for p in sorted(src.glob("kart_3d*_*.jpg")):
        m = re.fullmatch(r"kart_3d(\d+)_([bflr])\.jpg", p.name)
        if m:
            groups[m[1]][m[2]] = p
    ids = sorted(groups)
    rng = random.Random(seed)
    val_ids = set(rng.sample(ids, round(len(ids) * val_ratio)))

    rows = []
    for num in ids:
        split = "val" if num in val_ids else "train"
        aid = f"K{num}"
        for view, p in sorted(groups[num].items()):
            dst = DATA / split / aid / f"{view}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            rows.append({"artifact_id": aid, "name": f"K-Art {num}", "material": "", "license": LICENSE,
                         "source_url": "", "split": split, "path": f"{split}/{aid}/{view}.jpg",
                         "source": "K-Art(AI Hub)"})
    out = ROOT / "train" / "manifest.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"유물 {len(ids)}점: train {len(ids) - len(val_ids)} / val {len(val_ids)}, 이미지 {len(rows)}장 -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    main(a.src, a.val_ratio, a.seed)
