import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# recognize가 import 시점에 STAGE를 읽으므로 그보다 먼저 레포 루트의 .env를 읽는다
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import rag, recognize  # noqa: E402

WARMUP: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 첫 요청이 모델 로딩을 떠안지 않도록 시작할 때 미리 올린다
    t = time.perf_counter()
    try:
        WARMUP.update(recognize.warmup(), seconds=round(time.perf_counter() - t, 1))
        print(f"[warmup] {WARMUP}")
    except Exception as e:  # 인덱스가 없어도 /health로 원인을 볼 수 있게 서버는 띄운다
        WARMUP.update(error=f"{type(e).__name__}: {e}")
        print(f"[warmup 실패] {WARMUP['error']}")
    yield


app = FastAPI(title="유담 YU:DAM", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 시연용. ngrok 주소가 매번 바뀐다
    allow_methods=["*"],
    allow_headers=["*"],
)

# 해설 텍스트는 얼굴·라이선스 문제가 없어 git으로 관리한다 (docs/narration_guide.md)
NARRATIONS_PATH = Path(__file__).resolve().parents[1] / "scripts" / "narrations.json"

Profile = Literal["congenital", "acquired", "low_vision"]
Length = Literal["short", "long"]


class RecognizeResponse(BaseModel):
    status: Literal["ok", "uncertain", "reject"]
    artifact_id: str | None = None
    name: str | None = None
    score: float | None = None
    message: str | None = None


class NarrationResponse(BaseModel):
    text: str
    reviewed: bool


class AskRequest(BaseModel):
    artifact_id: str
    profile: Profile
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    grounded: bool


@app.get("/health")
def health():
    return {"ok": "error" not in WARMUP, **WARMUP}


@app.post("/recognize", response_model=RecognizeResponse)
async def recognize_image(
    image: UploadFile | None = File(None),  # 기존 단일 사진 (호환 유지)
    images: list[UploadFile] = File(default=[]),  # 연속 촬영한 여러 장
):
    files = ([image] if image else []) + images
    if not files:
        raise HTTPException(422, "image 또는 images가 필요해요")
    return recognize.recognize_many([await f.read() for f in files[:8]])


@app.get("/narration", response_model=NarrationResponse)
def narration(artifact_id: str, profile: Profile, length: Length):
    # 검수 완료(reviewed=true)된 해설만 내보낸다
    if not NARRATIONS_PATH.exists():
        raise HTTPException(404, "해설 데이터가 없어요")
    items = json.loads(NARRATIONS_PATH.read_text(encoding="utf-8"))
    for n in items:
        if (n["artifact_id"], n["profile"], n["length"]) == (artifact_id, profile, length):
            if n.get("reviewed"):
                return {"text": n["text"], "reviewed": True}
    raise HTTPException(404, "검수된 해설이 없어요")


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    return rag.answer(req.artifact_id, req.profile, req.question)
