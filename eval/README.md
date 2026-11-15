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
