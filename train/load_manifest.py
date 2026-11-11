"""수집 목록(CSV)을 검증하고 artifacts.db에 train/val 이미지를 적재한다.

실행: python train/load_manifest.py train/manifest.csv [--dry-run]
- 컬럼: artifact_id, name, material, license, source_url, split, path, source
  path는 data/ 기준 상대경로 (예: train/T001/01.jpg)
- 검증 (하나라도 어기면 아무것도 적재하지 않는다):
  · split은 train 또는 val, 한 유물은 한 split에만 (유물 ID 기준 분할)
  · license 필수 (모르면 넣지 않는다)
  · gallery 유물 ID(A01, B01, C01…)와 겹치면 안 된다
  · path가 data/gallery/ 또는 data/test/ 아래면 안 된다
  · 파일이 실제로 있어야 한다
- 유물당 4장 미만이면 경고 (배치 = 유물 16개 × 이미지 4장)
- 다시 실행하면 train/val 행만 새로 채우고 gallery·test·narrations는 건드리지 않는다.
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "artifacts.db"
REQUIRED = ["artifact_id", "name", "license", "split", "path", "source"]


def main(manifest: str, dry_run: bool) -> None:
    with open(manifest, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    con = sqlite3.connect(DB)
    gallery_ids = {r[0] for r in con.execute(
        "SELECT DISTINCT artifact_id FROM artifact_images WHERE split = 'gallery'")}

    errors: list[str] = []
    splits: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for n, r in enumerate(rows, start=2):
        for col in REQUIRED:
            if not (r.get(col) or "").strip():
                errors.append(f"{n}행: {col} 비어 있음")
        aid, split, path = r["artifact_id"].strip(), r["split"].strip(), r["path"].strip()
        if split not in ("train", "val"):
            errors.append(f"{n}행: split은 train/val만 가능 ({split!r})")
        if aid in gallery_ids:
            errors.append(f"{n}행: {aid}는 gallery 유물 (train/val에 쓸 수 없음)")
        p = Path(path)
        if p.parts and p.parts[0] in ("gallery", "test", "none_val"):
            errors.append(f"{n}행: {path}는 train/val 경로가 아님")
        if not (DATA / p).is_file():
            errors.append(f"{n}행: 파일 없음 data/{path}")
        splits[aid].add(split)
        counts[aid] += 1
    for aid, s in splits.items():
        if len(s) > 1:
            errors.append(f"{aid}: train과 val에 나뉘어 있음 (유물 ID 기준으로 한쪽에만)")

    if errors:
        print("검증 실패: 적재하지 않았습니다")
        print("\n".join(errors))
        sys.exit(1)

    for aid, c in counts.items():
        if c < 4:
            print(f"경고: {aid}는 이미지 {c}장 (4장 미만)")

    n_train = len([a for a, s in splits.items() if "train" in s])
    n_val = len([a for a, s in splits.items() if "val" in s])
    print(f"유물 train {n_train}점 / val {n_val}점, 이미지 {len(rows)}장")
    if dry_run:
        print("--dry-run: 적재하지 않음")
        return

    con.execute("DELETE FROM artifact_images WHERE split IN ('train', 'val')")
    seen: set[str] = set()
    for r in rows:
        aid = r["artifact_id"].strip()
        if aid not in seen:
            seen.add(aid)
            con.execute(
                "INSERT INTO artifacts (id, name, material, source_url, license) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, material = excluded.material, "
                "source_url = excluded.source_url, license = excluded.license",
                (aid, r["name"].strip(), (r.get("material") or "").strip() or None,
                 (r.get("source_url") or "").strip() or None, r["license"].strip()),
            )
        con.execute("INSERT INTO artifact_images VALUES (?, ?, ?, ?)",
                    (aid, r["path"].strip(), r["source"].strip(), r["split"].strip()))
    con.commit()
    con.close()
    print("적재 완료")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(args[0], "--dry-run" in sys.argv)
