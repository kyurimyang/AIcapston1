"""test 사진으로 '원본 1장' vs '중앙 다중 크롭' 비교. 결과만 보고하고, 크롭 비율·임계값 튜닝에는 쓰지 않는다.

실행 (레포 루트에서): python eval/evaluate_multicrop.py [단계=2]

가설 (gallery와 test를 눈으로 비교해서 세운 것):
  gallery는 불상이 화면을 꽉 채운 스튜디오 사진인데, 사유의 방 사진은 불상이 작고
  A·B 공통 배경(주황 벽, 천장 조명, 받침대)이 대부분이라 두 상의 차이가 임베딩에서 묻힌다.
방법:
  원본 + 중앙 60% + 중앙 40% 크롭을 각각 임베딩하고, 유물별로 가장 높은 점수를 쓴다.
  크롭 비율(SCALES)은 결과를 보기 전에 정했다. test를 보고 바꾸지 않는다.
  임계값은 방식마다 val로 따로 정한 것을 쓴다 (pick_thresholds.py, 다중 크롭은 --crop).
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import faiss

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.recognize import (  # noqa: E402
    CROP_SCALES as SCALES, MODELS, ROOT, center_crop, embed, judge, load_image, merge, search,
)

LABEL_TO_ID = {"A": "A01", "B": "B01"}


def main(stage: int) -> None:
    index = faiss.read_index(str(MODELS / f"index_stage{stage}.faiss"))
    ids = json.loads((MODELS / f"index_stage{stage}_ids.json").read_text(encoding="utf-8"))
    # 방식마다 val로 따로 정한 임계값을 쓴다 (원본: thresholds_stage{N}, 다중 크롭: _crop)
    th = {name: json.loads((MODELS / f"thresholds_stage{stage}{suf}.json").read_text())
          for name, suf in (("원본", ""), ("다중 크롭", "_crop"))}
    ckpt = MODELS / f"ckpt_stage{stage}.pt"
    ckpt = str(ckpt) if ckpt.exists() else None

    test_dir = ROOT / "data" / "test"
    with open(test_dir / "test_images.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    images = [load_image(test_dir / r["path"]) for r in rows]
    crops = [center_crop(im, s) for im in images for s in SCALES]
    vecs = embed(crops, ckpt=ckpt).reshape(len(rows), len(SCALES), -1)

    res = {"원본": defaultdict(list), "다중 크롭": defaultdict(list)}
    status = {"원본": defaultdict(int), "다중 크롭": defaultdict(int)}
    for r, v in zip(rows, vecs):
        rankeds = [search(index, ids, v[k][None]) for k in range(len(SCALES))]
        for name, ranked in (("원본", rankeds[0]), ("다중 크롭", merge(rankeds))):
            st = judge(ranked, th[name]["T"], th[name]["M"])
            top = ranked[0][0]
            label = r["label"]
            if label in LABEL_TO_ID:
                right = top == LABEL_TO_ID[label]
                for key in ("전체", r["condition"]):
                    res[name][key].append(right)
                status[name][st] += 1
                status[name]["확신오답"] += st == "ok" and not right
            elif label == "AB":
                res[name]["AB 동시"].append(top in LABEL_TO_ID.values())
            else:
                status[name]["none_오인식"] += st != "reject"
                status[name]["none_n"] += 1

    print(f"== stage{stage} · 크롭 {SCALES} · 임계값 {th} ==")
    keys = ["전체"] + sorted(k for k in res["원본"] if k not in ("전체", "AB 동시")) + ["AB 동시"]
    print(f"{'조건':<10}{'장수':>5}{'원본':>9}{'다중 크롭':>10}")
    for k in keys:
        n = len(res["원본"][k])
        print(f"{k:<10}{n:>5}{sum(res['원본'][k]) / n:>9.1%}{sum(res['다중 크롭'][k]) / n:>10.1%}")
    n_ab = len(res["원본"]["전체"])
    print()
    for name in ("원본", "다중 크롭"):
        s = status[name]
        print(f"[{name}] A/B {n_ab}장: ok {s['ok']} / uncertain {s['uncertain']} / reject {s['reject']}"
              f" · 확신 오답 {s['확신오답']}장 ({s['확신오답'] / n_ab:.1%})"
              f" · none 오인식 {s['none_오인식']}/{s['none_n']}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
