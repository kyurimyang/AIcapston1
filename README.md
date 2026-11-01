# 유담 (YU:DAM)

전맹·저시력 관람객을 위한 맞춤형 AI 유물 도슨트. 유물을 찍으면 CLIP + FAISS로 인식하고, 시각 경험 프로필에 맞는 음성 해설을 들려준다.
AI융합캡스톤디자인1 (26-2) 6조 

## 구조

```
backend/    FastAPI (/health, /recognize, /narration, /ask)  — 규림
frontend/   React + Vite + TypeScript                         — 혜진
train/      Colab 노트북, 학습 스크립트 (① ② ③)
eval/       단계별·조건별 정확도 계산
data/       git 제외. 받는 방법은 data/README.md
models/     git 제외. 체크포인트·FAISS 인덱스
```

## 실행

```bash
cp .env.example .env     # 값을 채운다 (.env는 커밋 금지)

# 백엔드
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 프론트
cd frontend
npm install
npm run dev
```

시연: `ngrok http 8000` 후 나온 주소를 `frontend/.env`의 `VITE_API_BASE_URL`에 넣는다. 카메라는 HTTPS가 필요하다.

## 규칙

- test 데이터(`data/test/`)는 학습·임계값 튜닝·gallery에 쓰지 않는다.
- 다른 관람객 얼굴이 나온 사진, 대용량 이미지, 체크포인트, API 키는 커밋하지 않는다.
