# 유담 (YU:DAM)

전맹·저시력 관람객을 위한 맞춤형 AI 유물 도슨트. 유물을 찍으면 CLIP + FAISS로 인식하고, 시각 경험 프로필에 맞는 음성 해설을 들려준다.
AI융합캡스톤디자인1 (26-2) 6조 

## 구조

```
backend/    FastAPI (/health, /recognize, /narration, /ask)  
frontend/   React + Vite + TypeScript                         
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

시연 (폰): 백엔드(8000)를 켜고, 프론트는 **빌드해서 `preview`로** 연 뒤, **`ngrok http 5173` 하나만** 연다. 폰 크롬에서 ngrok이 준 `https://…` 주소를 열면 된다.

```bash
# frontend/ 에서
npm run build
npm run preview -- --port 5173 --strictPort

# 다른 터미널에서
ngrok http 5173
```

- **`npm run dev`(개발 서버)는 ngrok으로 열지 않는다.** 링크를 아는 사람이 `data/`처럼 git에 없는 프로젝트 파일까지 받아 갈 수 있다. `preview`는 빌드한 화면만 보여 준다.
- `preview`는 빌드한 시점의 화면이다. 코드를 고치면 다시 빌드한다.
- 카메라는 HTTPS 페이지에서만 켜진다. 그래서 백엔드가 아니라 프론트를 ngrok으로 연다.
- API는 프론트 서버가 `/api` → `localhost:8000`으로 넘긴다 (`frontend/vite.config.ts`). ngrok 주소가 바뀌어도 설정을 고칠 필요가 없다.
- `frontend/.env`의 `VITE_API_BASE_URL`은 비워 둔다 (백엔드를 다른 곳에서 따로 열 때만 쓴다).

## 규칙

- test 데이터(`data/test/`)는 학습·임계값 튜닝·gallery에 쓰지 않는다.
- 다른 관람객 얼굴이 나온 사진, 대용량 이미지, 체크포인트, API 키는 커밋하지 않는다.
