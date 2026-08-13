/**
 * 검인(檢印).
 *
 * 이 서비스가 다른 세무 뉴스 모음과 갈리는 지점은 하나다 —
 * **공식 원문으로 확인하고 세무전문가가 검수한 것만 올린다.**
 * 그 약속을 그림으로 만든 것이다. 관공서 문서에 찍히는 도장이고,
 * 그래서 살짝 기울어 있다. 반듯하면 체크박스가 되고, 체크박스는
 * "고를 수 있는 것" 으로 읽힌다. 이건 이미 찍힌 표시다.
 *
 * `currentColor` 로만 그린다. 짙은 남색 밴드에서는 흰색으로, 흰 바탕
 * 화면에서는 먹색으로 저절로 따라간다 — 색을 두 벌 관리하지 않는다.
 *
 * 파비콘은 `app/icon.svg` 에 따로 있다. 브라우저 탭에서는 배경을
 * 못 물려받아 남색 바탕을 직접 칠해야 한다.
 */
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
      className="shrink-0"
    >
      <g transform="rotate(-7 16 16)">
        <rect
          x="3.6"
          y="3.6"
          width="24.8"
          height="24.8"
          rx="6.4"
          stroke="currentColor"
          strokeWidth="2.6"
        />
        <path
          d="M10.6 16.5l3.9 3.9 7.2-8.2"
          stroke="currentColor"
          strokeWidth="2.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}

/**
 * 마크 + 글자.
 *
 * 글자에서 "Tax" 만 굵기를 살린다. 사장님이 기억하는 것은 그 세 글자다.
 */
export function Wordmark({ tone = 'light' }: { tone?: 'light' | 'dark' }) {
  return (
    <span className="flex items-center gap-2.5">
      <Logo />
      <span
        className={`text-[19px] font-extrabold tracking-[-0.03em] ${
          tone === 'light' ? 'text-white' : 'text-ink'
        }`}
      >
        TaxBriefing
      </span>
    </span>
  );
}
