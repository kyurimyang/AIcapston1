# data/

git에 올리지 않는다 (이 README만 예외). 팀 공유 드라이브에서 받아 아래 구조로 둔다.

```
data/
├── artifacts.db        # artifacts, artifact_images, narrations, test_images
├── gallery/            # FAISS 기준 이미지 (유물당 3~10장)
├── train/  val/        # K-Art, 유물 ID 기준 split
├── none_val/           # 유물 없는 사진 (임계값용)
└── test/{A,B,AB,none}/ # 사유의 방 촬영본 + test_images.csv (최종 평가 전용)
```

test 라벨: `A`, `B`, `AB`(두 유물이 한 화면에 같이 찍힌 사진, 동시 촬영 처리 확인용), `none`(유물 없음).

| 라벨 | 국보 | 정식 명칭 |
|---|---|---|
| A | 제78호 | 금동미륵보살반가사유상 |
| B | 제83호 | 금동미륵보살반가사유상 |

- 두 점의 이름이 같으므로 `artifacts.name`에는 호수를 붙인다 (예: "금동미륵보살반가사유상 (국보 제78호)").
- 두 점은 겉모습이 매우 비슷하다. e뮤지엄 gallery 이미지는 `source_url`로 국보 번호를 교차 확인한 뒤 넣는다.

- test는 학습·임계값·gallery에 쓰지 않는다.
- 다른 관람객 얼굴이 나온 사진은 공유 전에 제외한다.
