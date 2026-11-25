"""새 유물 1점을 gallery에 추가한다 (코드 수정 없이 유물을 늘리기 위한 스크립트).

실행 (레포 루트에서):
  python backend/scripts/add_artifact.py --id C21 --name "..." --images <폴더> --license "..." [--meta meta.json] [--stage 2] [--dry-run]

하는 일
  1. 검사: license 필수, id 중복 불가, 이미지는 열 수 있어야 한다 (gallery는 3~10장 권장)
  2. models/의 인덱스·ids·임계값 파일을 .bak으로 백업
  3. 이미지를 data/gallery/<id>/로 복사하고 artifacts·artifact_images에 등록
  4. build_index.py로 인덱스를 다시 만들고, pick_thresholds.py 방식(val + none_val, 다중 크롭)으로 T·M을 다시 정한다
  5. 닮은 유물 경고: 새 유물 gallery를 leave-one-out으로 검색해 다른 유물이 1위이거나 1·2위 간격이 M보다 작은 비율
--dry-run은 파일·DB·인덱스를 건드리지 않고 5번 경고만 (현재 인덱스 + 새 이미지를 메모리에서 합쳐) 출력한다.

--meta는 JSON: {"era": "", "material": "", "size": "", "description": "", "source_url": ""}  (확인한 값만 넣는다)
data/test는 읽지 않는다. 학습(ckpt)은 바꾸지 않는다.
"""
import argparse
import json
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "eval"), str(HERE.parent)]
import build_index  # noqa: E402
import pick_thresholds  # noqa: E402
from app.recognize import CROP_SCALES, DB_PATH, MODELS, ROOT, STAGE, center_crop, embed, load_image, rank_embeddings  # noqa: E402

DATA = ROOT / "data"
NARRATIONS = HERE / "narrations.json"
EXTS = {".jpg", ".jpeg", ".png"}


def fail(msg: str) -> None:
    print(f"[중단] {msg}")
    sys.exit(1)


def model_files(stage: int) -> list[Path]:
    return [MODELS / f"index_stage{stage}.faiss", MODELS / f"index_stage{stage}_ids.json",
            MODELS / f"thresholds_stage{stage}_crop.json"]


def crop_embed(images, ckpt) -> np.ndarray:
    E = embed([center_crop(im, s) for im in images for s in CROP_SCALES], ckpt=ckpt)
    return E.reshape(len(images), len(CROP_SCALES), -1)


def similarity_report(new_id: str, new_crops: np.ndarray, G: np.ndarray, ids: np.ndarray, M: float, names: dict) -> None:
    """새 유물의 gallery 이미지를 하나씩 빼고(LOO) 검색해, 다른 유물과 헷갈릴 위험을 출력한다."""
    rows = np.where(ids == new_id)[0]
    if len(rows) < 2:
        print("[닮은 유물] 이미지가 1장이라 leave-one-out으로 확인할 수 없어요 (2장 이상 권장)")
        return
    wrong = small = 0
    rivals: list[tuple[str, float]] = []
    for q, r in enumerate(rows):
        keep = np.arange(len(ids)) != r
        ranked = rank_embeddings(new_crops[q], G[keep], ids[keep])
        wrong += ranked[0][0] != new_id
        small += (ranked[0][1] - ranked[1][1]) < M
        rivals.append(next(x for x in ranked if x[0] != new_id))
    n = len(rows)
    print(f"[닮은 유물] 새 유물 이미지 {n}장 leave-one-out (M={M:.4f})")
    print(f"  다른 유물이 1위: {wrong}/{n} ({wrong / n:.0%}) · 1·2위 간격 < M: {small}/{n} ({small / n:.0%})")
    top = Counter(a for a, _ in rivals).most_common()
    mean = {a: float(np.mean([s for b, s in rivals if b == a])) for a, _ in top}
    best = sorted(top, key=lambda kv: (-kv[1], -mean[kv[0]]))[0][0]
    print(f"  가장 헷갈리는 유물: {best} ({names.get(best, '?')}), 평균 유사도 {mean[best]:.3f}")
    if wrong or small:
        print("  -> 시연에서 uncertain(재촬영 안내)이 자주 나올 수 있어요. 이미지를 더 다양한 각도로 추가하는 것을 권장해요.")


