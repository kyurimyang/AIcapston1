# 클래스 다이어그램 명세

다이어그램 원본: `class.puml` (렌더링: VS Code PlantUML 확장 또는 https://www.plantuml.com/plantuml)

> 백엔드(`recognize.py`, `rag.py`)와 프론트 유틸(`api.ts`, `speech.ts`, `image.ts`)은 클래스가 아니라 함수 모듈이다.
> 다이어그램에서는 책임 단위를 보여 주려고 `<<module>>` 스테레오타입을 붙인 클래스로 그렸다.

## 패키지 구성

| 패키지 | 담당 | 클래스 |
|---|---|---|
| frontend (React + Vite) | 혜진 | App, AppContext, Settings, 화면 4개(Onboarding·Capture·Narration·Ask), ApiClient, Speech, ImageUtil |
| backend (FastAPI) | 규림 | MainApp, Recognizer, RagAnswerer, DTO 4개 |
| data / models | 공통 | Artifact, ArtifactImage, Narration, TestImage, FaissIndex, Checkpoint, Thresholds |
| 외부 | — | CLIPModel(open_clip ViT-B/16), LLMService(openai·anthropic·gemini 중 하나) |

## 주요 클래스

### 프론트엔드
| 클래스 | 책임 | 파일 |
|---|---|---|
| App | 해시 라우팅, 저장된 프로필이 있으면 `/capture`로 바로 이동 | `frontend/src/App.tsx` |
| AppContext | 프로필 설정(localStorage `yudam.settings`), 마지막 인식 결과·촬영 사진을 화면 간에 공유 | `frontend/src/AppContext.tsx` |
| Settings | 시각 경험(Profile) + 해설 길이(Length) | 〃 |
| OnboardingPage | 프로필·해설 길이 선택 후 저장 | `pages/Onboarding.tsx` |
| CapturePage | 자동 인식·카메라 촬영·사진/영상 올리기 → 인식 요청, `uncertain`/`reject`이면 음성으로 재촬영 안내 | `pages/Capture.tsx` |
| NarrationPage | 검수된 해설을 받아 바로 재생, 다시 듣기·속도 조절 | `pages/Narration.tsx` |
| AskPage | 음성(또는 글) 질문 → 답변과 근거 표시·재생 | `pages/Ask.tsx` |
| ApiClient | 모든 API 호출. 타임아웃 5초, 실패 시 1회 재시도 (`/ask`는 15초, 재시도 없음) | `src/api.ts` |
| Speech | TTS(`speak`, 이전 음성 cancel) · STT(`listen`) · 속도 0.8/1.0/1.3 | `src/speech.ts` |
| ImageUtil | 전송 전 긴 변 768px JPEG로 축소 | `src/image.ts` |

### 백엔드
| 클래스 | 책임 | 파일 |
|---|---|---|
| MainApp | `/health`, `/recognize`, `/narration`, `/ask` 엔드포인트. 시작 시 모델 warmup | `backend/app/main.py` |
| Recognizer | CLIP 임베딩(원본 + 중앙 60%·40% 크롭) → FAISS 검색 → 유물별 최고 점수 → T·M으로 ok/uncertain/reject 판정 | `backend/app/recognize.py` |
| RagAnswerer | 유물 설명을 문단 번호와 함께 프롬프트에 넣고 LLM 호출, 근거 문단이 없으면 "자료에 없는 내용이에요" | `backend/app/rag.py` |
| RecognizeResult · NarrationResponse · AskRequest · AskResponse | API 요청·응답 형식 (CLAUDE.md 6장) | `main.py`, `api.ts` |

### 데이터·모델
| 클래스 | 저장 위치 | 비고 |
|---|---|---|
| Artifact | `data/artifacts.db` `artifacts` | 해설·RAG의 유일한 근거 |
| ArtifactImage | `artifact_images` | split = train / val / gallery |
| Narration | `backend/scripts/narrations.json` | 유물당 3프로필 × 2길이, `reviewed=true`만 응답 |
| TestImage | `test_images` | 평가 전용. 학습·임계값·인덱스와 관계 없음 (다이어그램에서도 연결하지 않음) |
| FaissIndex | `models/index_stageN.faiss` + `_ids.json` | gallery 이미지로만 구축 |
| Checkpoint | `models/ckpt_stageN.pt` | ②③만 있음, ①은 사전학습 그대로 |
| Thresholds | `models/thresholds_stageN_crop.json` | T·M, val로만 결정 |

## 관계 요약
- **합성**: App ◆— 화면 4개, AppContext ◆— Settings, Artifact ◆— ArtifactImage / Narration
- **의존**: 화면 → AppContext·ApiClient·Speech, ApiClient → MainApp (HTTPS, ngrok), MainApp → Recognizer·RagAnswerer
- **연관**: Recognizer → CLIPModel·FaissIndex·Checkpoint·Thresholds, RagAnswerer → LLMService
