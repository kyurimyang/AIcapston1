"""gallery 이미지로 FAISS 인덱스 구축.

실행: python backend/scripts/build_index.py [단계=1]
- 대상은 artifact_images에서 split='gallery'인 이미지뿐이다. train·val·test는 읽지 않는다.
- 결과: models/index_stage{N}.faiss, models/index_stage{N}_ids.json (벡터 순서대로 유물 ID)
- 단계 ②③은 models/ckpt_stage{N}.pt가 있으면 그 가중치로 임베딩한다.
"""
import json
import sqlite3
import sys
from pathlib import Path

import faiss

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognize import DB_PATH, MODELS, ROOT, embed, load_image  # noqa: E402


def main(stage: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT artifact_id, path FROM artifact_images WHERE split = 'gallery' ORDER BY artifact_id, path"
        ).fetchall()
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    vecs = embed(
        [load_image(ROOT / "data" / p) for _, p in rows],
        ckpt=str(ckpt) if ckpt.exists() else None,
    )
    index = faiss.IndexFlatIP(vecs.shape[1])  # 정규화된 벡터의 내적 = 코사인
    index.add(vecs)
    MODELS.mkdir(exist_ok=True)
    faiss.write_index(index, str(MODELS / f"index_stage{stage}.faiss"))
    (MODELS / f"index_stage{stage}_ids.json").write_text(
        json.dumps([a for a, _ in rows], ensure_ascii=False), encoding="utf-8"
    )
    print(f"stage{stage}: {index.ntotal}장, {len({a for a, _ in rows})}점")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
