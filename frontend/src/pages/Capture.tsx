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
  const [status, setStatus] = useState("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    const noCamera = () => {
      setCamera("off");
      speak("카메라를 쓸 수 없어요. 사진 올리기 버튼을 눌러 주세요");
    };
    // HTTPS가 아니면(ngrok 없이 접속) mediaDevices 자체가 없다
    if (!navigator.mediaDevices?.getUserMedia) noCamera();
    else
      navigator.mediaDevices
        .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false })
        .then((s) => {
          if (cancelled) return s.getTracks().forEach((t) => t.stop());
          stream = s;
          if (video.current) video.current.srcObject = s;
          setCamera("on");
          speak("화면 아래쪽 절반을 누르면 촬영해요");
        })
        .catch(() => !cancelled && noCamera());
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop()); // 다른 화면으로 가면 카메라를 끈다
    };
  }, []);

  const send = async (getImage: () => Promise<Blob>) => {
    if (busy) return;
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
      setBusy(false);
    }
  };

  const shoot = () => video.current && video.current.videoWidth > 0 && send(() => captureFrame(video.current!));

  return (
    <main className="capture">
      <video ref={video} className="capture-preview" autoPlay playsInline muted aria-hidden="true" />
      <div className="capture-top">
        <PageTitle>유물 촬영</PageTitle>
        <div aria-live="polite">{status}</div>
        <button aria-label="설정 바꾸기" onClick={() => go("/onboarding")}>설정 바꾸기</button>
        {camera === "off" && (
          <label className="upload">
            사진 올리기
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = ""; // 같은 사진을 다시 골라도 onChange가 오게
                if (f) send(() => resizeFile(f));
              }}
            />
          </label>
        )}
      </div>
      {camera === "on" && (
        <button className="capture-shoot" aria-label="유물 촬영하기" onClick={shoot} disabled={busy}>
          {busy ? "확인 중…" : "촬영"}
        </button>
      )}
    </main>
  );
}
