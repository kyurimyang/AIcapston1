# models/

git에 올리지 않는다 (이 README와 `.gitkeep`만 예외). 백엔드를 다른 컴퓨터에서 돌리려면 팀 공유 드라이브에서 받아 이 폴더에 둔다.

## 시연(②)에 필요한 파일

| 파일 | 크기 | 없으면 |
|---|---|---|
| `ckpt_stage2.pt` | 약 570MB | 파인튜닝 전 모델(①)로 돌아가 결과가 달라진다 |
| `index_stage2.faiss`, `index_stage2_ids.json` | 약 300KB | `/recognize`가 시작 때 실패한다. gallery가 있으면 `python backend/scripts/build_index.py 2`로 다시 만든다 |
| `thresholds_stage2_crop.json` | 작음 | 다중 크롭 기준 T·M. 없으면 원본 기준 `thresholds_stage2.json`을 쓰는데 크롭은 점수가 높게 나와 판정이 어긋난다 |

③④ 파일(`*_stage3*`, `*_stage4*`)과 `ckpt_stage2_rerun.pt`는 학습 비교용이라 시연에는 필요 없다.

## 같이 필요한 것

- `data/artifacts.db` — 유물 이름·해설(검수 완료분)·RAG 근거. `data/README.md` 참고. 해설은 이 DB에 들어 있어서 코드만으로는 복원되지 않는다.
- `.env` — `.env.example`을 복사해 `LLM_API_KEY`, `LLM_PROVIDER`를 채운다. 없으면 `/ask`만 동작하지 않는다.
- `STAGE`는 기본 2다. `.env`에서 바꾸면 다른 모델이 돌아간다.
- 첫 실행 때 CLIP 사전학습 가중치를 HuggingFace에서 내려받는다 (인터넷 필요).

## 같은 결과가 나오는지 확인

```
python eval/evaluate_multicrop.py 2
```

받은 파일이 맞으면 ② 다중 크롭 결과가 `eval/results_stage_comparison.md`의 값과 같아야 한다.
