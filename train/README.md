# train/

Colab T4 노트북과 학습 스크립트. 단계마다 달라지는 건 학습 방법 하나뿐이어야 한다.

- ① 베이스라인: 학습 없음 -> `index_stage1.faiss`
- ② 파인튜닝: K-Art train, 마지막 블록 2~4개 + projection만 -> `ckpt_stage2.pt`
- ③ + 증강: ②와 같은 train + albumentations -> `ckpt_stage3.pt`
- ④ ② + A/B hard negative: ②와 같은 설정 + A01·B01 gallery 54장 + A01↔B01 쌍 -> `ckpt_stage4.pt` (**채택 안 함**: test에서 ②보다 낮음, `eval/results_stage_comparison.md` 7절)

`data/test/`를 읽는 코드는 넣지 않는다.

④는 A01·B01에 한해 gallery를 학습에 쓰는 예외다 (`--gallery-ids`, `--stage 4`에서만 허용). Colab 실행은 `colab_train.ipynb`.
