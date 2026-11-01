import { useState } from "react";
import { recognize } from "../api";
import { useApp } from "../AppContext";
import { PageTitle } from "../components/PageTitle";
import { speak } from "../speech";

// TODO(혜진): getUserMedia 전체 화면 미리보기 + 하단 절반 촬영 버튼,
// 전송 전 긴 변 512~768px로 리사이즈
export default function Capture({ go }: { go: (path: string) => void }) {
  const { setResult } = useApp();
  const [status, setStatus] = useState("");

  const onFile = async (file: File) => {
    setStatus("확인하고 있어요");
    speak("확인하고 있어요");
    try {
      const r = await recognize(file);
      setResult(r);
      if (r.status === "ok") return go("/narration");
      const msg =
        r.status === "uncertain"
          ? "반가사유상 종류로 보여요. 조금 더 가까이에서 다시 찍어 주세요"
          : "유물을 찾지 못했어요. 정면에서 다시 찍어 주세요";
      setStatus(msg);
      speak(msg);
    } catch {
      setStatus("연결이 불안정해요. 다시 시도해 주세요");
      speak("연결이 불안정해요. 다시 시도해 주세요");
    }
  };

  return (
    <main>
      <PageTitle>유물 촬영</PageTitle>
      <label>
        이미지 업로드
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
      </label>
      <button aria-label="설정 바꾸기" onClick={() => go("/onboarding")}>설정 바꾸기</button>
      <div aria-live="polite">{status}</div>
    </main>
  );
}