def narration_notice(art_id: str) -> None:
    ok = False
    if NARRATIONS.exists():
        ok = any(n.get("artifact_id") == art_id and n.get("reviewed")
                 for n in json.loads(NARRATIONS.read_text(encoding="utf-8")))
    if not ok:
        print(f"[해설] {art_id}의 검수된 해설이 없어요. /narration은 404('검수된 해설이 없어요')를 반환합니다."
              f" 해설을 만들고 검수해 {NARRATIONS.relative_to(ROOT).as_posix()}에 reviewed=true로 넣어야 재생돼요.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--license", default="", help="공공누리 유형 등 (필수)")
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--source", default="직접 등록", help="artifact_images.source")
    ap.add_argument("--stage", type=int, default=STAGE, help="다시 만들 단계 (기본: 앱이 쓰는 STAGE)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.license.strip():
        fail("--license가 없어요. 라이선스를 모르는 이미지는 넣지 않습니다 (CLAUDE.md 4-2)")
    if not a.images.is_dir():
        fail(f"이미지 폴더가 없어요: {a.images}")
    srcs = sorted(p for p in a.images.iterdir() if p.suffix.lower() in EXTS)
    if not srcs:
        fail("jpg/png 이미지가 없어요")
    meta = json.loads(a.meta.read_text(encoding="utf-8")) if a.meta else {}
    dest = DATA / "gallery" / a.id
    with sqlite3.connect(DB_PATH) as con:
        if con.execute("SELECT 1 FROM artifacts WHERE id = ?", (a.id,)).fetchone():
            fail(f"이미 있는 유물 ID예요: {a.id}")
        names = dict(con.execute("SELECT id, name FROM artifacts").fetchall())
    if dest.exists():
        fail(f"{dest}가 이미 있어요")
    try:
        images = [load_image(p) for p in srcs]
    except Exception as e:  # noqa: BLE001
        fail(f"이미지를 열 수 없어요: {e}")
    if not 3 <= len(srcs) <= 10:
        print(f"[주의] gallery는 유물당 3~10장을 권장해요 (지금 {len(srcs)}장)")

    ckpt = MODELS / f"ckpt_stage{a.stage}.pt"
    ckpt = str(ckpt) if ckpt.exists() else None
    new_crops = crop_embed(images, ckpt)
    names[a.id] = a.name

    print(f"{'[dry-run] ' if a.dry_run else ''}유물 추가: {a.id} {a.name} · 이미지 {len(srcs)}장 · 라이선스 {a.license} · stage{a.stage}")

    import faiss

    if a.dry_run:
        index = faiss.read_index(str(MODELS / f"index_stage{a.stage}.faiss"))
        ids = np.array(json.loads((MODELS / f"index_stage{a.stage}_ids.json").read_text(encoding="utf-8")) + [a.id] * len(srcs))
        G = np.concatenate([index.reconstruct_n(0, index.ntotal), new_crops[:, 0]])
        th = json.loads((MODELS / f"thresholds_stage{a.stage}_crop.json").read_text())
        print("실제 실행하면:")
        print(f"  - {len(srcs)}장을 {dest.relative_to(ROOT).as_posix()}/{a.id}_NN.jpg로 복사, artifacts·artifact_images(split=gallery) 등록")
        print(f"  - models/ 백업(.bak): {', '.join(p.name for p in model_files(a.stage))}")
        print(f"  - build_index.py {a.stage}로 인덱스 재구축, pick_thresholds {a.stage} --crop --write로 T·M 재계산")
        print(f"  (dry-run이라 T·M은 재계산하지 않고 현재 값 T={th['T']}, M={th['M']}로 경고를 계산)")
        similarity_report(a.id, new_crops, G, ids, th["M"], names)
        narration_notice(a.id)
        print("[dry-run] 파일·DB·인덱스는 바뀌지 않았어요")
        return

    # ---- 실제 실행 ----
    for p in model_files(a.stage):
        if p.exists():
            shutil.copy2(p, p.with_name(p.name + ".bak"))
    print("백업:", ", ".join(p.name + ".bak" for p in model_files(a.stage)), "+ artifacts.db.bak")
    db_bak = DB_PATH.with_name(DB_PATH.name + ".bak")
    shutil.copy2(DB_PATH, db_bak)  # 실패하면 DB 파일을 바이트 그대로 되돌린다
    con = sqlite3.connect(DB_PATH)
    try:
        dest.mkdir(parents=True)
        paths = []
        for n, (src, im) in enumerate(zip(srcs, images), 1):
            out = dest / f"{a.id}_{n:02d}.jpg"
            if src.suffix.lower() in (".jpg", ".jpeg"):
                shutil.copy2(src, out)
            else:
                im.save(out, "JPEG", quality=95)
            paths.append(out.relative_to(DATA).as_posix())
        con.execute("INSERT INTO artifacts (id, name, era, material, size, description, source_url, license) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (a.id, a.name, meta.get("era"), meta.get("material"), meta.get("size"),
                     meta.get("description"), meta.get("source_url"), a.license))
        con.executemany("INSERT INTO artifact_images VALUES (?, ?, ?, 'gallery')", [(a.id, p, a.source) for p in paths])
        con.commit()
        build_index.main(a.stage)
        pick_thresholds.main(a.stage, write=True, crop=True)
    except Exception as e:  # noqa: BLE001
        print(f"[실패] {type(e).__name__}: {e} -> 되돌립니다")
        con.close()
        shutil.copy2(db_bak, DB_PATH)
        shutil.rmtree(dest, ignore_errors=True)
        for p in model_files(a.stage):
            bak = p.with_name(p.name + ".bak")
            if bak.exists():
                shutil.copy2(bak, p)
            elif p.exists():  # 원래 없던 파일(예: 새로 만든 임계값)은 지운다
                p.unlink()
        for b in [db_bak] + [p.with_name(p.name + ".bak") for p in model_files(a.stage)]:
            b.unlink(missing_ok=True)  # 복구 완료. 백업은 원본과 같으므로 지운다
        raise
    finally:
        con.close()

    index = faiss.read_index(str(MODELS / f"index_stage{a.stage}.faiss"))
    ids = np.array(json.loads((MODELS / f"index_stage{a.stage}_ids.json").read_text(encoding="utf-8")))
    M = json.loads((MODELS / f"thresholds_stage{a.stage}_crop.json").read_text())["M"]
    # 인덱스는 path 순서라 새 유물 행의 순서 = 파일명(_01, _02, ...) 순서 = new_crops 순서
    similarity_report(a.id, new_crops, index.reconstruct_n(0, index.ntotal), ids, M, names)
    narration_notice(a.id)
    print("서버를 다시 시작해야 새 인덱스가 적용돼요")


if __name__ == "__main__":
    main()
