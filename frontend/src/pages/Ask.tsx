import { useEffect, useState } from "react";
import { ask } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { canListen, listen, speak } from "../speech";

type Phase = "idle" | "listening" | "thinking";

// 한 번 눌러 말하기: 누르면 "말씀하세요" 안내 뒤 듣고, 말이 끝나면 자동으로 질문을 보낸다.
// 길게 누르기는 TalkBack에서 두 번 탭 후 유지해야 해서 한 번 누르기로 했다.
export default function Ask({ go }: { go: (path: string) => void }) {
  const { settings, result } = useApp();
  const voice = canListen();
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState(""); // 입력창
  const [asked, setAsked] = useState(""); // 마지막으로 보낸 질문
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<string[]>([]);

  useEffect(() => {
    speak(voice ? "질문하기 버튼을 누르고 궁금한 점을 말해 주세요" : "질문을 입력해 주세요");
  }, []);

  const submit = async (q: string) => {
    if (!settings || !result?.artifact_id || !q.trim()) return;
    setAsked(q);
    setPhase("thinking");
    speak(`${q}. 찾아보고 있어요`);
    try {
      const r = await ask(result.artifact_id, settings.profile, q);
      setAnswer(r.answer);
      setSources(r.sources);
      speak(r.answer);
    } catch {
      speak("연결이 불안정해요. 다시 시도해 주세요");
    } finally {
      setPhase("idle");
    }
  };

  const talk = async () => {
    if (phase !== "idle") return;
    setPhase("listening");
    try {
      await speak("말씀하세요"); // 안내가 끝난 뒤 마이크를 켠다 (안내 소리가 인식되지 않게)
      const q = await listen();
      if (q) return await submit(q);
      speak("잘 못 들었어요. 다시 눌러 주세요");
    } catch {
      speak("마이크를 쓸 수 없어요. 아래 입력창에 질문을 적어 주세요");
    }
    setPhase("idle");
  };

  const label = { idle: "질문하기", listening: "듣고 있어요", thinking: "찾아보고 있어요" }[phase];

  return (
    <main>
      <PageTitle>질문하기</PageTitle>
      {voice && (
        <button className="big" aria-label="질문 말하기" onClick={talk} disabled={phase !== "idle"}>
          {label}
        </button>
      )}
      {asked && <p>질문: {asked}</p>}
      <p aria-live="polite">{answer}</p>
      {sources.length > 0 && <p>근거: {sources.join(", ")}</p>}
      {answer && <button aria-label="답변 다시 듣기" onClick={() => speak(answer)}>답변 다시 듣기</button>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
          setQuestion("");
        }}
      >
        <input aria-label="질문 입력" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button aria-label="질문 보내기" type="submit" disabled={phase !== "idle"}>보내기</button>
      </form>
      <button aria-label="해설로 돌아가기" onClick={() => go("/narration")}>해설로 돌아가기</button>
      <button aria-label="다시 촬영하기" onClick={() => go("/capture")}>다시 찍기</button>
    </main>
  );
}
