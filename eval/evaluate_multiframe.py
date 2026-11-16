"""test 영상으로 '프레임 1장' vs '연속 4장 평균' 비교. 결과만 보고하고, 임계값 튜닝에는 쓰지 않는다.

실행 (레포 루트에서): python eval/evaluate_multiframe.py [단계=2]

- 영상 3개(A / B / A&B 동시)는 test로만 쓴다. 학습·gallery·임계값에 쓰지 않는다.
- 0.5초마다 창을 열고, 창마다 0.3초 간격 4장을 뽑는다 (앱의 연속 촬영과 같은 설정).
- 같은 4장으로 두 방식을 비교한다.
    단일: 4장을 각각 따로 판단한 결과를 모두 센다
    평균: 4장 임베딩을 평균해 한 번에 판단한다 (backend recognize_many와 같은 방식)
- T·M은 models/thresholds_stage{N}.json 그대로. 정답은 A/B는 해당 유물, AB는 A 또는 B.
- '확신 오답' = status가 ok인데 1위가 틀린 경우 (서비스에서 가장 나쁜 실패).
"""
import io
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import faiss
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import MODELS, ROOT, embed, judge, search  # noqa: E402

VIDEOS = [("A", "A/A영상.mp4"), ("B", "B/B영상.mp4"), ("AB", "AB/A&B 영상.mp4")]
LABEL_IDS = {"A": {"A01"}, "B": {"B01"}, "AB": {"A01", "B01"}}
N, GAP_S, STEP_S, MAX_SIDE = 4, 0.3, 0.5, 768


def to_upload_like(frame_bgr) -> Image.Image:
    """앱처럼 긴 변 768px JPEG(품질 0.85)로 줄였다 다시 연다."""
    im = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    s = min(1, MAX_SIDE / max(im.size))
    im = im.resize((round(im.width * s), round(im.height * s)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def windows(path: Path):
    cap = cv2.VideoCapture(str(path))
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    gap, step = round(GAP_S * fps), round(STEP_S * fps)
    for start in range(0, total - gap * (N - 1), step):
        frames = []
        for k in range(N):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start + k * gap)
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(to_upload_like(fr))
        if len(frames) == N:
            yield frames


def main(stage: int) -> None:
    index = faiss.read_index(str(MODELS / f"index_stage{stage}.faiss"))
    ids = json.loads((MODELS / f"index_stage{stage}_ids.json").read_text(encoding="utf-8"))
    th = json.loads((MODELS / f"thresholds_stage{stage}.json").read_text())
    T, M = th["T"], th["M"]
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    ckpt = str(ckpt) if ckpt.exists() else None

    def decide(vec):
        ranked = search(index, ids, vec)
        return judge(ranked, T, M), ranked[0][0]

    print(f"== stage{stage} (T={T}, M={M}) · 창마다 {N}장, {GAP_S}초 간격, {STEP_S}초마다 ==")
    total = {"단일": Counter(), "평균": Counter()}
    for label, rel in VIDEOS:
        per = {"단일": Counter(), "평균": Counter()}
        for frames in windows(ROOT / "data" / "test" / rel):
            vecs = embed(frames, ckpt=ckpt)
            mean = vecs.mean(axis=0, keepdims=True)
            mean /= np.linalg.norm(mean, axis=1, keepdims=True)
            cases = {"단일": [decide(v[None]) for v in vecs], "평균": [decide(mean.astype("float32"))]}
            for name, outs in cases.items():
                for status, top in outs:
                    right = top in LABEL_IDS[label]
                    per[name]["n"] += 1
                    per[name][f"status_{status}"] += 1
                    per[name]["top1_ok"] += right
                    per[name]["확신오답"] += status == "ok" and not right
        for name in per:
            total[name].update(per[name])
        print(f"\n[{label}] 창 {per['평균']['n']}개")
        report(per)
    print("\n[전체]")
    report(total)


def report(c: dict) -> None:
    print(f"{'방식':<4}{'판단수':>7}{'Top-1':>8}{'ok':>7}{'uncertain':>11}{'reject':>8}{'확신 오답':>10}")
    for name in ("단일", "평균"):
        r = c[name]
        n = r["n"]
        print(f"{name:<4}{n:>7}{r['top1_ok'] / n:>8.1%}{r['status_ok'] / n:>7.1%}"
              f"{r['status_uncertain'] / n:>11.1%}{r['status_reject'] / n:>8.1%}{r['확신오답'] / n:>10.1%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
