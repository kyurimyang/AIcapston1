import { useEffect, useState } from "react";
import type { Length, Profile } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { speak } from "../speech";

const PROFILES: { value: Profile; label: string; desc: string }[] = [
  { value: "congenital", label: "선천 전맹", desc: "태어날 때부터 앞이 보이지 않았어요" },
  { value: "acquired", label: "후천 전맹", desc: "예전에는 볼 수 있었어요" },
  { value: "low_vision", label: "저시력", desc: "조금 볼 수 있어요" },
];

const LENGTHS: { value: Length; label: string; desc: string; spoken: string }[] = [
  { value: "short", label: "짧게", desc: "핵심만 · 약 30초", spoken: "짧은 해설" },
  { value: "long", label: "자세히", desc: "자세하게 · 약 1분 30초", spoken: "자세한 해설" },
];

// 안내 음성이 끝나지 않는 기기에서도 멈추지 않게, 이 시간이 지나면 넘어간다
const CONFIRM_MAX_MS = 7000;

// 한 화면에서 시각 경험과 해설 길이를 고르고 "시작하기" (설정 바꾸기로 다시 와도 이전 값이 선택돼 있다)
// 선택지는 라디오 버튼이라 TalkBack이 "후천 전맹, 선택됨, 3개 중 2번째"처럼 읽는다
export default function Onboarding({ go }: { go: (path: string) => void }) {
  const { settings, saveSettings } = useApp();
  const [profile, setProfile] = useState<Profile | null>(settings?.profile ?? null);
  const [length, setLength] = useState<Length>(settings?.length ?? "short");
  const [starting, setStarting] = useState(false);

  useEffect(() => { speak("유담입니다. 평소 어떻게 보이시나요?"); }, []);

  const p = PROFILES.find((x) => x.value === profile);
  const l = LENGTHS.find((x) => x.value === length)!;

  // 고른 설정을 소리로 확인해 준 뒤 촬영 화면으로 넘어간다.
  // 안내가 끝난 뒤에 넘어가야 촬영 화면의 첫 안내에 끊기지 않는다.
  const start = async () => {
    if (!p || starting) return;
    saveSettings({ profile: p.value, length });
    setStarting(true);
    await Promise.race([
      speak(`${p.label}, ${l.spoken}로 설정했어요. 촬영 화면으로 넘어갈게요`),
      new Promise((resolve) => setTimeout(resolve, CONFIRM_MAX_MS)),
    ]);
    go("/capture");
  };

  return (
    <main className="onboarding">
      <PageTitle>평소 어떻게 보이시나요?</PageTitle>

      <fieldset className="choices">
        <legend>시각 경험</legend>
        {PROFILES.map((x) => (
          <label key={x.value} className="choice">
            <input type="radio" name="profile" checked={profile === x.value} onChange={() => setProfile(x.value)} />
            <span>
              <strong>{x.label}</strong>
              <small>{x.desc}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset className="choices choices-row">
        <legend>해설 길이</legend>
        {LENGTHS.map((x) => (
          <label key={x.value} className="choice">
            <input type="radio" name="length" checked={length === x.value} onChange={() => setLength(x.value)} />
            <span>
              <strong>{x.label}</strong>
              <small>{x.desc}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <p className="summary" aria-live="polite">
        {p ? `내 설정: ${p.label} · ${l.label} 듣기` : "시각 경험을 골라 주세요"}
      </p>

      <button onClick={start} disabled={!profile || starting}>{starting ? "설정했어요" : "시작하기"}</button>
    </main>
  );
}
