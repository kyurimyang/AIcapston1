import { useEffect, useRef } from "react";

// 화면이 바뀌면 포커스를 제목으로 옮긴다 (TalkBack)
export function PageTitle({ children }: { children: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
