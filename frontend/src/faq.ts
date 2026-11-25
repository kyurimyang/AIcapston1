// 자주 묻는 질문: 음성 인식이나 LLM(/ask)이 안 될 때도 바로 답할 수 있게 미리 써 둔 답.
// 근거는 국가유산포털 원문(backend/scripts/artifact_meta.json)뿐이다. 검수(reviewed=true)한 것만 화면에 나온다.
export interface Faq { q: string; a: string; reviewed: boolean }

const DIFF = "78호는 화려한 관을 쓰고 손가락 끝을 뺨에 대고 있어요. 83호는 둥근 산 세 개 모양의 관을 쓰고, 손가락으로 턱을 괴고 있어요. 83호는 윗몸에 옷 없이 두 줄 목걸이만 걸쳤어요.";

const FAQ: Record<string, Faq[]> = {
  A01: [
    { q: "크기는 얼마나 돼요?", a: "높이는 80센티미터예요. 보통 책상보다 조금 높은 정도예요.", reviewed: true },
    { q: "언제 만들었어요?", a: "삼국시대, 6세기 중엽이나 그 직후에 만든 것으로 봐요.", reviewed: true },
    { q: "손 모양은 어때요?", a: "오른쪽 팔꿈치를 오른쪽 무릎에 얹고, 손가락 끝을 뺨에 대고 있어요. 손은 몸에 비해 큼직한 편이에요.", reviewed: true },
    { q: "머리에 쓴 건 뭐예요?", a: "화려한 관을 쓰고 있고, 관에서 내려온 장식 두 가닥이 양쪽 어깨까지 닿아요.", reviewed: true },
    { q: "어떻게 박물관에 오게 됐어요?", a: "1912년에 일본인이 입수해 조선총독부에 기증했고, 1916년에 총독부박물관으로 옮겨졌어요. 지금은 국립중앙박물관에 있어요.", reviewed: true },
    { q: "83호와 뭐가 달라요?", a: DIFF, reviewed: true },
  ],
  B01: [
    { q: "크기는 얼마나 돼요?", a: "높이는 93.5센티미터예요. 국보 78호와 함께 우리나라 금동반가사유상 가운데 가장 커요.", reviewed: true },
    { q: "언제 만들었어요?", a: "국보 78호보다 늦은 삼국시대 후기에 만든 것으로 봐요.", reviewed: true },
    { q: "손 모양은 어때요?", a: "왼손으로 올린 오른쪽 발목을 잡고, 오른손은 팔꿈치를 무릎에 얹은 채 손가락으로 턱을 살며시 괴고 있어요.", reviewed: true },
    { q: "머리에 쓴 건 뭐예요?", a: "둥근 산 세 개를 나란히 세운 모양의 관을 쓰고 있어서, 삼산반가사유상이라고도 불러요.", reviewed: true },
    { q: "어디서 발견됐어요?", a: "1920년대에 경주에서 발견되었다고 전하지만, 확실한 기록은 없어요.", reviewed: true },
    { q: "78호와 뭐가 달라요?", a: DIFF, reviewed: true },
  ],
};

export function faqFor(artifactId: string): Faq[] {
  return (FAQ[artifactId] ?? []).filter((f) => f.reviewed);
}
