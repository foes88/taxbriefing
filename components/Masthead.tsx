import Link from 'next/link';

import { Logo } from './Logo';

/**
 * 머리글과 메뉴.
 *
 * **메뉴를 자료 종류가 아니라 쓰는 순간으로 나눈다.**
 *
 * 예전 탭은 「정책·법령 / 실무 TIP / 뉴스」였다. 그건 우리 서류함
 * 분류지 세무사무소 직원이 일하는 순서가 아니다. 그래서 "왼쪽 메뉴가
 * 너무 애매해" 라는 말이 나왔고, 실제로 애매했다 — 아침에 화면을 열면
 * 세 탭을 다 눌러 봐야 오늘 뭐가 있는지 알 수 있었다.
 *
 * 쓰는 순간은 셋이다.
 *
 *   오늘  — 아침에 한 번. 지금 알아야 할 것.
 *   일정  — 앞으로 닥치는 것. 미리 준비할 것.
 *   찾기  — 상담 중에. "학원 4대보험" 하고 즉석에서.
 *
 * 심판례와 뉴스는 탭이 아니라 **찾기의 종류 칩**이 되고, 오늘 화면의
 * 한 구획이 된다. 종류로 나눠 두면 종류를 알아야 찾을 수 있는데,
 * 상담 중에는 그걸 모른 채 찾는다.
 *
 * 밴드는 걷어냈다. 짙은 남색 띠가 화면 맨 위를 20% 먹고 있었는데,
 * 거기 담긴 정보는 서비스 이름 하나뿐이었다.
 */
const TABS = [
  { href: '/', label: '오늘', key: 'today' },
  { href: '/upcoming', label: '일정', key: 'schedule' },
  { href: '/search', label: '찾기', key: 'search' },
] as const;

export type Tab = (typeof TABS)[number]['key'];

export function Masthead({ active }: { active?: Tab }) {
  return (
    <header className="sticky top-0 z-20 bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-page items-center gap-1 px-4 pt-3">
        <Link href="/" className="flex shrink-0 items-center gap-2 pr-2 text-ink">
          <Logo size={22} />
          <span className="text-[17px] font-extrabold tracking-[-0.03em]">TaxBriefing</span>
        </Link>

        <Link
          href="/admin"
          className="ml-auto shrink-0 px-2 text-meta font-semibold text-ink-3 transition-colors hover:text-ink"
        >
          관리자
        </Link>
      </div>

      {active ? (
        <nav aria-label="메뉴" className="mx-auto max-w-page px-2 pb-1 pt-1.5">
          <div className="rail px-2">
            {TABS.map((tab) => {
              const on = tab.key === active;
              return (
                <Link
                  key={tab.key}
                  href={tab.href}
                  aria-current={on ? 'page' : undefined}
                  className={`shrink-0 rounded-full px-4 py-2 text-[15px] font-bold transition ${
                    on ? 'bg-ink text-white' : 'text-ink-3 hover:bg-surface hover:text-ink-2'
                  }`}
                >
                  {tab.label}
                </Link>
              );
            })}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
