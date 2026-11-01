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

export default function Onboarding({ go }: { go: (path: string) => void }) {
  const { saveSettings } = useApp();
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => speak("유담입니다. 시각 경험을 골라 주세요"), []);

  const choose = (length: Length) => {
    if (!profile) return;
    saveSettings({ profile, length });
    go("/capture");
  };

  return (
    <main>
      <PageTitle>시각 경험을 골라 주세요</PageTitle>
      {!profile ? (
        PROFILES.map((p) => (
          <button key={p.value} aria-label={`${p.label}. ${p.desc}`} onClick={() => setProfile(p.value)}>
            {p.label}
          </button>
        ))
      ) : (
        <>
          <button aria-label="짧게 듣기" onClick={() => choose("short")}>짧게</button>
          <button aria-label="자세히 듣기" onClick={() => choose("long")}>자세히</button>
        </>
      )}
    </main>
  );
}
