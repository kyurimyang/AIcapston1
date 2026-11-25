import { useEffect, useRef, useState } from "react";
import { recognize } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { captureFrame, resizeFile } from "../image";
import { speak } from "../speech";

// 서버 message가 없을 때의 대체 문구. 화면을 못 봐도 따라 할 수 있는 몸의 동작으로 안내한다
const FALLBACK = {
  uncertain: "반가사유상 종류로 보여요. 한 걸음 앞으로 다가가 주세요. 폰을 두 손으로 가슴 높이에 잡고 다시 찍어 주세요",
  reject: "유물을 찾지 못했어요. 유물 쪽으로 몸을 돌리고, 폰을 가슴 높이에 들고 다시 찍어 주세요",
};

type Camera = "starting" | "on" | "off";

// 화면 전체가 카메라 미리보기, 아래 절반 전체가 촬영 버튼 (보지 않고도 누를 수 있게)
export default function Capture({ go }: { go: (path: string) => void }) {
  const { setResult } = useApp();
  const video = useRef<HTMLVideoElement>(null);
  const [camera, setCamera] = useState<Camera>("starting");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [status, setStatus] = useState("");
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
          speak("유물을 향해 천천히 움직여 주세요. 자동으로 인식해요. 화면 아래쪽 절반을 누르면 바로 촬영해요");
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
          const r = await recognize(await captureFrame(v));
          if (stop || busyRef.current || pausedRef.current) continue;
          console.info(`[auto] ${v.currentTime.toFixed(1)}s`, r.status, r.artifact_id, r.score);
          if (r.status === "ok") {
            okCount = r.artifact_id === okId ? okCount + 1 : 1;
            okId = r.artifact_id ?? "";
            if (okCount >= 2) {
              stop = true;
              navigator.vibrate?.([50, 50, 50]);
              setResult(r);
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
  }, [live, videoUrl, go, setResult]);

  const send = async (getImage: () => Promise<Blob>) => {
    if (busy) return;
    busyRef.current = true; // 직접 촬영하는 동안 자동 인식은 잠시 멈춘다
    setBusy(true);
    navigator.vibrate?.(50);
    setStatus("확인하고 있어요");
    speak("확인하고 있어요");
    const t0 = performance.now();
    try {
      const r = await recognize(await getImage());
      console.info(`[timing] /recognize ${Math.round(performance.now() - t0)}ms`, r.status, r.score);
      setResult(r);
      if (r.status === "ok") return go("/narration");
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
      <div className="capture-top">
        <PageTitle>유물 촬영</PageTitle>
        <div aria-live="polite">{status}</div>
        <button aria-label="설정 바꾸기" onClick={() => go("/onboarding")}>설정 바꾸기</button>
        {camera === "off" && fileInput("사진 찍어 올리기", "image/*", true)}
        {fileInput("사진·영상 올리기", "image/*,video/*", false)}
      </div>
      {live && (
        <button className="capture-shoot" aria-label="유물 촬영하기" onClick={shoot} disabled={busy}>
          {busy ? "확인 중…" : "촬영"}
        </button>
      )}
    </main>
  );
}
