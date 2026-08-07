import Link from 'next/link';

/**
 * 제호와 탭을 하나의 짙은 밴드로 묶는다.
 *
 * 흰 바탕만 이어지면 화면에 시작점이 없다. 앞선 시안은 제호도 탭도 흰
 * 바탕이라 스크롤하면 어디까지가 머리이고 어디부터가 내용인지 흐려졌다.
 * 밴드 하나로 그 경계를 만든다 — 페이지를 어둡게 하는 것과는 다른 얘기다.
 *
 * 탭이 이 안에 들어오는 이유: 정책과 뉴스는 **서로 다른 화면**이지
 * 한 화면의 필터가 아니다. 탐색 층위에 있어야 할 것이 내용 층위에 있으면
 * 스크롤할 때 같이 밀려 올라간다.
 */
export function Masthead({
  active,
  compact = false,
}: {
  active?: 'policy' | 'news';
  compact?: boolean;
}) {
  return (
    <header className="bg-band text-white">
      <div className="mx-auto flex max-w-page items-center justify-between gap-4 px-4 py-3.5">
        <Link href="/" className="flex items-baseline gap-3">
          <span className="text-[19px] font-extrabold tracking-[-0.03em]">TaxBriefing</span>
          {!compact ? (
            <span className="hidden border-l border-white/20 pl-3 text-[12.5px] font-medium text-white/60 sm:inline">
              공식 원문으로 확인한 세무 브리핑
            </span>
          ) : null}
        </Link>

        <Link
          href="/admin"
          className="shrink-0 text-[12.5px] font-semibold text-white/60 transition-colors hover:text-white"
        >
          관리자
        </Link>
      </div>

      {active ? (
        <nav aria-label="구분" className="mx-auto max-w-page px-4">
          <div className="flex gap-1">
            <Tab href="/" label="정책·법령" note="검수 완료" current={active === 'policy'} />
            <Tab href="/news" label="뉴스" note="확인 전" current={active === 'news'} unverified />
          </div>
        </nav>
      ) : null}
    </header>
  );
}

/**
 * 활성 탭은 아래 흰 화면과 이어 붙인다 — 탭이 그 화면의 손잡이라는 뜻이다.
 *
 * 두 탭의 성격이 다르므로 부제 색을 다르게 둔다. 정책은 검수를 거친 것이고
 * 뉴스는 아니다. 같은 색으로 칠하면 두 탭이 같은 무게로 읽히고,
 * 그게 이 서비스에서 가장 위험한 오해다.
 */
function Tab({
  href,
  label,
  note,
  current,
  unverified = false,
}: {
  href: string;
  label: string;
  note: string;
  current: boolean;
  unverified?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`flex items-baseline gap-2 rounded-t-[4px] px-3.5 pb-2.5 pt-2 transition-colors ${
        current ? 'bg-paper' : 'hover:bg-white/10'
      }`}
    >
      <span
        className={`text-[14.5px] font-bold tracking-tight ${
          current ? 'text-ink' : 'text-white/70'
        }`}
      >
        {label}
      </span>
      <span
        className={`text-[11.5px] font-semibold ${
          current
            ? unverified
              ? 'text-state-pending'
              : 'text-state-effective'
            : 'text-white/40'
        }`}
      >
        {note}
      </span>
    </Link>
  );
}
