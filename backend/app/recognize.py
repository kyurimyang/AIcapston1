"""유물 인식 (CLIP + FAISS).

status 규칙 (임계값 T·M은 val로만 정한다)
- ok:        score >= T 이고 (1위 - 2위) >= M
- uncertain: score >= T 이지만 1·2위가 비슷함
- reject:    score < T

단계는 환경변수 STAGE(기본 1)로 고른다: models/index_stage{N}.faiss
임계값은 models/thresholds_stage{N}.json ({"T": ..., "M": ...}). 파일이 없으면 T=M=0이라
reject·uncertain이 나오지 않는다. val로 정하기 전의 임시 상태다.
"""
import io
import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np
import open_clip
import torch
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
DB_PATH = ROOT / "data" / "artifacts.db"

MODEL_NAME = "ViT-B-16-quickgelu"  # openai 가중치는 QuickGELU 구조
PRETRAINED = "openai"
STAGE = int(os.getenv("STAGE", "1"))

MESSAGES = {
    "uncertain": "반가사유상 종류로 보여요. 조금 더 가까이에서 다시 찍어 주세요",
    "reject": "유물을 찾지 못했어요. 정면에서 다시 찍어 주세요",
}


@lru_cache(maxsize=1)
def _clip(ckpt: str | None = None):
    """ckpt가 있으면 파인튜닝한 가중치(②③)를 얹는다. 없으면 사전학습 그대로(①)."""
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    if ckpt:
        model.load_state_dict(torch.load(ckpt, map_location="cpu"))
    return model.eval(), preprocess


def load_image(src) -> Image.Image:
    """경로 또는 바이트 -> RGB. 폰 사진은 EXIF 회전 정보를 반영해야 한다."""
    img = Image.open(io.BytesIO(src) if isinstance(src, bytes) else src)
    return ImageOps.exif_transpose(img).convert("RGB")


@torch.no_grad()
def embed(images: list[Image.Image], ckpt: str | None = None, batch: int = 16) -> np.ndarray:
    """이미지 -> L2 정규화된 임베딩 (내적 = 코사인)."""
    model, preprocess = _clip(ckpt)
    out = []
    for i in range(0, len(images), batch):
        x = torch.stack([preprocess(im) for im in images[i : i + batch]])
        f = model.encode_image(x)
        out.append(torch.nn.functional.normalize(f, dim=-1).numpy())
    return np.concatenate(out).astype("float32")


def search(index, ids: list[str], vec: np.ndarray) -> list[tuple[str, float]]:
    """유물별 최고 유사도 내림차순. 한 유물의 gallery 이미지가 여러 장이라 max로 합친다."""
    sims, idx = index.search(vec, index.ntotal)
    best: dict[str, float] = {}
    for s, i in zip(sims[0], idx[0]):
        best.setdefault(ids[i], float(s))
    return sorted(best.items(), key=lambda kv: -kv[1])


def judge(ranked: list[tuple[str, float]], T: float, M: float) -> str:
    top = ranked[0][1]
    gap = top - ranked[1][1] if len(ranked) > 1 else top
    if top < T:
        return "reject"
    return "ok" if gap >= M else "uncertain"


@lru_cache(maxsize=1)
def _stage():
    index = faiss.read_index(str(MODELS / f"index_stage{STAGE}.faiss"))
    ids = json.loads((MODELS / f"index_stage{STAGE}_ids.json").read_text(encoding="utf-8"))
    th_path = MODELS / f"thresholds_stage{STAGE}.json"
    th = json.loads(th_path.read_text()) if th_path.exists() else {}
    return index, ids, th.get("T", 0.0), th.get("M", 0.0)


def _name(artifact_id: str) -> str | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT name FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return row[0] if row else None


def recognize(image_bytes: bytes) -> dict:
    index, ids, T, M = _stage()
    ranked = search(index, ids, embed([load_image(image_bytes)], ckpt=_ckpt()))
    status = judge(ranked, T, M)
    top_id, score = ranked[0]
    if status == "reject":
        return {"status": status, "score": score, "message": MESSAGES["reject"]}
    return {
        "status": status,
        "artifact_id": top_id,
        "name": _name(top_id),
        "score": score,
        "message": MESSAGES.get(status),
    }


def _ckpt() -> str | None:
    p = MODELS / f"ckpt_stage{STAGE}.pt"
    return str(p) if p.exists() else None
