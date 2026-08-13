/**
 * 브리핑.
 *
 * 처음엔 검인(체크 도장)을 썼다. "검수했다" 는 약속을 그린 것이었는데,
 * 체크박스는 어디에나 있는 모양이라 이 서비스의 것으로 읽히지 않았다.
 *
 * 이 서비스가 하는 일은 하나다. **매일 아침, 무엇이 바뀌었는지 짚어
 * 말해 준다.** 그래서 말풍선이고, 그 안에 요약 세 줄이 있다.
 *
 * 가운데 줄만 굵고 짧다. 그게 **바뀐 줄**이다 — 조문 신구 대조에서
 * 실제로 하는 일이고, 사장님이 알고 싶은 그 한 줄이다. 색을 두 벌
 * 쓰지 않고 굵기로만 구분하므로 흑백으로 봐도 읽힌다 (NFR-013).
 *
 * `currentColor` 로만 그린다. 짙은 바탕에서는 흰색으로, 흰 바탕에서는
 * 먹색으로 저절로 따라간다.
 *
 * 파비콘은 `app/icon.svg` 에 따로 있다. 브라우저 탭은 배경을 물려주지
 * 않아 바탕을 직접 칠해야 한다.
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
      {/*
        말풍선. 왼쪽 아래로 꼬리가 내려간다 — 누가 나에게 말해 주는
        모양이다. 내가 쓰는 메모가 아니라 받는 브리핑이다.
      */}
      <path
        d="M6.6 4.5h18.8a2.6 2.6 0 0 1 2.6 2.6v12.6a2.6 2.6 0 0 1-2.6 2.6H12.4l-5.1 4.6a.9.9 0 0 1-1.5-.67V22.3H6.6A2.6 2.6 0 0 1 4 19.7V7.1a2.6 2.6 0 0 1 2.6-2.6Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      {/* 요약 세 줄. 가운데가 바뀐 줄이라 굵고 짧다. */}
      <path d="M9.4 10.4h13.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M9.4 14.2h7.6" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" />
      <path d="M9.4 18h10.4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

/**
 * 마크 + 글자.
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
