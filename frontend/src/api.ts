// API 호출은 이 파일에만 모은다. 형식은 CLAUDE.md 6장 기준.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Profile = "congenital" | "acquired" | "low_vision";
export type Length = "short" | "long";

export interface RecognizeResult {
  status: "ok" | "uncertain" | "reject";
  artifact_id?: string;
  name?: string;
  score?: number;
  message?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const call = async () => {
    const res = await fetch(`${BASE}${path}`, { ...init, signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  };
  try {
    return await call();
  } catch {
    return await call(); // 타임아웃·연결 실패 시 1회 자동 재시도
  }
}

export function recognize(image: Blob) {
  const form = new FormData();
  form.append("image", image, "photo.jpg");
  return request<RecognizeResult>("/recognize", { method: "POST", body: form });
}

export function getNarration(artifactId: string, profile: Profile, length: Length) {
  const q = new URLSearchParams({ artifact_id: artifactId, profile, length });
  return request<{ text: string; reviewed: boolean }>(`/narration?${q}`);
}

export function ask(artifactId: string, profile: Profile, question: string) {
  return request<{ answer: string; sources: string[]; grounded: boolean }>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artifact_id: artifactId, profile, question }),
  });
}
