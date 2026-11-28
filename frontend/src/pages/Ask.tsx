import { useEffect, useRef, useState } from "react";
import { ask } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { TopBar } from "../components/TopBar";
import { type Faq, faqFor } from "../faq";
import { canListen, listen, speak } from "../speech";

type Phase = "idle" | "listening" | "thinking";

interface Turn {
  q: string; // 화면에 보이는 질문
  ask: string; // /ask에 보낸 질문 (어려워요 → 다시 설명할 때 원래 질문을 다시 쓴다)
  a: string;
  sources: string[];
  from: "llm" | "faq";
  feedback?: "ok" | "hard";
}

const SLOW = 0.8; // 어려워요: 다시 설명이 안 될 때 천천히 다시 읽는 속도
const easier = (q: string) => `${q} (방금 답을 더 쉬운 말로, 짧게 다시 설명해 주세요)`;

// 슬라이드 14쪽 ④ 질문: 질문·답변 말풍선, 근거 표시, 이해됐어요/어려워요, 아래쪽 "누르고 말하기".
// 한 번 눌러 말하기: 누르면 "말씀하세요" 안내 뒤 듣고, 말이 끝나면 자동으로 질문을 보낸다.
// 길게 누르기는 TalkBack에서 두 번 탭 후 유지해야 해서 한 번 누르기로 했다.
export default function Ask({ go }: { go: (path: string) => void }) {
  const { settings, result } = useApp();
  const voice = canListen();
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState(""); // 입력창
  const [turns, setTurns] = useState<Turn[]>([]);
  const [typing, setTyping] = useState(!voice); // 입력창은 "글로 질문하기"를 눌러야 열린다 (음성 인식이 없으면 처음부터)
  const faqs = result?.artifact_id ? faqFor(result.artifact_id) : [];
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const how = voice ? "아래쪽 말하기 버튼을 누르고 궁금한 점을 말해 주세요" : "질문을 입력해 주세요";
    speak(faqs.length ? `${how}. 자주 묻는 질문도 있어요` : how);
  }, []);

  // 중괄호를 빼면 안 된다: 최신 크롬은 scrollIntoView가 Promise를 돌려줘서, effect가 반환하면 화면이 죽는다
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns, phase]);

  const last = turns[turns.length - 1];

  const send = async (shown: string, q: string) => {
    if (!settings || !result?.artifact_id || !q.trim()) return false;
    setPhase("thinking");
    speak(`${shown}. 찾아보고 있어요`);
    try {
      const r = await ask(result.artifact_id, settings.profile, q);
      setTurns((t) => [...t, { q: shown, ask: q, a: r.answer, sources: r.grounded ? r.sources : [], from: "llm" }]);
      speak(r.answer);
      return true;
    } catch {
      speak(faqs.length ? "연결이 불안정해요. 자주 묻는 질문을 눌러 보세요" : "연결이 불안정해요. 다시 시도해 주세요");
      return false;
    } finally {
      setPhase("idle");
    }
  };

  // 서버·음성 인식 없이 바로 답한다 (미리 써서 검수한 답)
  const pickFaq = (f: Faq) => {
    if (phase !== "idle") return;
    setTurns((t) => [...t, { q: f.q, ask: f.q, a: f.a, sources: ["자주 묻는 질문 (국가유산포털 설명 기반)"], from: "faq" }]);
    speak(f.a);
  };

  const talk = async () => {
    if (phase !== "idle") return;
    setPhase("listening");
    try {
      await speak("말씀하세요"); // 안내가 끝난 뒤 마이크를 켠다 (안내 소리가 인식되지 않게)
      const q = await listen();
      if (q) return void (await send(q, q));
      speak("잘 못 들었어요. 다시 눌러 주세요");
    } catch {
      setTyping(true);
      speak("마이크를 쓸 수 없어요. 아래 입력창에 질문을 적어 주세요");
    }
    setPhase("idle");
  };

  const mark = (feedback: Turn["feedback"]) =>
    setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, feedback } : x)));

  // 이해됐어요: 다음 행동 안내. 어려워요: 같은 자료로 더 쉽게 다시 설명 (안 되면 천천히 다시 읽기)
  const understood = () => {
    mark("ok");
    speak("좋아요. 더 궁금한 점이 있으면 말하기 버튼을 눌러 주세요");
  };
  const hard = async () => {
    if (!last || phase !== "idle") return;
    mark("hard");
    const ok = last.from === "llm" && (await send("더 쉽게 설명해 주세요", easier(last.ask)));
    if (!ok) speak(`천천히 다시 읽어 드릴게요. ${last.a}`, SLOW);
  };

  const label = { idle: "누르고 말하기", listening: "듣고 있어요", thinking: "찾아보고 있어요" }[phase];

  return (
    <main className="ask">
      <TopBar title="질문하기" back="해설로" onBack={() => go("/narration")} />

      <div className="thread">
        {turns.length === 0 && <p className="hint">유물에 대해 궁금한 점을 물어보세요. 예: 손 모양 더 알려줘</p>}
        {turns.map((t, i) => (
          <section key={i} className="turn" aria-label={`질문 ${i + 1}`}>
            <p className="bubble me"><span className="sr-only">내 질문: </span>{t.q}</p>
            <div className="bubble bot">
              <p><span className="sr-only">답변: </span>{t.a}</p>
              {t.sources.length > 0 && <small className="source">근거 · {t.sources.join(", ")}</small>}
            </div>
            {i === turns.length - 1 && (
              <div className="row" role="group" aria-label="답변이 어땠나요">
                <button aria-pressed={t.feedback === "ok"} onClick={understood} disabled={phase !== "idle"}>
                  이해됐어요
                </button>
                <button className="secondary" aria-pressed={t.feedback === "hard"} onClick={hard} disabled={phase !== "idle"}>
                  어려워요
                </button>
              </div>
            )}
          </section>
        ))}
        {phase === "thinking" && <p className="bubble bot typing" aria-hidden="true">찾아보고 있어요…</p>}

        {faqs.length > 0 && (
          <section className="faq" aria-label="자주 묻는 질문">
            <h2>자주 묻는 질문</h2>
            <div className="faq-chips">
              {faqs.map((f) => (
                <button key={f.q} className="chip" onClick={() => pickFaq(f)} disabled={phase !== "idle"}>{f.q}</button>
              ))}
            </div>
          </section>
        )}
        <div ref={end} />
      </div>

      <div className="talk-dock">
        {voice && (
          <button className={`mic ${phase}`} aria-label={phase === "idle" ? "질문 말하기" : label} onClick={talk} disabled={phase !== "idle"}>
            <Icon name="mic" size={44} />
          </button>
        )}
        {voice && <p className="mic-label" aria-hidden="true">{label}</p>}
        {last && (
          <button className="link" aria-label="마지막 답변 다시 듣기" onClick={() => speak(last.a)}>답변 다시 듣기</button>
        )}
        {typing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(question, question);
              setQuestion("");
            }}
          >
            <input aria-label="질문 입력" placeholder="예: 손 모양 더 알려줘" value={question} onChange={(e) => setQuestion(e.target.value)} />
            <button aria-label="질문 보내기" type="submit" disabled={phase !== "idle"}>보내기</button>
          </form>
        ) : (
          <button className="link" onClick={() => setTyping(true)}>글로 질문하기</button>
        )}
      </div>
    </main>
  );
}
