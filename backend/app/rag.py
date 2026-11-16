"""추가 질문 RAG. 근거는 유물 설명(국가유산포털 원문)뿐이다.

유물 2점의 설명은 몇 문단밖에 안 돼서 벡터 검색 없이 설명 전체를 문단 번호와 함께 프롬프트에 넣는다.
LLM은 근거 문단 번호를 함께 돌려주고, 근거가 없으면 grounded=false로 거절한다.

환경변수 (레포 루트 .env)
- LLM_PROVIDER: openai | anthropic | gemini
- LLM_API_KEY, LLM_MODEL: 해당 회사의 키와 모델 이름
- LLM_TIMEOUT: 초 (기본 8). 프론트 /ask 타임아웃(15초)보다 짧게 둔다.
키가 없거나 호출이 실패해도 서버는 죽지 않고 "자료에 없는 내용이에요"로 답한다.
"""
import json
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "artifacts.db"
META_PATH = ROOT / "backend" / "scripts" / "artifact_meta.json"
load_dotenv(ROOT / ".env")  # LLM 설정은 호출 시점에 읽으므로 main.py 로드 순서와 무관

REFUSAL = "자료에 없는 내용이에요"
SOURCE_LABEL = "국가유산포털 설명"

PROFILE_STYLE = {
    "congenital": "듣는 사람은 태어날 때부터 앞이 보이지 않았다. 색이나 빛 같은 시각 기억을 전제하지 말고, "
                  "모양은 손으로 만지는 느낌이나 몸 동작으로 옮겨 말한다.",
    "acquired": "듣는 사람은 예전에 볼 수 있었다. 시각적인 비유를 써도 되고, 장면을 떠올리게 말한다.",
    "low_vision": "듣는 사람은 조금 볼 수 있다. 해당 부위가 불상의 어디쯤(위·아래, 어느 손 근처)에 있는지 함께 말한다.",
}

SYSTEM = """너는 박물관 음성 도슨트다. 아래 [자료]에 적힌 내용만 근거로 질문에 답한다.
규칙
- [자료]에 없는 사실은 추측하거나 일반 상식으로 채우지 않는다. 답할 근거가 없으면 grounded를 false로 한다.
- 답은 한국어 2~3문장, 음성으로 읽히므로 괄호·한자·기호·목록을 쓰지 않는다.
- {style}
- 반드시 JSON 하나만 출력한다: {{"answer": "...", "sources": [근거 문단 번호 정수], "grounded": true 또는 false}}"""


def _artifact(artifact_id: str) -> dict | None:
    """DB가 있으면 DB(artifacts 테이블), 없으면 같은 원문인 artifact_meta.json에서 읽는다."""
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
            if row:
                return dict(row)
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    return {"id": artifact_id, "name": None, **meta[artifact_id]} if artifact_id in meta else None


def build_paragraphs(art: dict) -> list[str]:
    """1번 = 기본 정보, 2번부터 = 설명 문단."""
    labels = {"name": "이름", "era": "시대", "material": "재질", "size": "크기"}
    basic = ", ".join(f"{v} {art[k]}" for k, v in labels.items() if art.get(k))
    paras = [f"기본 정보: {basic}"] if basic else []
    paras += [p.strip() for p in (art.get("description") or "").split("\n") if p.strip()]
    return paras


def build_prompt(paras: list[str], profile: str, question: str) -> tuple[str, str]:
    system = SYSTEM.format(style=PROFILE_STYLE.get(profile, PROFILE_STYLE["acquired"]))
    material = "\n".join(f"[{i}] {p}" for i, p in enumerate(paras, start=1))
    return system, f"[자료]\n{material}\n\n[질문]\n{question}"


# ---------------- LLM 호출 (회사별) ----------------
def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_llm(system: str, user: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "").lower()
    key, model = os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL")
    timeout = float(os.getenv("LLM_TIMEOUT", "8"))
    if not (provider and key and model):
        raise RuntimeError("LLM_PROVIDER, LLM_API_KEY, LLM_MODEL을 .env에 채워 주세요")

    if provider == "openai":
        r = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}, {
            "model": model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }, timeout)
        return r["choices"][0]["message"]["content"]
    if provider == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": key, "anthropic-version": "2023-06-01"}, {
                      "model": model, "max_tokens": 400, "temperature": 0, "system": system,
                      "messages": [{"role": "user", "content": user}],
                  }, timeout)
        return "".join(b.get("text", "") for b in r["content"])
    if provider == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"x-goog-api-key": key}, {
                      "systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                  }, timeout)
        return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    raise RuntimeError(f"모르는 LLM_PROVIDER: {provider}")


# ---------------- 응답 검증 ----------------
def parse_reply(raw: str, n_paras: int) -> dict:
    """LLM 출력 -> 응답. 근거 번호가 실제 문단 범위 밖이거나 비어 있으면 거절로 바꾼다."""
    m = re.search(r"\{.*\}", raw, re.S)  # 코드블록·앞뒤 말이 붙어 와도 JSON만 꺼낸다
    data = json.loads(m.group(0) if m else raw)
    nums = sorted({int(s) for s in data.get("sources", []) if str(s).strip().isdigit()})
    nums = [n for n in nums if 1 <= n <= n_paras]
    answer = str(data.get("answer", "")).strip()
    if not (data.get("grounded") is True and nums and answer):
        return {"answer": REFUSAL, "sources": [], "grounded": False}
    return {"answer": answer, "sources": [_label(n) for n in nums], "grounded": True}


def _label(n: int) -> str:
    return f"{SOURCE_LABEL} 기본 정보" if n == 1 else f"{SOURCE_LABEL} {n - 1}문단"


def answer(artifact_id: str, profile: str, question: str) -> dict:
    refusal = {"answer": REFUSAL, "sources": [], "grounded": False}
    art = _artifact(artifact_id)
    paras = build_paragraphs(art) if art else []
    if not paras or not question.strip():
        return refusal
    try:
        return parse_reply(call_llm(*build_prompt(paras, profile, question)), len(paras))
    except Exception as e:  # 키 없음·타임아웃·JSON 깨짐 모두 거절로 (시연 중 서버가 죽지 않게)
        print(f"[ask 실패] {type(e).__name__}: {e}")
        return refusal
