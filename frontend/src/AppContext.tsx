import { createContext, useContext, useState, type ReactNode } from "react";
import type { Length, Profile, RecognizeResult } from "./api";

interface Settings { profile: Profile; length: Length }

interface AppState {
  settings: Settings | null;
  saveSettings: (s: Settings) => void;
  result: RecognizeResult | null;
  setResult: (r: RecognizeResult | null) => void;
  /** 마지막으로 찍은 사진 (해설 화면 썸네일). 서버에 저장하지 않고 이 폰 메모리에만 있다 */
  photo: string | null;
  setPhoto: (blob: Blob) => void;
}

const KEY = "yudam.settings";
const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(() => {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  });
  const [result, setResult] = useState<RecognizeResult | null>(null);
  const [photo, setPhotoUrl] = useState<string | null>(null);

  const saveSettings = (s: Settings) => {
    localStorage.setItem(KEY, JSON.stringify(s));
    setSettings(s);
  };

  const setPhoto = (blob: Blob) =>
    setPhotoUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(blob);
    });

  return (
    <Ctx.Provider value={{ settings, saveSettings, result, setResult, photo, setPhoto }}>{children}</Ctx.Provider>
  );
}

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppProvider 안에서 써야 해요");
  return v;
}
