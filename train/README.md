# train/

Colab T4 노트북과 학습 스크립트. 단계마다 달라지는 건 학습 방법 하나뿐이어야 한다.

- ① 베이스라인: 학습 없음 -> `index_stage1.faiss`
- ② 파인튜닝: K-Art train, 마지막 블록 2~4개 + projection만 -> `ckpt_stage2.pt`
- ③ + 증강: ②와 같은 train + albumentations -> `ckpt_stage3.pt`

`data/test/`를 읽는 코드는 넣지 않는다.
