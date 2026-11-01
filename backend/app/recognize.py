"""유물 인식 (CLIP + FAISS). 2주차에 구현.

status 규칙 (임계값 T·M은 val로만 정한다)
- ok:        score >= T 이고 (1위 - 2위) >= M
- uncertain: score >= T 이지만 1·2위가 비슷함
- reject:    score < T
"""


def recognize(image_bytes: bytes) -> dict:
    # TODO: open_clip 임베딩 -> FAISS(models/index_stageN.faiss) 검색
    return {
        "status": "reject",
        "message": "아직 인식 모델이 연결되지 않았어요",
    }
