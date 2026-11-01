# data/

git에 올리지 않는다 (이 README만 예외). 팀 공유 드라이브에서 받아 아래 구조로 둔다.

```
data/
├── artifacts.db        # artifacts, artifact_images, narrations, test_images
├── gallery/            # FAISS 기준 이미지 (유물당 3~10장)
├── train/  val/        # K-Art, 유물 ID 기준 split
├── none_val/           # 유물 없는 사진 (임계값용)
└── test/{A,B,none}/    # 사유의 방 촬영본 + test_images.csv (최종 평가 전용)
```

- test는 학습·임계값·gallery에 쓰지 않는다.
- 다른 관람객 얼굴이 나온 사진은 공유 전에 제외한다.
