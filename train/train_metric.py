"""② 파인튜닝 / ③ + 증강: CLIP 이미지 인코더의 마지막 블록 N개 + projection만 학습 (SupCon).

실행 예
  ②  python train/train_metric.py --stage 2 --manifest train/manifest.csv --data-root data
  ③  python train/train_metric.py --stage 3 --manifest train/manifest.csv --data-root data
- ②와 ③의 차이는 증강 하나뿐이다. 나머지 설정(시드, 에폭, lr, 배치)은 같게 둔다.
- manifest.csv의 split=train 행으로 학습하고, split=val 행으로 검색 정확도를 본다.
  data/test와 data/gallery는 읽지 않는다.
- 결과: models/ckpt_stage{N}.pt (전체 state_dict, backend/app/recognize.py가 그대로 읽는다)
- 헷갈리는 쌍(hard negative)은 --hard-pairs CSV(컬럼 a,b = 유물 ID)로 준다.
  이 쌍은 한 배치에 함께 들어가 서로 negative가 된다.

④ = ② 설정 그대로 + A/B gallery 사진을 학습에 추가 + A01↔B01 hard negative (2026-11-16)
  python train/train_metric.py --stage 4 --manifest train/manifest.csv --data-root data \
      --gallery-ids A01,B01 --hard-pairs train/hard_pairs_ab.csv
- 원칙상 gallery는 학습에 쓰지 않지만, A·B는 K-Art train에 없어 두 상의 차이를 배울 사진이
  gallery뿐이다. --gallery-ids로 명시한 유물만 예외로 허용한다. test는 계속 금지.
- A·B는 val이 없으므로 설정을 val로 고를 수 없다. ②와 같은 설정으로 한 번만 학습한다.
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

MODEL_NAME = "ViT-B-16-quickgelu"
PRETRAINED = "openai"
GALLERY_PREFIXES = ("gallery", "test", "none_val")


def load_manifest(path: str, data_root: Path):
    by_split: dict[str, dict[str, list[Path]]] = {"train": defaultdict(list), "val": defaultdict(list)}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            p = Path(r["path"])
            if p.parts[0] in GALLERY_PREFIXES:
                raise ValueError(f"학습에 쓸 수 없는 경로: {r['path']}")
            if r["split"] in by_split:
                by_split[r["split"]][r["artifact_id"]].append(data_root / p)
    return by_split["train"], by_split["val"]


def load_gallery(ids: list[str], data_root: Path) -> dict[str, list[Path]]:
    """--gallery-ids로 명시한 유물의 gallery 사진만 읽는다 (④ 전용 예외)."""
    import sqlite3

    with sqlite3.connect(data_root / "artifacts.db") as con:
        rows = con.execute(
            f"SELECT artifact_id, path FROM artifact_images WHERE split='gallery' "
            f"AND artifact_id IN ({','.join('?' * len(ids))})", ids,
        ).fetchall()
    groups: dict[str, list[Path]] = defaultdict(list)
    for aid, p in rows:
        if not p.startswith("gallery/"):
            raise ValueError(f"gallery가 아닌 경로: {p}")
        groups[aid].append(data_root / p)
    missing = set(ids) - set(groups)
    if missing:
        raise ValueError(f"gallery 사진이 없는 유물: {sorted(missing)}")
    return groups


def build_augment():
    """③ 전용. 전시장 조건(조명, 흔들림, 가림, 각도)을 흉내 낸다."""
    import albumentations as A

    return A.Compose([
        A.RandomResizedCrop(size=(224, 224), scale=(0.5, 1.0), ratio=(0.8, 1.25), p=1.0),
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.7),
        A.RandomGamma(gamma_limit=(70, 140), p=0.5),
        A.RGBShift(r_shift_limit=20, g_shift_limit=10, b_shift_limit=20, p=0.4),  # 색온도
        A.MotionBlur(blur_limit=(3, 9), p=0.4),
        A.GaussNoise(std_range=(0.02, 0.1), p=0.4),
        A.Perspective(scale=(0.02, 0.08), p=0.4),
        A.CoarseDropout(num_holes_range=(1, 3), hole_height_range=(0.1, 0.3),
                        hole_width_range=(0.1, 0.3), p=0.4),
    ])


class BatchSampler:
    """배치 = 유물 P개 × 이미지 K장. 유물당 이미지가 K장보다 적으면 중복 허용."""

    def __init__(self, groups, P, K, steps, hard_pairs, seed):
        self.groups, self.P, self.K, self.steps = groups, P, K, steps
        self.ids = sorted(groups)
        self.pairs = [(a, b) for a, b in hard_pairs if a in groups and b in groups]
        self.rng = random.Random(seed)

    def __iter__(self):
        for _ in range(self.steps):
            chosen: list[str] = []
            if self.pairs:  # 배치마다 헷갈리는 쌍 하나는 반드시 함께 넣는다
                chosen += list(self.rng.choice(self.pairs))
            rest = [i for i in self.ids if i not in chosen]
            self.rng.shuffle(rest)
            chosen += rest[: max(0, self.P - len(chosen))]
            batch = []
            for aid in chosen:
                paths = self.groups[aid]
                picks = self.rng.sample(paths, self.K) if len(paths) >= self.K else self.rng.choices(paths, k=self.K)
                batch += [(p, aid) for p in picks]
            yield batch


def supcon_loss(z: torch.Tensor, labels: torch.Tensor, temp: float = 0.1) -> torch.Tensor:
    sim = z @ z.T / temp
    n = z.size(0)
    self_mask = torch.eye(n, dtype=torch.bool, device=z.device)
    sim = sim.masked_fill(self_mask, -1e9)
    pos = (labels[:, None] == labels[None, :]) & ~self_mask
    log_prob = sim - torch.logsumexp(sim, dim=1, keepdim=True)
    n_pos = pos.sum(1).clamp(min=1)
    return -((log_prob * pos).sum(1) / n_pos).mean()


def set_trainable(model, n_blocks: int):
    for p in model.parameters():
        p.requires_grad = False
    v = model.visual
    params = []
    for blk in v.transformer.resblocks[-n_blocks:]:
        params += list(blk.parameters())
    params += list(v.ln_post.parameters()) + [v.proj]  # projection
    for p in params:
        p.requires_grad = True
    return params


def to_tensor(path: Path, preprocess, augment):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if augment is not None:
        img = Image.fromarray(augment(image=np.array(img))["image"])
    return preprocess(img)


@torch.no_grad()
def val_top1(model, preprocess, val, device) -> float:
    """val 안에서 이미지 하나를 질의로, 나머지를 gallery로 두고 (leave-one-out) Top-1을 본다."""
    model.eval()
    feats, labels = [], []
    for aid, paths in val.items():
        for p in paths:
            x = to_tensor(p, preprocess, None)[None].to(device)
            feats.append(F.normalize(model.encode_image(x), dim=-1).cpu())
            labels.append(aid)
    if len(set(labels)) < 2:
        return float("nan")
    f = torch.cat(feats)
    sim = f @ f.T
    sim.fill_diagonal_(-1)
    nn = sim.argmax(1)
    return float(np.mean([labels[i] == labels[j] for i, j in enumerate(nn.tolist())]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, choices=[2, 3, 4])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--out-dir", default="models")
    ap.add_argument("--hard-pairs", default=None)
    ap.add_argument("--gallery-ids", default=None, help="④ 전용: 학습에 넣을 gallery 유물 ID (쉼표 구분)")
    ap.add_argument("--blocks", type=int, default=4, help="마지막 몇 개 블록을 학습할지 (2~4)")
    ap.add_argument("--P", type=int, default=16)
    ap.add_argument("--K", type=int, default=4)
    ap.add_argument("--steps", type=int, default=300, help="에폭 대신 배치 수")
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--temp", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    train, val = load_manifest(a.manifest, Path(a.data_root))
    if a.gallery_ids:
        if a.stage != 4:
            raise ValueError("--gallery-ids는 --stage 4에서만 쓴다")
        extra = load_gallery(a.gallery_ids.split(","), Path(a.data_root))
        overlap = set(extra) & (set(train) | set(val))
        if overlap:
            raise ValueError(f"train/val과 겹치는 유물: {sorted(overlap)}")
        train.update(extra)
        print("gallery에서 추가: " + ", ".join(f"{k} {len(v)}장" for k, v in extra.items()))
    print(f"stage{a.stage} device={device} train 유물 {len(train)}점 / val 유물 {len(val)}점")

    pairs = []
    if a.hard_pairs:
        with open(a.hard_pairs, encoding="utf-8-sig", newline="") as f:
            pairs = [(r["a"], r["b"]) for r in csv.DictReader(f)]

    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    model.to(device)
    params = set_trainable(model, a.blocks)
    print(f"학습 파라미터 {sum(p.numel() for p in params) / 1e6:.1f}M (마지막 {a.blocks}블록 + projection)")
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.01)
    augment = build_augment() if a.stage == 3 else None

    print(f"val Top-1 (학습 전): {val_top1(model, preprocess, val, device):.3f}")
    sampler = BatchSampler(train, min(a.P, len(train)), a.K, a.steps, pairs, a.seed)
    model.train()
    for step, batch in enumerate(sampler, start=1):
        x = torch.stack([to_tensor(p, preprocess, augment) for p, _ in batch]).to(device)
        ids = sorted({aid for _, aid in batch})
        y = torch.tensor([ids.index(aid) for _, aid in batch], device=device)
        z = F.normalize(model.encode_image(x), dim=-1)
        loss = supcon_loss(z, y, a.temp)
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 20 == 0 or step == a.steps:
            print(f"step {step}/{a.steps} loss {loss.item():.4f}")

    print(f"val Top-1 (학습 후): {val_top1(model, preprocess, val, device):.3f}")
    out = Path(a.out_dir); out.mkdir(exist_ok=True)
    torch.save({k: v.cpu() for k, v in model.state_dict().items()}, out / f"ckpt_stage{a.stage}.pt")
    print(f"저장: {out / f'ckpt_stage{a.stage}.pt'}")


if __name__ == "__main__":
    main()
