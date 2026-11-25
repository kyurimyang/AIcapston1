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
// 크롬은 cancel() 직후 같은 순간에 speak()하면 새 음성을 버리거나, 일시정지 상태로 굳어 아무 소리도 안 나는 경우가 있다.
// 그래서 cancel 뒤 잠깐 쉬고, resume()으로 굳은 상태를 풀어 준 뒤 말한다.
const GAP_MS = 60;
let latest = 0;

/** 지금 읽는 음성과 곧 읽으려던 음성을 모두 멈춘다 (일시정지) */
export function stopSpeaking() {
  latest++;
  speechSynthesis.cancel();
}

export function speak(text: string, rate = getRate()): Promise<void> {
  const id = ++latest;
  speechSynthesis.cancel();
  return new Promise((resolve) => {
    setTimeout(() => {
      if (id !== latest) return resolve(); // 그 사이에 다른 음성이 요청됐다
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "ko-KR";
      u.rate = rate;
      u.onend = () => resolve();
      u.onerror = (e) => {
        // not-allowed: 페이지를 새로 연 뒤 아직 화면을 한 번도 누르지 않아 크롬이 막은 것
        if (e.error !== "interrupted" && e.error !== "canceled") console.warn("[tts]", e.error, text.slice(0, 20));
        resolve();
      };
      speechSynthesis.resume();
      speechSynthesis.speak(u);
    }, GAP_MS);
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
  stopSpeaking(); // TTS 소리가 마이크로 들어가지 않게
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
