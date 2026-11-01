// TTS: 새 음성 전에 이전 음성을 cancel() 해서 겹치지 않게 한다.
const RATE_KEY = "yudam.rate";

export function getRate(): number {
  return Number(localStorage.getItem(RATE_KEY)) || 1.0; // 0.8 / 1.0 / 1.3
}

export function setRate(rate: number) {
  localStorage.setItem(RATE_KEY, String(rate));
}

export function speak(text: string) {
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ko-KR";
  u.rate = getRate();
  speechSynthesis.speak(u);
}
