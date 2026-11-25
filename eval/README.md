# eval/

단계별·조건별 정확도를 계산해 결과표를 만든다.
지표: Top-1 / Top-3, 오인식률, 조건별 정확도.

| 파일 | 하는 일 | 쓰는 데이터 |
|---|---|---|
| `pick_thresholds.py` | 임계값 T·M을 정해 `models/thresholds_stage{N}.json`에 저장 | gallery, val, none_val (**test 읽지 않음**) |
| `evaluate.py` | 정한 T·M으로 test 결과만 보고 (튜닝 금지) | test |
| `results_stage_comparison.md` | ①②③ 비교표 | — |

실행 (레포 루트에서, 단계 번호 = 1·2·3):

```
python eval/pick_thresholds.py 2 --write   # 1) val로 T·M 결정
python eval/evaluate.py 2                  # 2) test는 결과 보고에만
```

## 합성 검증셋 (test 없이 방법 비교용)

| 파일 | 하는 일 | 쓰는 데이터 |
|---|---|---|
| `make_synth_val.py` | gallery 사진을 배경 위에 작게(20~50%) 붙여 "불상이 작고 배경이 큰 사진"을 만든다 → `data/synth_val/` + `synth_val.csv` | gallery, val, (있으면) `data/synth_bg/` (**test·none_val 읽지 않음**) |
| `evaluate_synth.py` | 현재 방식(② + 다중 크롭 + max, 현재 T·M)으로 평가. 양성은 원본 gallery 사진과 pHash 중복본을 검색 대상에서 뺀다(leave-one-out) | synth_val, gallery |
| `results_synth_val.md` | 합성 검증셋 기준선 | — |
| `compare_agg_synth.py` | 집계 방식 5종을 합성셋 두 버전에서 비교. 방식별 T·M은 val+none_val로 메모리에서 다시 정함(models/ 안 씀). 선택 기준은 스크립트 맨 위 | synth_val, synth_val_cut, gallery, val, none_val |
| `results_agg_synth.md` | 집계 방식 비교 결과 | — |

```
python eval/make_synth_val.py      # 시드 0, 유물당 20장
python eval/make_synth_val.py --cutout   # GrabCut으로 배경 지운 버전 -> data/synth_val_cut/
python eval/evaluate_synth.py      # 두 버전 기준선
python eval/compare_agg_synth.py   # 집계 방식 비교
```

- `data/synth_bg/`(선택): 배경으로 쓸 사진(jpg·png)을 넣으면 절반 확률로 절차 생성 배경 대신 쓴다.
  **사유의 방이 아닌 곳에서 찍은 사진만 넣는다** (사유의 방 사진은 test 누수가 된다). 사람 얼굴이 나온 사진은 넣지 않는다.
- 새 방법은 이 검증셋으로 비교해 고르고, test는 고른 뒤 결과 보고에만 쓴다. 합성셋과 현장의 차이는 `results_synth_val.md` 주의 절 참고.
