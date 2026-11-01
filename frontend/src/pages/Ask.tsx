import { useState } from "react";
import { ask } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { speak } from "../speech";

// TODO(혜진): 길게 눌러 말하기(webkitSpeechRecognition). 현재는 텍스트 입력만
export default function Ask({ go }: { go: (path: string) => void }) {
  const { settings, result } = useApp();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<string[]>([]);

  const submit = async () => {
    if (!settings || !result?.artifact_id) return;
    const r = await ask(result.artifact_id, settings.profile, question);
    setAnswer(r.answer);
    setSources(r.sources);
    speak(r.answer);
  };

  return (
    <main>
      <PageTitle>질문하기</PageTitle>
      <input aria-label="질문 입력" value={question} onChange={(e) => setQuestion(e.target.value)} />
      <button aria-label="질문 보내기" onClick={submit}>질문 보내기</button>
      <p aria-live="polite">{answer}</p>
      {sources.length > 0 && <p>근거: {sources.join(", ")}</p>}
      <button aria-label="다시 촬영하기" onClick={() => go("/capture")}>다시 찍기</button>
    </main>
  );
}
