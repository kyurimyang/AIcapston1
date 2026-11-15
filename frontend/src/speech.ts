// 음성 출력(TTS)과 음성 인식. 새 음성 전에 이전 음성을 cancel() 해서 겹치지 않게 한다.
const RATE_KEY = "yudam.rate";

export const RATES = [
  { value: 0.8, label: "느리게" },
  { value: 1.0, label: "보통" },
  { value: 1.3, label: "빠르게" },
] as const;

export function getRate(): number {
  return Number(localStorage.getItem(RATE_KEY)) || 1.0;
}

export function setRate(rate: number) {
  localStorage.setItem(RATE_KEY, String(rate));
}

/** 읽기가 끝나면(또는 취소·오류 시) resolve된다. 기다릴 필요가 없으면 결과를 무시하면 된다. */
export function speak(text: string): Promise<void> {
  speechSynthesis.cancel();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = getRate();
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

// ---------------- 음성 인식 (안드로이드 크롬: webkitSpeechRecognition) ----------------
interface Recognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export const canListen = () => recognitionCtor() !== undefined;

/** 한 문장을 듣고 텍스트로 돌려준다. 말이 끝나면(침묵) 자동으로 멈춘다. 못 알아들으면 빈 문자열. */
export function listen(): Promise<string> {
  const Ctor = recognitionCtor();
  if (!Ctor) return Promise.reject(new Error("음성 인식을 지원하지 않는 브라우저"));
  speechSynthesis.cancel(); // TTS 소리가 마이크로 들어가지 않게
  return new Promise((resolve, reject) => {
    const r = new Ctor();
    r.lang = "ko-KR";
    r.interimResults = false;
    r.maxAlternatives = 1;
    let text = "";
    r.onresult = (e) => { text = e.results[0]?.[0]?.transcript?.trim() ?? ""; };
    r.onerror = (e) => (e.error === "no-speech" ? resolve("") : reject(new Error(e.error)));
    r.onend = () => resolve(text);
    r.start();
  });
}
