"""합성 검증셋 평가의 leave-one-out(누수 방지) 테스트. 모델·인덱스·데이터를 읽지 않는다.

실행: pytest backend/tests
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import evaluate_synth as es  # noqa: E402


def _unit(v):
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _img(seed, h=120, w=90):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (6, 5, 3)).astype(np.uint8)
    import cv2
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


# --- pHash 중복 판정 ------------------------------------------------------

def test_phash_same_photo_resized_is_duplicate():
    import cv2
    a = _img(0, 300, 200)
    b = cv2.resize(a, (100, 150), interpolation=cv2.INTER_AREA)  # 같은 사진, 해상도만 다름
    d = int((es.phash(a) != es.phash(b)).sum())
    assert d <= es.DUP_MAX_DIST


def test_phash_different_photos_are_not_duplicates():
    d = int((es.phash(_img(1)) != es.phash(_img(2))).sum())
    assert d > es.DUP_MAX_DIST


def test_find_duplicates_is_symmetric_and_excludes_self():
    H = np.array([[0] * 8, [0] * 7 + [1], [1] * 8], bool)
    dups = es.find_duplicates(["a", "b", "c"], H, max_dist=1)
    assert dups == {"a": {"b"}, "b": {"a"}, "c": set()}


# --- leave-one-out ------------------------------------------------------------

PATHS = ["g/A01/1.jpg", "g/A01/1_copy.jpg", "g/A01/2.jpg", "g/B01/1.jpg"]
IDS = ["A01", "A01", "A01", "B01"]
DUPS = {"g/A01/1.jpg": {"g/A01/1_copy.jpg"}, "g/A01/1_copy.jpg": {"g/A01/1.jpg"},
        "g/A01/2.jpg": set(), "g/B01/1.jpg": set()}


def test_mask_drops_source_and_its_duplicates():
    keep = es.loo_keep_mask(PATHS, "g/A01/1.jpg", DUPS)
    assert keep.tolist() == [False, False, True, True]


def test_mask_keeps_everything_for_negatives():
    assert es.loo_keep_mask(PATHS, None, DUPS).all()
    assert es.loo_keep_mask(PATHS, "", DUPS).all()


def test_mask_unknown_source_raises():
    with pytest.raises(KeyError):
        es.loo_keep_mask(PATHS, "g/A01/없는사진.jpg", DUPS)


def test_rank_ignores_source_even_if_it_is_the_best_match():
    # gallery: A01 원본(질의와 똑같음), A01 중복본(똑같음), A01 다른 사진, B01
    G = _unit([[1, 0, 0], [1, 0, 0], [0, 1, 0], [0.8, 0.6, 0]])
    V = _unit([[1, 0, 0]])  # 원본을 합성한 질의
    with_leak = es.rank_embeddings(V, G, IDS, "max")
    assert with_leak[0] == ("A01", pytest.approx(1.0))  # 빼지 않으면 원본이 1.0으로 1위
    ranked = es.rank_leave_one_out(V, G, IDS, PATHS, "g/A01/1.jpg", DUPS)
    assert ranked[0][0] == "B01"  # 원본·중복본을 빼면 남은 A01(0.0)보다 B01(0.8)이 위
    assert dict(ranked)["A01"] == pytest.approx(0.0)
    assert dict(ranked)["B01"] == pytest.approx(0.8)


def test_rank_artifact_disappears_when_all_its_images_are_excluded():
    paths, ids = ["g/C05/1.jpg", "g/A01/1.jpg"], ["C05", "A01"]
    dups = {p: set() for p in paths}
    G = _unit([[1, 0], [0, 1]])
    ranked = es.rank_leave_one_out(_unit([[1, 0]]), G, ids, paths, "g/C05/1.jpg", dups)
    assert [a for a, _ in ranked] == ["A01"]
