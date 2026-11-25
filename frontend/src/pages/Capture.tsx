import { useEffect, useRef, useState } from "react";
import { recognize } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { TopBar } from "../components/TopBar";
import { captureFrame, resizeFile } from "../image";
import { speak } from "../speech";

// 서버 message가 없을 때의 대체 문구. 화면을 못 봐도 따라 할 수 있는 몸의 동작으로 안내한다
const FALLBACK = {
  uncertain: "반가사유상 종류로 보여요. 한 걸음 앞으로 다가가 주세요. 폰을 두 손으로 가슴 높이에 잡고 다시 찍어 주세요",
  reject: "유물을 찾지 못했어요. 유물 쪽으로 몸을 돌리고, 폰을 가슴 높이에 들고 다시 찍어 주세요",
};
const READY = "폰을 가슴 높이에 들고 유물 쪽을 향해 주세요";

// 진동으로도 결과를 알린다: 찰칵 짧게 1번, 찾으면 짧게 2번, 다시 찍어야 하면 길게 1번
const BUZZ = { shoot: 50, ok: [80, 80, 80], retry: 400 };

type Camera = "starting" | "on" | "off";

// 슬라이드 14쪽 ② 촬영 가이드: 미리보기 위에 가이드 틀, 아래에 안내 카드와 셔터.
// 셔터는 보지 않고도 누를 수 있게 화면 아래쪽 전체가 버튼이다 (가운데 동그라미는 표시용).
// 자동 인식은 화면 전체를 주기적으로 서버에 보내는 방식이다. 방향 안내("조금 왼쪽으로")는 하지 않는다:
// 유물 위치를 찾는 기능(객체 탐지)이 없다.
export default function Capture({ go }: { go: (path: string) => void }) {
  const { setResult, setPhoto } = useApp();
  const video = useRef<HTMLVideoElement>(null);
  const [camera, setCamera] = useState<Camera>("starting");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [status, setStatus] = useState(READY);
  // 올린 영상은 카메라 자리에서 재생해 자동 인식을 그대로 돌린다 (현장에 못 갈 때의 확인용)
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoChosen = useRef(false);
  const pausedRef = useRef(false); // 사진을 올리면 결과 안내가 덮이지 않게 자동 인식을 멈춘다 (촬영을 누르면 다시 시작)
  const live = camera === "on" || videoUrl !== null; // 미리보기에 인식할 화면이 있는지

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    const noCamera = () => {
      setCamera("off");
      setStatus("카메라를 쓸 수 없어요. 사진 찍어 올리기를 눌러 주세요");
      speak("카메라를 쓸 수 없어요. 사진 찍어 올리기 버튼을 눌러 주세요");
    };
    // HTTPS가 아니면(ngrok 없이 접속) mediaDevices 자체가 없다
    if (!navigator.mediaDevices?.getUserMedia) noCamera();
    else
      navigator.mediaDevices
        .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false })
        .then((s) => {
          if (cancelled || videoChosen.current) return s.getTracks().forEach((t) => t.stop());
          stream = s;
          if (video.current) video.current.srcObject = s;
          setCamera("on");
          speak(`${READY}. 자동으로 인식해요. 화면 아래쪽 절반을 누르면 바로 촬영해요`);
          setStatus("유물을 찾고 있어요");
        })
        .catch(() => !cancelled && !videoChosen.current && noCamera());
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop()); // 다른 화면으로 가면 카메라를 끈다
    };
  }, []);

  useEffect(() => () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  // 자동 인식: 카메라가 켜지면 1~2초마다 미리 인식해 상태를 알려 주고, 같은 유물이 두 번 연속 ok면 자동으로 넘어간다
  // 음성은 상태가 바뀔 때(또는 같은 상태가 8초 이상 이어질 때)만 말해 소리가 겹치거나 시끄럽지 않게 한다
  useEffect(() => {
    if (!live) return;
    let stop = false;
    let okId = "";
    let okCount = 0;
    let lastKey = "";
    let lastSpoken = 0;
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const tell = (key: string, msg: string) => {
      setStatus(msg);
      if (key !== lastKey || Date.now() - lastSpoken > 8000) {
        lastSpoken = Date.now();
        speak(msg);
      }
      lastKey = key;
    };
    (async () => {
      await sleep(3000); // 첫 안내 음성이 끝난 뒤 시작
      while (!stop) {
        const v = video.current;
        if (busyRef.current || pausedRef.current || !v || v.videoWidth === 0) {
          await sleep(300);
          continue;
        }
        try {
          const image = await captureFrame(v);
          const r = await recognize(image);
          if (stop || busyRef.current || pausedRef.current) continue;
          console.info(`[auto] ${v.currentTime.toFixed(1)}s`, r.status, r.artifact_id, r.score);
          if (r.status === "ok") {
            okCount = r.artifact_id === okId ? okCount + 1 : 1;
            okId = r.artifact_id ?? "";
            if (okCount >= 2) {
              stop = true;
              navigator.vibrate?.(BUZZ.ok);
              setResult(r);
              setPhoto(image); // 해설 화면 썸네일
              go("/narration");
              return;
            }
            setStatus(`${r.name ?? "유물"} 확인하고 있어요. 그대로 잠시 들고 계세요`);
          } else {
            okId = "";
            okCount = 0;
            tell(r.status, r.message ?? FALLBACK[r.status]);
          }
        } catch {
          okCount = 0;
          tell("error", "연결이 불안정해요. 잠시만 기다려 주세요");
          await sleep(1500);
        }
        await sleep(700);
      }
    })();
    return () => {
      stop = true;
    };
    // setPhoto는 렌더마다 새로 만들어져서 넣지 않는다 (넣으면 자동 인식이 다시 시작된다)
  }, [live, videoUrl, go, setResult]);

  const send = async (getImage: () => Promise<Blob>) => {
    if (busy) return;
    busyRef.current = true; // 직접 촬영하는 동안 자동 인식은 잠시 멈춘다
    setBusy(true);
    navigator.vibrate?.(BUZZ.shoot);
    setStatus("확인하고 있어요");
    speak("확인하고 있어요");
    const t0 = performance.now();
    try {
      const image = await getImage();
      const r = await recognize(image);
      console.info(`[timing] /recognize ${Math.round(performance.now() - t0)}ms`, r.status, r.score);
      setResult(r);
      if (r.status === "ok") {
        navigator.vibrate?.(BUZZ.ok);
        setPhoto(image); // 해설 화면 썸네일 (서버에 저장하지 않는다)
        return go("/narration");
      }
      navigator.vibrate?.(BUZZ.retry);
      const msg = r.message ?? FALLBACK[r.status];
      setStatus(msg);
      speak(msg);
    } catch {
      const msg = "연결이 불안정해요. 다시 시도해 주세요";
      setStatus(msg);
      speak(msg);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const shoot = () => {
    pausedRef.current = false;
    if (video.current && video.current.videoWidth > 0) send(() => captureFrame(video.current!));
  };

  const open = (f: File) => {
    if (!f.type.startsWith("video/")) {
      pausedRef.current = true;
      send(() => resizeFile(f));
      return;
    }
    const v = video.current!;
    videoChosen.current = true;
    pausedRef.current = false;
    (v.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
    v.srcObject = null; // srcObject가 남아 있으면 src가 무시된다
    setVideoUrl(URL.createObjectURL(f));
    setStatus("올린 영상에서 유물을 찾고 있어요");
    speak("올린 영상에서 유물을 찾고 있어요");
  };

  const fileInput = (label: string, accept: string, useCamera: boolean) => (
    <label className="upload">
      {label}
      <input
        type="file"
        accept={accept}
        capture={useCamera ? "environment" : undefined}
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = ""; // 같은 파일을 다시 골라도 onChange가 오게
          if (f) open(f);
        }}
      />
    </label>
  );

  return (
    <main className="capture">
      <video
        ref={video}
        className="capture-preview"
        src={videoUrl ?? undefined}
        autoPlay
        loop
        playsInline
        muted
        aria-hidden="true"
        onError={() => {
          if (!videoUrl) return;
          const msg = "이 영상은 재생할 수 없어요. 다른 파일을 골라 주세요";
          setStatus(msg);
          speak(msg);
        }}
      />

      <TopBar title="사유의 방" back="설정" onBack={() => go("/onboarding")} />

      {live && (
        <div className="guide" aria-hidden="true">
          <span className="guide-chip">{busy ? "인식 중…" : "가운데에 유물"}</span>
          <i className="c tl" /><i className="c tr" /><i className="c bl" /><i className="c br" />
        </div>
      )}

      <div className="capture-dock">
        <div className="status-card" aria-live="polite">
          <span className="status-icon" aria-hidden="true"><Icon name="info" size={22} /></span>
          <span>{status}</span>
        </div>
        <p className="capture-note" aria-hidden="true">음성·진동으로 결과를 알려 드려요</p>

        {camera === "off" && fileInput("사진 찍어 올리기", "image/*", true)}
        {fileInput("사진·영상 올리기", "image/*,video/*", false)}
        {live && (
          <button className="capture-shoot" aria-label="유물 촬영하기" onClick={shoot} disabled={busy}>
            <span className="shutter" aria-hidden="true">{busy ? "확인 중" : ""}</span>
          </button>
        )}
      </div>
    </main>
  );
}
