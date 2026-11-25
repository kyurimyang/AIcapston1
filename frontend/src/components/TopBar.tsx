import { Icon } from "./Icon";
import { PageTitle } from "./PageTitle";

// 화면 위쪽 막대: 왼쪽 뒤로 버튼, 가운데 제목 (슬라이드 14쪽 화면 구성)
export function TopBar({ title, back, onBack }: { title: string; back: string; onBack: () => void }) {
  return (
    <header className="topbar">
      <button className="topbar-back" aria-label={back} onClick={onBack}>
        <Icon name="back" size={28} />
        <span aria-hidden="true">{back}</span>
      </button>
      <PageTitle>{title}</PageTitle>
      <span className="topbar-spacer" aria-hidden="true" />
    </header>
  );
}
