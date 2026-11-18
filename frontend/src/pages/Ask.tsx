import { useEffect, useState } from "react";
import { ask } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { type Faq, faqFor } from "../faq";
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
  const faqs = result?.artifact_id ? faqFor(result.artifact_id) : [];
  const [typing, setTyping] = useState(!voice); // 입력창은 "글로 질문하기"를 눌러야 열린다 (음성 인식이 없으면 처음부터)

  useEffect(() => {
    const how = voice ? "질문하기 버튼을 누르고 궁금한 점을 말해 주세요" : "질문을 입력해 주세요";
    speak(faqs.length ? `${how}. 아래에 자주 묻는 질문도 있어요` : how);
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
      speak(faqs.length ? "연결이 불안정해요. 아래 자주 묻는 질문을 눌러 보세요" : "연결이 불안정해요. 다시 시도해 주세요");
    } finally {
      setPhase("idle");
    }
  };

  // 서버·음성 인식 없이 바로 답한다 (미리 써서 검수한 답)
  const pickFaq = (f: Faq) => {
    if (phase !== "idle") return;
    setAsked(f.q);
    setAnswer(f.a);
    setSources(["자주 묻는 질문 (국가유산포털 설명 기반)"]);
    speak(f.a);
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
      setTyping(true);
      speak("마이크를 쓸 수 없어요. 아래 입력창에 질문을 적어 주세요");
    }
    setPhase("idle");
  };

  const label = { idle: answer ? "다시 질문하기" : "질문하기", listening: "듣고 있어요", thinking: "찾아보고 있어요" }[phase];

  return (
    <main className="fill">
      <PageTitle>질문하기</PageTitle>
      {voice && (
        // 답변이 나오면 버튼을 줄이고 남는 공간을 답변에 준다
        <button className={answer ? "talk talk-small" : "talk"} aria-label="질문 말하기" onClick={talk} disabled={phase !== "idle"}>
          {label}
        </button>
      )}
      {answer && (
        <section className="answer" aria-label="답변">
          <small>질문: {asked}</small>
          <p aria-live="polite">{answer}</p>
          {sources.length > 0 && <small>근거: {sources.join(", ")}</small>}
        </section>
      )}
      {faqs.length > 0 && (
        <section className="faq" aria-label="자주 묻는 질문">
          <h2>자주 묻는 질문</h2>
          {faqs.map((f) => (
            <button key={f.q} className="secondary" onClick={() => pickFaq(f)} disabled={phase !== "idle"}>{f.q}</button>
          ))}
        </section>
      )}
      {answer && <button className="secondary" aria-label="답변 다시 듣기" onClick={() => speak(answer)}>답변 다시 듣기</button>}
      {typing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(question);
            setQuestion("");
          }}
        >
          <input aria-label="질문 입력" placeholder="예: 손 모양 더 알려줘" value={question} onChange={(e) => setQuestion(e.target.value)} />
          <button aria-label="질문 보내기" type="submit" disabled={phase !== "idle"}>보내기</button>
        </form>
      ) : (
        <button className="secondary" onClick={() => setTyping(true)}>글로 질문하기</button>
      )}
      <div className="row">
        <button className="secondary" aria-label="해설로 돌아가기" onClick={() => go("/narration")}>해설로</button>
        <button className="secondary" aria-label="다시 촬영하기" onClick={() => go("/capture")}>다시 찍기</button>
      </div>
    </main>
  );
}
