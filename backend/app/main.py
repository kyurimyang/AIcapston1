import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import rag, recognize

app = FastAPI(title="유담 YU:DAM")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 시연용. ngrok 주소가 매번 바뀐다
    allow_methods=["*"],
    allow_headers=["*"],
)

NARRATIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "narrations.json"

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
    return {"ok": True}


@app.post("/recognize", response_model=RecognizeResponse)
async def recognize_image(image: UploadFile = File(...)):
    return recognize.recognize(await image.read())


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
