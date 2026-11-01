import { useEffect, useState } from "react";
import { useApp } from "./AppContext";
import Ask from "./pages/Ask";
import Capture from "./pages/Capture";
import Narration from "./pages/Narration";
import Onboarding from "./pages/Onboarding";

// 라우터 라이브러리 없이 해시 라우팅 (라이브러리 추가 금지)
const current = () => window.location.hash.slice(1) || "/";

export default function App() {
  const { settings } = useApp();
  const [path, setPath] = useState(current());

  useEffect(() => {
    const on = () => setPath(current());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = (p: string) => { window.location.hash = p; };

  // 저장된 프로필이 있으면 온보딩을 건너뛴다
  if (path === "/") return <Redirect to={settings ? "/capture" : "/onboarding"} go={go} />;
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
