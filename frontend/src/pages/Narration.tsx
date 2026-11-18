import { useEffect, useRef, useState } from "react";
import { getNarration } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { bundledNarration } from "../offline";
import { getRate, RATES, setRate, speak } from "../speech";

// 해설이 끝나면 다음 행동을 알려 준다. 다른 불상으로 잘못 인식됐을 때 되돌릴 길이기도 하다.
const AFTER = "다른 불상이면 다시 찍기를, 궁금한 점이 있으면 질문하기를 눌러 주세요";

export default function Narration({ go }: { go: (path: string) => void }) {
  const { settings, result } = useApp();
  const [text, setText] = useState("");
  const [rate, setRateState] = useState(getRate());
  const mounted = useRef(true);
  const playId = useRef(0);

  // 해설을 읽고, 끝까지 들었을 때만 다음 행동 안내를 덧붙인다.
  // (다시 듣기·속도 변경·화면 이동으로 끊기면 안내하지 않는다)
  const play = async (t: string) => {
    const id = ++playId.current;
    await speak(t);
    if (mounted.current && playId.current === id) speak(AFTER);
  };

  useEffect(() => {
    if (!settings || !result?.artifact_id) return go("/capture");
    mounted.current = true; // 개발 모드(StrictMode)는 effect를 두 번 실행한다
    const id = result.artifact_id;
    getNarration(id, settings.profile, settings.length)
      .then((n) => { setText(n.text); play(n.text); }) // 인식 직후 바로 재생
      .catch(() => {
        // 서버가 안 되면 앱에 함께 묶어 둔 같은 해설로 읽는다
        const t = bundledNarration(id, settings.profile, settings.length);
        if (t) { setText(t); play(t); } else speak("해설을 불러오지 못했어요");
      });
    return () => { mounted.current = false; };
  }, []);

  const changeRate = (r: number) => {
    setRate(r);
    setRateState(r);
    if (text) play(text); // 바꾼 속도로 처음부터 다시 읽는다
  };

  return (
    <main>
      <PageTitle>{result?.name ?? "해설"}</PageTitle>
      <p aria-live="polite">{text}</p>
      <button aria-label="해설 다시 듣기" onClick={() => play(text)}>다시 듣기</button>
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
