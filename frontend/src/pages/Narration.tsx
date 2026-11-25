import { useEffect, useRef, useState } from "react";
import { getNarration, type Length } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { TopBar } from "../components/TopBar";
import { bundledNarration } from "../offline";
import { lengthOf, profileOf, tagsFor } from "../profiles";
import { getRate, RATES, setRate, speak, stopSpeaking } from "../speech";

// 해설이 끝나면 다음 행동을 알려 준다. 다른 불상으로 잘못 인식됐을 때 되돌릴 길이기도 하다.
const AFTER = "다른 불상이면 다시 찍기를, 궁금한 점이 있으면 질문하기를 눌러 주세요";

const split = (t: string) => t.split(/(?<=[.?!])\s+/).map((s) => s.trim()).filter(Boolean);

// 슬라이드 14쪽 ③ 해설: 찍은 사진·이름·태그, 맞춤 해설 배지, 본문, 재생 막대, 다시 듣기·더 짧게·더 자세히.
// 브라우저 음성(speechSynthesis)은 재생 위치를 알려 주지 않아서, 문장 단위로 읽고 "몇 번째 문장"으로 진행을 보여 준다.
// 일시정지도 문장 단위다 (다시 누르면 그 문장 처음부터).
export default function Narration({ go }: { go: (path: string) => void }) {
  const { settings, saveSettings, result, photo } = useApp();
  const [text, setText] = useState("");
  const [pos, setPos] = useState(0); // 읽고 있는(또는 멈춘) 문장 번호
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState(getRate());
  const sentences = useRef<string[]>([]);
  const at = useRef(0);
  const run = useRef(0); // 재생할 때마다 1씩 올린다. 값이 바뀌면 이전 재생은 멈춘다
  const mounted = useRef(true);

  const play = async (from: number) => {
    const id = ++run.current;
    const list = sentences.current;
    setPlaying(true);
    for (let i = from; i < list.length; i++) {
      at.current = i;
      setPos(i);
      await speak(list[i]);
      if (!mounted.current || run.current !== id) return; // 멈춤·다시 듣기·화면 이동
    }
    at.current = list.length;
    setPos(list.length);
    setPlaying(false);
    speak(AFTER); // 끝까지 들었을 때만 안내한다
  };

  const stop = () => {
    run.current++;
    stopSpeaking();
    setPlaying(false);
  };

  const load = (length: Length) => {
    if (!settings || !result?.artifact_id) return;
    const id = result.artifact_id;
    const show = (t: string) => {
      setText(t);
      sentences.current = split(t);
      play(0); // 불러오면 바로 재생
    };
    getNarration(id, settings.profile, length)
      .then((n) => show(n.text))
      .catch(() => {
        // 서버가 안 되면 앱에 함께 묶어 둔 같은 해설로 읽는다
        const t = bundledNarration(id, settings.profile, length);
        if (t) show(t);
        else speak("해설을 불러오지 못했어요");
      });
  };

  useEffect(() => {
    if (!settings || !result?.artifact_id) return go("/capture");
    mounted.current = true; // 개발 모드(StrictMode)는 effect를 두 번 실행한다
    load(settings.length);
    return () => {
      mounted.current = false;
      run.current++;
    };
  }, []);

  if (!settings || !result?.artifact_id) return null;

  const total = sentences.current.length;
  const done = pos >= total && total > 0;
  const profile = profileOf(settings.profile);

  const toggle = () => (playing ? stop() : play(done ? 0 : at.current));

  const cycleRate = () => {
    const i = RATES.findIndex((r) => r.value === rate);
    const next = RATES[(i + 1) % RATES.length];
    setRate(next.value);
    setRateState(next.value);
    if (playing) play(at.current); // 바꾼 속도로 지금 문장부터 다시 읽는다
    else speak(`${next.label} 속도`);
  };

  // 피드백: 더 짧게 / 더 자세히 → 해설 길이 설정을 바꾸고 바로 다시 읽는다 (다음 유물에도 적용)
  const changeLength = (length: Length) => {
    if (length === settings.length) return speak(`지금 ${lengthOf(length).spoken}이에요`);
    stop();
    saveSettings({ ...settings, length });
    load(length);
  };

  const rateLabel = RATES.find((r) => r.value === rate)?.label ?? "보통";

  return (
    <main className="narration">
      <TopBar title="해설" back="다시 찍기" onBack={() => go("/capture")} />

      <section className="art-card">
        {photo && <img className="art-thumb" src={photo} alt="" />}
        <div>
          <h2>{result.name}</h2>
          <p className="tags">
            {tagsFor(result.artifact_id).map((t) => <span key={t} className="tag">{t}</span>)}
          </p>
        </div>
      </section>

      <p className="badge">{profile.label} 맞춤 해설</p>

      {/* TTS가 읽으므로 aria-live를 두지 않는다 (TalkBack과 겹쳐 두 번 읽힌다) */}
      <div className="narration-text">
        {sentences.current.length
          ? sentences.current.map((s, i) => <span key={i} className={i === pos && playing ? "now" : undefined}>{s} </span>)
          : text || "해설을 불러오고 있어요"}
      </div>

      {/* 아래쪽 고정: 본문이 길어도 재생·피드백·질문하기 버튼이 항상 화면에 보인다 */}
      <div className="narration-dock">
      <div className="player">
        <button className="play" aria-label={playing ? "일시정지" : "재생"} onClick={toggle} disabled={!total}>
          <Icon name={playing ? "pause" : "play"} size={30} />
        </button>
        <div className="player-progress">
          <progress value={done ? total : pos} max={total || 1} aria-hidden="true" />
          <small aria-hidden="true">{total ? `${Math.min(pos + 1, total)} / ${total} 문장` : ""}</small>
        </div>
        <button className="rate" aria-label={`말하기 속도 ${rateLabel}. 눌러서 바꾸기`} onClick={cycleRate}>
          {rate.toFixed(1)}x
        </button>
      </div>

      <div className="row feedback" role="group" aria-label="해설 다시 듣기와 길이 바꾸기">
        <button onClick={() => play(0)} disabled={!total}>다시 듣기</button>
        <button className="secondary" aria-pressed={settings.length === "short"} onClick={() => changeLength("short")}>
          더 짧게
        </button>
        <button className="secondary" aria-pressed={settings.length === "long"} onClick={() => changeLength("long")}>
          더 자세히
        </button>
      </div>

      {/* 해설을 들은 뒤 이 유물에 대해 바로 질문 (슬라이드 ④) */}
      <div className="row">
        <button className="primary-wide" aria-label={`${result.name ?? "이 유물"}에 대해 질문하기`} onClick={() => go("/ask")}>
          <Icon name="mic" size={22} /> 질문하기
        </button>
        <button className="secondary next-shot" aria-label="다른 유물 찍기" onClick={() => go("/capture")}>다시 찍기</button>
      </div>
      </div>
    </main>
  );
}
