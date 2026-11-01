"""추가 질문 RAG. 근거는 artifacts 테이블(e뮤지엄 설명)뿐이다."""


def answer(artifact_id: str, profile: str, question: str) -> dict:
    # TODO: artifacts.description 검색 -> LLM 답변. 근거 없으면 grounded=False
    return {
        "answer": "자료에 없는 내용이에요",
        "sources": [],
        "grounded": False,
    }
