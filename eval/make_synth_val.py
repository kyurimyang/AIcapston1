"""합성 검증셋 만들기: "불상이 작고 배경이 큰 사진"을 test 없이 흉내 낸다.

실행 (레포 루트에서): python eval/make_synth_val.py [--per-artifact 20] [--seed 0] [--cutout]
출력: data/synth_val/{pos,neg_bg,neg_val}/*.jpg + data/synth_val/synth_val.csv
      --cutout이면 data/synth_val_cut/ (같은 구조)
      --seed가 0이 아니면 폴더 이름 뒤에 _s{시드} (예: data/synth_val_s1/, data/synth_val_cut_s1/)

읽는 데이터
- 양성 원본: gallery 이미지 (artifact_images split='gallery', A01·B01 포함 22점)
- 음성 원본: K-Art val 유물 (split='val', gallery에 없는 유물만)
- 배경: 절차 생성(단색·그라데이션·노이즈 텍스처 + 조명 비네팅, 색은 무작위).
  data/synth_bg/ 폴더가 있으면 그 사진도 절반 확률로 쓴다 (사유의 방이 아닌 곳에서 찍은 사진만).
- data/test, data/none_val은 읽지 않는다. 배경 색·구성·크기 범위는 test 사진을 보고 정하지 않았다.

합성 규칙
- 캔버스: 최종 크기(긴 변 768px, 앱 업로드와 같음)로 바로 만든다. 세로 576x768 / 가로 768x576 반반.
- 크기: 붙이는 사진이 캔버스 안에서 차지하는 비율 s ~ U(0.20, 0.50).
  s = max(붙인 폭/캔버스 폭, 붙인 높이/캔버스 높이) (사진이 캔버스에 맞춰 들어가는 긴 쪽 기준).
- 위치: 캔버스 안에서 무작위. 가장자리는 짧은 변의 3~8% 폭으로 페더링(가우시안).
- 약한 원근 변형: 네 꼭짓점을 붙인 크기의 0~6%씩 무작위 이동.
- 사진 전체에: 밝기 x0.6~1.3, 감마 0.7~1.4, 색온도(R·B 채널 ±15%),
  모션 블러(절반 확률, 길이 3~15px, 각도 무작위), JPEG 품질 40~95.
- 시드 고정. 이미지마다 (시드, 종류, 번호)로 난수를 따로 만들어 다시 돌려도 같은 결과가 나온다.

--cutout (배경 제거 버전, data/synth_val_cut/)
- 붙이기 전에 GrabCut으로 사진의 스튜디오 배경을 지우고 불상만 남긴다 (양성 gallery, 음성 val 둘 다).
  사진 가장자리 4%를 배경으로 두고 긴 변 400px로 줄여 5회 반복, 가장 큰 덩어리만 남긴 뒤 원래 크기로 키운다.
- 남은 불상의 경계 상자(여백 2%)로 자른 뒤, 그 상자 크기가 s(20~50%)가 되게 붙인다.
- 가장자리는 마스크를 같은 폭(짧은 변의 3~8%)의 절반 시그마로 흐린다 (사각형처럼 안쪽으로 깎지는 않는다).
- 분할 결과가 경계 상자의 3% 미만이거나 95% 초과면 실패로 보고 사진 전체를 붙인다 (csv cutout=fail).
- 시드와 난수를 뽑는 순서는 기본 버전과 같다. 같은 번호의 질의는 같은 원본·배경·변형 값을 쓴다
  (붙이는 물체 크기가 달라져 정수 위치 x·y만 범위가 바뀐다).
"""
import argparse
import csv
import shutil
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import DB_PATH, ROOT, load_image  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "synth_val"
OUT_CUT = DATA / "synth_val_cut"
BG_DIR = DATA / "synth_bg"
FORBIDDEN = ("test", "none_val")  # 이 폴더 아래 파일은 절대 읽지 않는다
LONG_SIDE = 768
SHORT_SIDE = 576
SCALE_RANGE = (0.20, 0.50)
FIELDS = ["path", "kind", "source_gallery_path", "source_val_path", "artifact_id", "scale", "size_bin",
          "x", "y", "obj_w", "obj_h", "canvas_w", "canvas_h", "bg_type", "bg_file", "feather",
          "persp", "brightness", "gamma", "temp", "blur_len", "blur_angle", "jpeg_q", "cutout"]


def _check_path(p: Path) -> Path:
    rel = Path(p).resolve().relative_to(DATA.resolve())
    if rel.parts and rel.parts[0] in FORBIDDEN:
        raise RuntimeError(f"{rel}은(는) 읽으면 안 되는 폴더예요 (test·none_val)")
    return p


