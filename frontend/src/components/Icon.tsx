// 장식용 아이콘 (TalkBack은 읽지 않는다: aria-hidden). 라이브러리 추가 없이 SVG 경로만 둔다.
const PATHS = {
  touch:
    "M9 11.24V7.5a2.5 2.5 0 0 1 5 0v3.74c1.21-.81 2-2.18 2-3.74a4.5 4.5 0 0 0-9 0c0 1.56.79 2.93 2 3.74zm9.84 4.63-4.54-2.26a1.4 1.4 0 0 0-.54-.11H13v-6a1.5 1.5 0 0 0-3 0v10.74l-3.43-.72-.24-.03c-.31 0-.59.13-.79.33l-.79.8 4.94 4.94c.27.27.65.44 1.06.44h6.79c.75 0 1.33-.55 1.44-1.28l.75-5.27.02-.2c0-.62-.38-1.16-.91-1.38z",
  eye: "M12 4.5C7 4.5 2.7 7.6 1 12c1.7 4.4 6 7.5 11 7.5s9.3-3.1 11-7.5c-1.7-4.4-6-7.5-11-7.5zM12 17a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  check: "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z",
  back: "M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6z",
  play: "M8 5v14l11-7z",
  pause: "M6 19h4V5H6zm8-14v14h4V5z",
  mic: "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z",
  info: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2zm0-8h-2V7h2z",
  person: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
} as const;

export type IconName = keyof typeof PATHS | "eyeOff";

export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d={PATHS[name === "eyeOff" ? "eye" : name]} />
      {name === "eyeOff" && <path d="M3 3l18 18" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />}
    </svg>
  );
}
