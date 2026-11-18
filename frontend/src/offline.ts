// 서버 없이도 해설을 들려주기 위한 폴백. 서버와 같은 원본(backend/scripts/narrations.json)을 빌드에 묶는다.
// 검수 완료(reviewed=true)된 해설만 쓴다 — 서버의 /narration과 같은 규칙.
import narrations from "../../backend/scripts/narrations.json";
import type { Length, Profile } from "./api";

interface Narration { artifact_id: string; profile: string; length: string; text: string; reviewed: boolean }

export function bundledNarration(artifactId: string, profile: Profile, length: Length): string | null {
  const n = (narrations as Narration[]).find(
    (x) => x.artifact_id === artifactId && x.profile === profile && x.length === length && x.reviewed,
  );
  return n?.text ?? null;
}
