"""인식 로직·업로드 검증 테스트. 모델·인덱스를 띄우지 않는다 (실행: pytest backend/tests).

pytest, httpx가 필요하다: pip install pytest httpx
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import recognize  # noqa: E402
from app.main import app  # noqa: E402

# lifespan(warmup)을 돌리지 않도록 with 없이 쓴다
client = TestClient(app)


def _jpeg(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


# --- judge ---------------------------------------------------------------

def test_judge_ok():
    assert recognize.judge([("A01", 0.8), ("B01", 0.6)], T=0.4, M=0.05) == "ok"


def test_judge_uncertain_when_gap_small():
    assert recognize.judge([("A01", 0.8), ("B01", 0.79)], T=0.4, M=0.05) == "uncertain"


def test_judge_reject_below_T():
    assert recognize.judge([("A01", 0.3), ("B01", 0.1)], T=0.4, M=0.05) == "reject"


def test_judge_boundaries_are_inclusive_for_ok():
    assert recognize.judge([("A01", 0.4), ("B01", 0.35)], T=0.4, M=0.05) == "ok"


def test_judge_single_artifact():
    assert recognize.judge([("A01", 0.9)], T=0.4, M=0.05) == "ok"


# --- merge ---------------------------------------------------------------

def test_merge_takes_max_per_artifact_and_sorts():
    merged = recognize.merge([
        [("A01", 0.5), ("B01", 0.4)],
        [("B01", 0.7), ("A01", 0.3)],
    ])
    assert merged == [("B01", 0.7), ("A01", 0.5)]


# --- 업로드 검증 ----------------------------------------------------------

def test_load_upload_empty():
    with pytest.raises(recognize.BadImage):
        recognize.load_upload(b"")


def test_load_upload_broken():
    with pytest.raises(recognize.BadImage):
        recognize.load_upload(b"not an image")


def test_load_upload_too_big(monkeypatch):
    monkeypatch.setattr(recognize, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(recognize.BadImage):
        recognize.load_upload(b"x" * 11)


def test_load_upload_downsizes_long_side():
    im = recognize.load_upload(_jpeg((3200, 1600)))
    assert max(im.size) == recognize.MAX_SIDE


def test_load_upload_keeps_small_image():
    assert recognize.load_upload(_jpeg((64, 48))).size == (64, 48)


# --- HTTP ----------------------------------------------------------------

def test_recognize_empty_file_is_400():
    r = client.post("/recognize", files={"image": ("a.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_recognize_broken_image_is_400():
    r = client.post("/recognize", files={"image": ("a.jpg", b"garbage", "image/jpeg")})
    assert r.status_code == 400


def test_recognize_ok_response_shape(monkeypatch):
    """모델 없이 recognize 내부를 가짜로 바꿔 응답 필드(API 형식)가 유지되는지 본다."""
    monkeypatch.setattr(recognize, "_stage", lambda: (None, [], 0.4, 0.05))
    monkeypatch.setattr(recognize, "_ckpt", lambda: None)
    monkeypatch.setattr(recognize, "rank_multicrop", lambda *a, **k: [("A01", 0.9), ("B01", 0.5)])
    monkeypatch.setattr(recognize, "_name", lambda i: "금동 반가사유상")
    r = client.post("/recognize", files={"image": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "artifact_id": "A01", "name": "금동 반가사유상",
                        "score": 0.9, "message": None}


def test_recognize_reject_response_shape(monkeypatch):
    monkeypatch.setattr(recognize, "_stage", lambda: (None, [], 0.4, 0.05))
    monkeypatch.setattr(recognize, "_ckpt", lambda: None)
    monkeypatch.setattr(recognize, "rank_multicrop", lambda *a, **k: [("A01", 0.2), ("B01", 0.1)])
    r = client.post("/recognize", files={"image": ("a.jpg", _jpeg(), "image/jpeg")})
    body = r.json()
    assert body["status"] == "reject" and body["artifact_id"] is None


# --- 유물 점수 집계 (rank_embeddings) ---------------------------------------

def _toy():
    import numpy as np
    # 2차원 단위벡터. A는 3장, B는 1장
    G = np.array([[1, 0], [0.8, 0.6], [0, 1], [0.6, 0.8]], dtype="float32")
    ids = ["A", "A", "A", "B"]
    V = np.array([[1, 0]], dtype="float32")
    return V, G, ids


def test_rank_max_matches_search_plus_merge():
    import numpy as np
    V, G, ids = _toy()
    r = recognize.rank_embeddings(V, G, ids, "max")
    assert r[0][0] == "A" and abs(r[0][1] - 1.0) < 1e-6
    assert abs(dict(r)["B"] - 0.6) < 1e-6


def test_rank_top3_averages_available_images():
    V, G, ids = _toy()
    d = dict(recognize.rank_embeddings(V, G, ids, "top3"))
    assert abs(d["A"] - (1.0 + 0.8 + 0.0) / 3) < 1e-6
    assert abs(d["B"] - 0.6) < 1e-6  # 1장뿐이면 있는 만큼


def test_rank_proto_is_cosine_to_mean():
    import numpy as np
    V, G, ids = _toy()
    d = dict(recognize.rank_embeddings(V, G, ids, "proto"))
    p = G[:3].mean(0)
    assert abs(d["A"] - float(V[0] @ (p / np.linalg.norm(p)))) < 1e-6


def test_rank_takes_max_over_crops():
    import numpy as np
    V, G, ids = _toy()
    V2 = np.vstack([V, np.array([[0, 1]], dtype="float32")])  # 두 번째 크롭은 B에 가까움
    d = dict(recognize.rank_embeddings(V2, G, ids, "max"))
    assert abs(d["B"] - 0.8) < 1e-6


def test_unknown_agg_raises():
    V, G, ids = _toy()
    with pytest.raises(ValueError):
        recognize.rank_embeddings(V, G, ids, "nope")
