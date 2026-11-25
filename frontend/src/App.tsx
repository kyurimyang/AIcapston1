import { useEffect, useState } from "react";
import Ask from "./pages/Ask";
import Capture from "./pages/Capture";
import Narration from "./pages/Narration";
import Onboarding from "./pages/Onboarding";

// 라우터 라이브러리 없이 해시 라우팅 (라이브러리 추가 금지)
const current = () => window.location.hash.slice(1) || "/";

export default function App() {
  const [path, setPath] = useState(current());

  useEffect(() => {
    const on = () => setPath(current());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = (p: string) => { window.location.hash = p; };

  // 앱을 열면 항상 설정(온보딩)부터. 저장된 설정이 있으면 그 값이 미리 선택돼 있어 "시작하기"만 누르면 된다
  if (path === "/") return <Redirect to="/onboarding" go={go} />;
  if (path === "/onboarding") return <Onboarding go={go} />;
  if (path === "/capture") return <Capture go={go} />;
  if (path === "/narration") return <Narration go={go} />;
  if (path === "/ask") return <Ask go={go} />;
  return <Redirect to="/" go={go} />;
}

function Redirect({ to, go }: { to: string; go: (p: string) => void }) {
  useEffect(() => go(to), []);
  return null;
}
