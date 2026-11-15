import { useEffect, useState } from "react";
import { getNarration } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { getRate, RATES, setRate, speak } from "../speech";

export default function Narration({ go }: { go: (path: string) => void }) {
  const { settings, result } = useApp();
  const [text, setText] = useState("");
  const [rate, setRateState] = useState(getRate());

  useEffect(() => {
    if (!settings || !result?.artifact_id) return go("/capture");
    getNarration(result.artifact_id, settings.profile, settings.length)
      .then((n) => { setText(n.text); speak(n.text); }) // 인식 직후 바로 재생
      .catch(() => speak("해설을 불러오지 못했어요"));
  }, []);

  const changeRate = (r: number) => {
    setRate(r);
    setRateState(r);
    if (text) speak(text); // 바꾼 속도로 처음부터 다시 읽는다
  };

  return (
    <main>
      <PageTitle>{result?.name ?? "해설"}</PageTitle>
      <p aria-live="polite">{text}</p>
      <button aria-label="해설 다시 듣기" onClick={() => speak(text)}>다시 듣기</button>
      <div className="row" role="group" aria-label="말하기 속도">
        {RATES.map((r) => (
          <button
            key={r.value}
            aria-label={`${r.label} 듣기`}
            aria-pressed={rate === r.value}
            onClick={() => changeRate(r.value)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <button aria-label="질문하기" onClick={() => go("/ask")}>질문하기</button>
      <button aria-label="다시 촬영하기" onClick={() => go("/capture")}>다시 찍기</button>
    </main>
  );
}
