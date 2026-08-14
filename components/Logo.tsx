/**
 * 달력 · 마감.
 *
 * 로고를 세 번 갈아엎고 나서야 여기 왔다. 검인(체크)은 어디에나 있는
 * 모양이었고, 말풍선은 메신저로 읽혔다. 둘 다 이 서비스의 것이 아니었다.
 *
 * **세무는 날짜 사업이다.** 실무자의 하루를 굴리는 것은 신고 기한이고,
 * 이 서비스가 파는 것도 "언제까지 뭘 해야 하는지 남보다 먼저 아는 것"
 * 이다. 그래서 달력이고, 붉은 점 하나가 그 마감일이다.
 *
 * **격자를 그리지 않는다.** 달력 아이콘에 흔히 들어가는 칸 나눔을 빼고
 * 점 하나만 남겼다. 두 가지를 얻었다 — 흔한 달력 아이콘과 달라 보이고,
 * 16px 로 줄여도 그 점은 끝까지 남는다. ₩ 나 稅 는 그 크기에서 획이
 * 뭉개져 무슨 글자인지 알 수 없었다. 로고는 작을 때 살아남아야 로고다.
 *
 * 테두리는 `currentColor` 라 바탕을 따라가고 **붉은 점만 고정색**이다.
 * 마감이라는 뜻이 배경색에 따라 흔들리면 안 된다.
 */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
      className="shrink-0"
    >
      <rect x="4" y="7" width="24" height="21" rx="5.5" stroke="currentColor" strokeWidth="2.6" />
      {/* 고리 두 개. 이것만으로 달력이 된다. */}
      <path d="M10.5 3.8v5M21.5 3.8v5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      {/* 마감일. 이 색만 바탕을 따라가지 않는다. */}
      <circle cx="16" cy="19.6" r="3.4" fill="var(--danger, #ef4452)" />
    </svg>
  );
}

/**
 * 마크 + 글자.
 *
 * 글자는 HTML 로 둔다. SVG 안에 넣으면 Pretendard 가 없는 곳에서
 * 엉뚱한 글꼴로 나오고, 그럴 바엔 브라우저가 고르게 두는 편이 낫다.
 */
export function Wordmark({
  tone = 'light',
  size = 28,
}: {
  tone?: 'light' | 'dark';
  size?: number;
}) {
  return (
    <span className="flex items-center gap-2.5">
      <Logo size={size} />
      <span
        className={`text-[20px] font-extrabold tracking-[-0.035em] ${
          tone === 'light' ? 'text-white' : 'text-ink'
        }`}
      >
        TaxBriefing
      </span>
    </span>
  );
}
