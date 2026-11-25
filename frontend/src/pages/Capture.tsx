import { useEffect, useRef, useState } from "react";
import { recognize } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { TopBar } from "../components/TopBar";
import { captureFrame, fromFile } from "../image";
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
// 방향 안내("조금 왼쪽으로")와 자동 촬영은 하지 않는다: 유물 위치를 찾는 기능(객체 탐지)이 없다.
export default function Capture({ go }: { go: (path: string) => void }) {
  const { setResult, setPhoto } = useApp();
  const video = useRef<HTMLVideoElement>(null);
  const [camera, setCamera] = useState<Camera>("starting");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(READY);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    const noCamera = () => {
      setCamera("off");
      setStatus("카메라를 쓸 수 없어요. 사진·영상 올리기를 눌러 주세요");
      speak("카메라를 쓸 수 없어요. 사진·영상 올리기 버튼을 눌러 주세요");
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
          speak(`${READY}. 화면 아래쪽 절반을 누르면 촬영해요`);
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
      setBusy(false);
    }
  };

  const shoot = () => video.current && video.current.videoWidth > 0 && send(() => captureFrame(video.current!));

  return (
    <main className="capture">
      <video ref={video} className="capture-preview" autoPlay playsInline muted aria-hidden="true" />

      <TopBar title="사유의 방" back="설정" onBack={() => go("/onboarding")} />

      {camera === "on" && (
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

        {camera === "on" && (
          <button className="capture-shoot" aria-label="유물 촬영하기" onClick={shoot} disabled={busy}>
            <span className="shutter" aria-hidden="true">{busy ? "확인 중" : ""}</span>
          </button>
        )}
        {/* 사진·영상 첨부: 카메라가 있어도 항상 둔다 (갤러리에서 고르기). 영상은 가운데 장면 한 장으로 인식 */}
        <label className={camera === "off" ? "upload" : "upload upload-secondary"}>
          사진·영상 올리기
          <input
            type="file"
            accept="image/*,video/*"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = ""; // 같은 파일을 다시 골라도 onChange가 오게
              if (f) send(() => fromFile(f));
            }}
          />
        </label>
      </div>
    </main>
  );
}