def read_rgb(p: Path) -> np.ndarray:
    return np.asarray(load_image(_check_path(p)))


def size_bin(s: float) -> str:
    lo = min(int(s * 10) * 10, 40)
    return f"{lo}-{lo + 10}%"


# --- 배경 ------------------------------------------------------------------

def _rand_color(rng) -> np.ndarray:
    hsv = np.uint8([[[rng.integers(0, 180), rng.integers(0, 256), rng.integers(25, 231)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0].astype(np.float32)


def _noise_texture(rng, h, w) -> np.ndarray:
    """여러 크기의 부드러운 노이즈를 섞어 벽·천 같은 질감을 만든다. 0~1."""
    acc = np.zeros((h, w), np.float32)
    for cell, wt in ((4, 1.0), (16, 0.5), (64, 0.25)):
        small = rng.random((cell, cell), dtype=np.float32)
        acc += wt * cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    acc -= acc.min()
    return acc / max(acc.max(), 1e-6)


def procedural_bg(rng, h, w) -> tuple[np.ndarray, str]:
    kind = rng.choice(["solid", "gradient", "noise"])
    c1, c2 = _rand_color(rng), _rand_color(rng)
    if kind == "solid":
        img = np.broadcast_to(c1, (h, w, 3)).copy()
    elif kind == "gradient":
        ang = rng.uniform(0, 2 * np.pi)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        t = xx * np.cos(ang) + yy * np.sin(ang)
        t = (t - t.min()) / max(t.max() - t.min(), 1e-6)
        img = c1 * (1 - t[..., None]) + c2 * t[..., None]
    else:
        t = _noise_texture(rng, h, w)
        img = c1 * (1 - t[..., None]) + c2 * t[..., None]
    img += rng.normal(0, rng.uniform(0, 6), img.shape)  # 센서 노이즈
    return np.clip(img, 0, 255), str(kind)


def photo_bg(rng, files, h, w) -> tuple[np.ndarray, str]:
    p = files[rng.integers(len(files))]
    im = read_rgb(p).astype(np.float32)
    ih, iw = im.shape[:2]
    scale = max(h / ih, w / iw) * rng.uniform(1.0, 1.5)
    im = cv2.resize(im, (max(w, round(iw * scale)), max(h, round(ih * scale))), interpolation=cv2.INTER_AREA)
    y0 = rng.integers(0, im.shape[0] - h + 1)
    x0 = rng.integers(0, im.shape[1] - w + 1)
    return im[y0:y0 + h, x0:x0 + w].copy(), p.name


def vignette(rng, img: np.ndarray) -> np.ndarray:
    """조명이 한쪽에서 비추는 느낌: 무작위 중심의 방사형 밝기 감쇠."""
    h, w = img.shape[:2]
    cy, cx = rng.uniform(0.2, 0.8) * h, rng.uniform(0.2, 0.8) * w
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((yy - cy) / h) ** 2 + ((xx - cx) / w) ** 2)
    strength = rng.uniform(0.0, 0.7)
    return img * (1 - strength * np.clip(d / 0.8, 0, 1))[..., None]


def make_background(rng, h, w, bg_files) -> tuple[np.ndarray, str, str]:
    if bg_files and rng.random() < 0.5:
        img, name = photo_bg(rng, bg_files, h, w)
        kind = "photo"
    else:
        (img, kind), name = procedural_bg(rng, h, w), ""
    return vignette(rng, img), kind, name


# --- 배경 제거 (--cutout) ------------------------------------------------------

def cutout(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    """GrabCut으로 배경 제거 -> (경계 상자로 자른 사진, 같은 크기 마스크 0~1, 성공 여부). 난수를 쓰지 않는다."""
    H, W = rgb.shape[:2]
    k = 400 / max(H, W)
    small = cv2.resize(rgb, (max(1, round(W * k)), max(1, round(H * k))), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    mx, my = max(1, round(0.04 * w)), max(1, round(0.04 * h))
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(0)  # GrabCut 내부 k-means 초기화를 고정
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), mask, (mx, my, w - 2 * mx, h - 2 * my),
                bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        fg = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    frac = fg.sum() / max(1, (w - 2 * mx) * (h - 2 * my))
    if not 0.03 <= frac <= 0.95:
        return rgb, np.ones((H, W), np.float32), False
    full = (cv2.resize(fg.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) > 0.5).astype(np.float32)
    ys, xs = np.nonzero(full)
    pad = round(0.02 * max(H, W))
    y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
    return rgb[y0:y1, x0:x1], full[y0:y1, x0:x1], True


# --- 붙이기 · 변형 ----------------------------------------------------------

def paste(rng, canvas: np.ndarray, obj: np.ndarray, obj_mask: np.ndarray | None = None) -> dict:
    """obj를 캔버스의 s(20~50%) 크기로 줄여 무작위 위치에 페더링·원근 변형해 붙인다 (canvas를 고친다)."""
    H, W = canvas.shape[:2]
    s = rng.uniform(*SCALE_RANGE)
    oh, ow = obj.shape[:2]
    k = s / max(ow / W, oh / H)
    nw, nh = max(8, round(ow * k)), max(8, round(oh * k))
    small = cv2.resize(obj.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)

    feather = rng.uniform(0.03, 0.08)
    f = max(1.0, feather * min(nw, nh))
    if obj_mask is None:  # 사각형: 안쪽으로 f만큼 깎고 흐림
        alpha = np.zeros((nh, nw), np.float32)
        m = int(np.ceil(f))
        alpha[m:nh - m, m:nw - m] = 1.0
    else:  # 오려 낸 불상: 마스크 경계만 흐림
        alpha = cv2.resize(obj_mask, (nw, nh), interpolation=cv2.INTER_AREA)
    alpha = cv2.GaussianBlur(alpha, (0, 0), f / 2)

    x = int(rng.integers(0, W - nw + 1))
    y = int(rng.integers(0, H - nh + 1))
    persp = rng.uniform(0.0, 0.06)
    src = np.float32([[0, 0], [nw, 0], [nw, nh], [0, nh]])
    jitter = rng.uniform(-persp, persp, (4, 2)) * np.float32([nw, nh])
    dst = src + jitter + np.float32([x, y])
    Mx = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    warped = cv2.warpPerspective(small, Mx, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    a = cv2.warpPerspective(alpha, Mx, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]
    canvas[:] = canvas * (1 - a) + warped * a
    return dict(scale=round(s, 4), size_bin=size_bin(s), x=x, y=y, obj_w=nw, obj_h=nh,
                feather=round(feather, 4), persp=round(persp, 4))


def photometric(rng, img: np.ndarray) -> tuple[np.ndarray, dict]:
    b = rng.uniform(0.6, 1.3)
    g = rng.uniform(0.7, 1.4)
    t = rng.uniform(-0.15, 0.15)  # +: 따뜻하게(R↑ B↓), -: 차갑게
    x = np.clip(img * b, 0, 255) / 255.0
    x = x ** g * 255.0
    x[..., 0] *= 1 + t
    x[..., 2] *= 1 - t
    x = np.clip(x, 0, 255)
    blur_len, blur_angle = 0, 0.0
    if rng.random() < 0.5:
        blur_len = int(rng.integers(3, 16))
        blur_angle = float(rng.uniform(0, 180))
        ker = np.zeros((blur_len, blur_len), np.float32)
        ker[blur_len // 2, :] = 1.0
        R = cv2.getRotationMatrix2D(((blur_len - 1) / 2, (blur_len - 1) / 2), blur_angle, 1.0)
        ker = cv2.warpAffine(ker, R, (blur_len, blur_len))
        ker /= max(ker.sum(), 1e-6)
        x = cv2.filter2D(x.astype(np.float32), -1, ker)
    return x, dict(brightness=round(b, 4), gamma=round(g, 4), temp=round(t, 4),
                   blur_len=blur_len, blur_angle=round(blur_angle, 1))


def render(rng, obj: np.ndarray | None, bg_files, obj_mask: np.ndarray | None = None) -> tuple[bytes, dict]:
    W, H = (SHORT_SIDE, LONG_SIDE) if rng.random() < 0.5 else (LONG_SIDE, SHORT_SIDE)
    canvas, bg_type, bg_file = make_background(rng, H, W, bg_files)
    info = dict(canvas_w=W, canvas_h=H, bg_type=bg_type, bg_file=bg_file)
    info.update({k: "" for k in ("scale", "size_bin", "x", "y", "obj_w", "obj_h", "feather", "persp")})
    if obj is not None:
        info.update(paste(rng, canvas, obj, obj_mask))
    img, ph = photometric(rng, canvas)
    info.update(ph)
    q = int(rng.integers(40, 96))
    info["jpeg_q"] = q
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, q])
    assert ok
    return buf.tobytes(), info


def rng_for(seed: int, kind: str, i: int) -> np.random.Generator:
    tag = {"pos": 1, "neg_bg": 2, "neg_val": 3}[kind]
    return np.random.default_rng([seed, tag, i])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-artifact", type=int, default=20)
    ap.add_argument("--n-bg", type=int, default=100, help="배경만 있는 음성 수")
    ap.add_argument("--n-val", type=int, default=140, help="val 유물을 붙인 음성 수")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cutout", action="store_true", help="GrabCut으로 배경을 지운 불상만 붙인다 -> data/synth_val_cut/")
    args = ap.parse_args()
    out = OUT_CUT if args.cutout else OUT
    if args.seed != 0:  # 시드 0은 기존 경로, 다른 시드는 _s{시드}를 붙인다
        out = out.with_name(f"{out.name}_s{args.seed}")

    with sqlite3.connect(DB_PATH) as con:
        gal = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='gallery' "
                          "ORDER BY artifact_id, path").fetchall()
        val = con.execute("SELECT artifact_id, path FROM artifact_images WHERE split='val' "
                          "ORDER BY artifact_id, path").fetchall()
    g_ids = {a for a, _ in gal}
    val = [(a, p) for a, p in val if a not in g_ids]  # gallery에 추가된 val 유물은 음성이 아니다
    by_art: dict[str, list[str]] = {}
    for a, p in gal:
        by_art.setdefault(a, []).append(p)

    bg_files = sorted(p for p in BG_DIR.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")) \
        if BG_DIR.is_dir() else []
    print(f"gallery {len(gal)}장/{len(by_art)}점, val 음성 원본 {len(val)}장, 배경 사진 {len(bg_files)}장")

    if out.exists():
        shutil.rmtree(out)  # 합성 결과만 지운다 (원본 데이터 아님)
    for d in ("pos", "neg_bg", "neg_val"):
        (out / d).mkdir(parents=True)

    # 원본이 고해상도(약 3000x2000)라 전부 들고 있으면 메모리가 모자란다. 최근 CACHE_MAX장만 둔다.
    # 원본은 유물 순서대로 연속해서 쓰이므로 결과는 전부 캐시할 때와 같다 (처리가 결정적).
    CACHE_MAX = 24
    cache: dict[str, tuple] = {}
    status: dict[str, str] = {}  # 경로 -> cutout 상태 (실패 보고용, 캐시에서 빠져도 남김)

    def obj_of(p: str) -> tuple[np.ndarray, np.ndarray | None, str]:
        """(사진, 마스크 또는 None, cutout 상태)"""
        if p in cache:
            cache[p] = cache.pop(p)  # 최근 사용으로 옮김
            return cache[p]
        rgb = read_rgb(DATA / p)
        if args.cutout:
            crop, mask, ok = cutout(rgb)
            item = (crop, mask if ok else None, "ok" if ok else "fail")
        else:
            item = (rgb, None, "")
        cache[p] = item
        status[p] = item[2]
        if len(cache) > CACHE_MAX:
            cache.pop(next(iter(cache)))
        return item

    rows = []

    def emit(kind, i, obj_path, aid, src_g="", src_v=""):
        rng = rng_for(args.seed, kind, i)
        obj, mask, cut = obj_of(obj_path) if obj_path else (None, None, "")
        data, info = render(rng, obj, bg_files, mask)
        rel = f"{kind}/{kind}_{i:04d}.jpg"
        (out / rel).write_bytes(data)
        rows.append(dict(path=rel, kind=kind, source_gallery_path=src_g, source_val_path=src_v,
                         artifact_id=aid, cutout=cut, **info))

    i = 0
    for a, paths in by_art.items():
        for j in range(args.per_artifact):
            p = paths[j % len(paths)]  # 유물의 gallery 사진을 돌아가며 쓴다
            emit("pos", i, p, a, src_g=p)
            i += 1
    for i in range(args.n_bg):
        emit("neg_bg", i, None, "none")
    for i in range(args.n_val):
        a, p = val[i % len(val)]
        emit("neg_val", i, p, "none", src_v=p)

    with open(out / "synth_val.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    if args.cutout:
        fails = sorted(p for p, c in status.items() if c == "fail")
        print(f"배경 제거 실패 {len(fails)}/{len(status)}장 (사진 전체를 붙임):", *fails, sep=chr(10) + "  ")
    print(f"저장: {out} (양성 {sum(r['kind'] == 'pos' for r in rows)}, "
          f"배경 음성 {args.n_bg}, val 음성 {args.n_val})")


if __name__ == "__main__":
    main()
