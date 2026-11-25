// 시각 경험·해설 길이의 화면 문구. 온보딩·해설·질문 화면이 같이 쓴다.
import type { IconName } from "./components/Icon";
import type { Length, Profile } from "./api";
import meta from "../../backend/scripts/artifact_meta.json";

export const PROFILES: { value: Profile; label: string; desc: string; how: string; icon: IconName }[] = [
  { value: "congenital", label: "선천 전맹", desc: "태어날 때부터 앞이 보이지 않았어요", how: "몸으로 따라 하는 자세와 크기 비교로 설명해요", icon: "touch" },
  { value: "acquired", label: "후천 전맹", desc: "예전에는 볼 수 있었어요", how: "기억하는 모양을 떠올리도록 설명해요", icon: "eyeOff" },
  { value: "low_vision", label: "저시력", desc: "조금 볼 수 있어요", how: "위에서 아래 순서로 찾기 쉽게 설명해요", icon: "eye" },
];

export const LENGTHS: { value: Length; label: string; desc: string; spoken: string }[] = [
  { value: "short", label: "짧게", desc: "핵심만 · 약 30초", spoken: "짧은 해설" },
  { value: "long", label: "자세히", desc: "자세하게 · 약 1분 30초", spoken: "자세한 해설" },
];

export const profileOf = (p: Profile) => PROFILES.find((x) => x.value === p)!;
export const lengthOf = (l: Length) => LENGTHS.find((x) => x.value === l)!;

interface Meta { era?: string | null; material?: string | null; size?: string | null }

/** 해설 화면의 태그 (시대 · 재질 · 크기). 근거는 국가유산포털 원문(artifact_meta.json) */
export function tagsFor(artifactId: string): string[] {
  const m = (meta as Record<string, Meta>)[artifactId];
  return m ? [m.era, m.material, m.size].filter((x): x is string => !!x) : [];
}
