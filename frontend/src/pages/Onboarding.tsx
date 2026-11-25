import { useEffect, useState } from "react";
import type { Length, Profile } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { PageTitle } from "../components/PageTitle";
import { LENGTHS, PROFILES } from "../profiles";
import { speak } from "../speech";

// 안내 음성이 끝나지 않는 기기에서도 멈추지 않게, 이 시간이 지나면 넘어간다
const CONFIRM_MAX_MS = 7000;

// 슬라이드 14쪽 ① 온보딩: 시각 경험 카드 3개 + 해설 길이 2개 + 내 맞춤 프로필 + 시작하기
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
      <span className="app-mark" aria-hidden="true"><Icon name="person" size={22} /></span>
      <PageTitle>평소 어떻게 보이시나요?</PageTitle>

      <fieldset className="choices">
        <legend className="sr-only">시각 경험</legend>
        {PROFILES.map((x) => (
          <label key={x.value} className="choice">
            <input type="radio" name="profile" checked={profile === x.value} onChange={() => setProfile(x.value)} />
            <span className="choice-icon" aria-hidden="true"><Icon name={x.icon} /></span>
            <span className="choice-text">
              <strong>{x.label}</strong>
              <small>{x.desc}</small>
            </span>
            <span className="choice-check" aria-hidden="true"><Icon name="check" size={20} /></span>
          </label>
        ))}
      </fieldset>

      <fieldset className="choices choices-row">
        <legend>해설 길이 <small>· 나중에 언제든 바꿀 수 있어요</small></legend>
        {LENGTHS.map((x) => (
          <label key={x.value} className="choice">
            <input type="radio" name="length" checked={length === x.value} onChange={() => setLength(x.value)} />
            <span className="choice-text">
              <strong>{x.label}</strong>
              <small>{x.desc}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <section className="summary" aria-live="polite" aria-label="내 맞춤 프로필">
        <small>내 맞춤 프로필</small>
        {p ? (
          <>
            <strong>{p.label} · {l.spoken}</strong>
            <small>{p.how}</small>
          </>
        ) : (
          <strong>시각 경험을 골라 주세요</strong>
        )}
      </section>

      <button onClick={start} disabled={!profile || starting}>{starting ? "설정했어요" : "시작하기"}</button>
      <p className="hint">TalkBack을 켜면 모든 버튼을 소리로 읽어 줘요</p>
    </main>
  );
}
