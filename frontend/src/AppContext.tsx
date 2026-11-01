import { createContext, useContext, useState, type ReactNode } from "react";
import type { Length, Profile, RecognizeResult } from "./api";

interface Settings { profile: Profile; length: Length }

interface AppState {
  settings: Settings | null;
  saveSettings: (s: Settings) => void;
  result: RecognizeResult | null;
  setResult: (r: RecognizeResult | null) => void;
}

const KEY = "yudam.settings";
const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(() => {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  });
  const [result, setResult] = useState<RecognizeResult | null>(null);

  const saveSettings = (s: Settings) => {
    localStorage.setItem(KEY, JSON.stringify(s));
    setSettings(s);
  };

  return <Ctx.Provider value={{ settings, saveSettings, result, setResult }}>{children}</Ctx.Provider>;
}

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppProvider 안에서 써야 해요");
  return v;
}
