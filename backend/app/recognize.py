"""유물 인식 (CLIP + FAISS).

status 규칙 (임계값 T·M은 val로만 정한다)
- ok:        score >= T 이고 (1위 - 2위) >= M
- uncertain: score >= T 이지만 1·2위가 비슷함
- reject:    score < T

단계는 환경변수 STAGE(기본 2, 시연 모델)로 고른다: models/index_stage{N}.faiss
질의 사진은 원본 + 중앙 크롭(CROP_SCALES)으로 검색해 합친다 (rank_multicrop).
임계값은 models/thresholds_stage{N}_crop.json ({"T": ..., "M": ...}, val로 정함).
없으면 thresholds_stage{N}.json, 그것도 없으면 T=M=0이라 reject·uncertain이 나오지 않는다.
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
STAGE = int(os.getenv("STAGE", "2"))  # 시연 모델은 ② (eval/results_stage_comparison.md)
# 원본 + 중앙 60% + 중앙 40%. 비율은 test를 보기 전에 정했고 test로 바꾸지 않는다.
CROP_SCALES = (1.0, 0.6, 0.4)

MESSAGES = {
    # 화면을 못 봐도 따라 할 수 있게, 몸의 동작으로 안내한다
    "uncertain": "반가사유상 종류로 보여요. 한 걸음 앞으로 다가가 주세요. 폰을 두 손으로 가슴 높이에 잡고 다시 찍어 주세요",
    "reject": "유물을 찾지 못했어요. 유물 쪽으로 몸을 돌리고, 폰을 가슴 높이에 들고 다시 찍어 주세요",
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
    # 다중 크롭은 점수가 원본보다 높게 나오므로 크롭 기준으로 val에서 다시 정한 임계값을 쓴다
    th_path = MODELS / f"thresholds_stage{STAGE}_crop.json"
    if not th_path.exists():
        print(f"[경고] {th_path.name}이 없어 원본 1장 기준 임계값을 씁니다 (pick_thresholds.py --crop)")
        th_path = MODELS / f"thresholds_stage{STAGE}.json"
    th = json.loads(th_path.read_text()) if th_path.exists() else {}
    return index, ids, th.get("T", 0.0), th.get("M", 0.0)


def _name(artifact_id: str) -> str | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT name FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return row[0] if row else None


def center_crop(im: Image.Image, s: float) -> Image.Image:
    if s >= 1:
        return im
    w, h = im.size
    cw, ch = round(w * s), round(h * s)
    left, top = (w - cw) // 2, (h - ch) // 2
    return im.crop((left, top, left + cw, top + ch))


def merge(rankeds: list[list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """크롭별 검색 결과를 유물별 최고 점수로 합친다."""
    best: dict[str, float] = {}
    for ranked in rankeds:
        for a, s in ranked:
            best[a] = max(best.get(a, -1.0), s)
    return sorted(best.items(), key=lambda kv: -kv[1])


def rank_multicrop(index, ids: list[str], im: Image.Image, ckpt: str | None) -> list[tuple[str, float]]:
    """원본 + 중앙 크롭들을 각각 검색해 합친다 (추론 규칙, 학습 변경 아님).

    사유의 방 사진은 불상이 작고 A·B 공통 배경(벽·조명·받침대)이 커서, gallery(불상이 꽉 찬
    스튜디오 사진)와 비교할 때 두 상의 차이가 묻힌다. 중앙을 잘라 불상 비중을 키운다.
    """
    vecs = embed([center_crop(im, s) for s in CROP_SCALES], ckpt=ckpt)
    return merge([search(index, ids, v[None]) for v in vecs])


def recognize(image_bytes: bytes) -> dict:
    index, ids, T, M = _stage()
    ranked = rank_multicrop(index, ids, load_image(image_bytes), _ckpt())
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


def warmup() -> dict:
    """서버 시작 시 인덱스·CLIP·체크포인트를 미리 올리고 더미 이미지로 한 번 추론한다.

    첫 /recognize 요청이 모델 로딩까지 떠안으면 프론트 타임아웃(5초)을 넘길 수 있다.
    """
    index, ids, T, M = _stage()
    ckpt = _ckpt()
    if STAGE > 1 and ckpt is None:
        print(f"[경고] ckpt_stage{STAGE}.pt가 없어 사전학습 가중치로 임베딩합니다 (인덱스와 불일치)")
    if T == 0 and M == 0:
        print(f"[경고] thresholds_stage{STAGE}.json이 없어 reject·uncertain이 나오지 않습니다")
    embed([Image.new("RGB", (224, 224))], ckpt=ckpt)
    return {"stage": STAGE, "vectors": index.ntotal, "artifacts": len(set(ids)),
            "T": T, "M": M, "ckpt": ckpt is not None}
