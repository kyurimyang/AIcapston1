"""data/artifacts.db 생성: 스키마 + gallery 이미지 + test_images.csv 적재.

실행: python backend/scripts/init_db.py
- artifacts의 시대·재질·크기·설명은 artifact_meta.json(국가유산포털 원문)에서 읽는다.
  source_url·license도 확인한 값만 넣는다 (비워 둔 값은 만들어 넣지 않는다).
- 다시 실행하면 artifact_images와 test_images를 새로 채우고, narrations는 유지한다.
"""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB = DATA / "artifacts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, era TEXT, material TEXT, size TEXT,
    description TEXT, source_url TEXT, license TEXT
);
CREATE TABLE IF NOT EXISTS artifact_images (
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    path TEXT NOT NULL, source TEXT,
    split TEXT NOT NULL CHECK (split IN ('train', 'val', 'gallery'))
);
CREATE TABLE IF NOT EXISTS narrations (
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    profile TEXT NOT NULL CHECK (profile IN ('congenital', 'acquired', 'low_vision')),
    length TEXT NOT NULL CHECK (length IN ('short', 'long')),
    text TEXT, reviewed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (artifact_id, profile, length)
);
CREATE TABLE IF NOT EXISTS test_images (
    path TEXT PRIMARY KEY,
    label TEXT NOT NULL CHECK (label IN ('A', 'B', 'AB', 'none')),
    condition TEXT, note TEXT
);
"""

# 두 점의 이름이 같으므로 호수를 붙인다 (data/README.md)
ARTIFACTS = [
    ("A01", "금동미륵보살반가사유상 (국보 제78호)"),
    ("B01", "금동미륵보살반가사유상 (국보 제83호)"),
    ("C01", "금동미륵보살반가사유상 (국보 제118호)"),
    ("C02", "Pensive bodhisattva (메트로폴리탄미술관)"),
    ("C03", "금동반가사유상 (국립중앙박물관 M265)"),
    ("C04", "금동미륵보살반가사유상 (양산 출토, 신수 4165)"),
    ("C05", "금동 반가사유상 (보물, 덕수 2327)"),
    ("C06", "금동반가사유상 (덕수 3200)"),
]


GALLERY_SOURCE = "국가유산포털 문화재대관"  # A01·B01 gallery 이미지는 모두 같은 출처


def main() -> None:
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.executemany("INSERT OR IGNORE INTO artifacts (id, name) VALUES (?, ?)", ARTIFACTS)

    meta = json.loads((Path(__file__).parent / "artifact_meta.json").read_text(encoding="utf-8"))
    con.executemany(
        "UPDATE artifacts SET era = :era, material = :material, size = :size, "
        "description = :description, source_url = :source_url, license = :license WHERE id = :id",
        [{"source_url": None, "license": None, **v, "id": k} for k, v in meta.items()],
    )

    con.execute("DELETE FROM artifact_images WHERE split = 'gallery'")
    for art_id, in con.execute("SELECT id FROM artifacts").fetchall():
        folder = DATA / "gallery" / art_id
        if not folder.is_dir():
            continue
        con.executemany(
            "INSERT INTO artifact_images VALUES (?, ?, ?, 'gallery')",
            [(art_id, p.relative_to(DATA).as_posix(), GALLERY_SOURCE)
             for p in sorted(folder.glob("*.jpg"))],
        )

    con.execute("DELETE FROM test_images")
    with open(DATA / "test" / "test_images.csv", encoding="utf-8-sig", newline="") as f:
        con.executemany(
            "INSERT INTO test_images VALUES (?, ?, ?, ?)",
            [(r["path"], r["label"], r["condition"], r["note"]) for r in csv.DictReader(f)],
        )
    con.commit()
    for t in ("artifacts", "artifact_images", "narrations", "test_images"):
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
