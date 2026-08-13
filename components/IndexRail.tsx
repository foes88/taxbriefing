'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import type { IndustryBucket, MonthBucket } from '@/lib/types';

/**
 * 왼쪽 레일.
 *
 * **위는 목적지, 아래는 업종, 맨 아래가 보관함이다.**
 *
 * 예전에는 업종 12줄과 공포월 12줄이 전부 숫자를 달고 세로로 서 있었다.
 * 그건 필터를 메뉴처럼 세워 놓은 것이고, 화면이 정보 서비스가 아니라
 * 데이터베이스 브라우저로 읽힌다. 참고한 서비스들(Deloitte tax@hand,
 * EY Tax Alerts, GOV.UK) 중 어느 곳도 첫 화면 왼쪽에 분류 트리를 세우지 않는다.
 *
 * 왼쪽은 "어디로 갈까"를 답해야 하고, "지금 목록을 좁히기"는 목록 위에 있어야 한다.
 *
 * 업종은 남긴다. 세무 실무자에게는 이게 상시 탐색축이지 가끔 켜는 필터가
 * 아니기 때문이다. 다만 목적지 아래로 내리고, 공포월은 접어 둔다 —
 * 매일 쓰는 것과 가끔 뒤지는 것은 같은 무게일 수 없다.
 */
export function IndexRail({
  industries,
  months,
  upcomingCount,
}: {
  industries: IndustryBucket[];
  months: MonthBucket[];
  upcomingCount?: number;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const activeIndustries = params.getAll('industries');
  const activeMonth = params.get('month');
  const total = months.reduce((sum, m) => sum + m.count, 0);

  const go = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    next.delete('show'); // 좁히면 처음부터 다시 본다
    if (key === 'month') {
      next.delete('from');
      next.delete('to');
    }
    if (value === null) {
      next.delete(key);
    } else if (next.getAll(key).includes(value)) {
      const rest = next.getAll(key).filter((v) => v !== value);
      next.delete(key);
      rest.forEach((v) => next.append(key, v));
    } else if (key === 'month') {
      next.set(key, value);
    } else {
      next.append(key, value);
    }
    router.push(next.toString() ? `/?${next}` : '/');
  };

  return (
    <nav aria-label="탐색" className="flex flex-col gap-7">
      <ul className="flex flex-col">
        <Destination href="/" label="오늘의 브리핑" current={pathname === '/'} />
        <Destination
          href="/upcoming"
          label="시행 예정"
          count={upcomingCount}
          current={pathname === '/upcoming'}
        />
        <Destination href="/news" label="뉴스" current={pathname === '/news'} />
      </ul>

      {industries.length > 0 ? (
        <section>
          <RailHeading>업종</RailHeading>
          <ul className="mt-1">
            {industries.map((item) => (
              <li key={item.code}>
                <RailRow
                  label={item.label}
                  count={item.count}
                  active={activeIndustries.includes(item.code)}
                  onClick={() => go('industries', item.code)}
                />
              </li>
            ))}
          </ul>
          {activeIndustries.length > 0 ? (
            <button
              type="button"
              onClick={() => go('industries', null)}
              className="mt-1.5 px-1 text-[12.5px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
            >
              업종 해제
            </button>
          ) : null}
        </section>
      ) : null}

      {/*
        공포월은 접어 둔다. 매일 쓰는 축이 아니라 "그때 그거" 를 뒤질 때 쓴다.
        details 를 쓰면 자바스크립트 없이도 열리고, 월을 고른 상태면 열린 채로 나온다.
      */}
      {months.length > 0 ? (
        <details open={Boolean(activeMonth)} className="group">
          <summary className="flex cursor-pointer items-center justify-between border-b-2 border-band px-1 pb-2 marker:content-['']">
            <span className="label text-ink">지난 공포분</span>
            <span aria-hidden className="text-[11px] text-ink-3 group-open:hidden">
              펼치기
            </span>
          </summary>
          <ul className="mt-1">
            <li>
              <RailRow
                label="전체 기간"
                count={total}
                active={!activeMonth}
                onClick={() => go('month', null)}
              />
            </li>
            {groupByYear(months).map((group) => (
              <li key={group.year}>
                <p className="tabular mt-3 border-b border-rule px-1 pb-1 text-[11.5px] font-extrabold text-ink">
                  {group.year}년
                </p>
                <ul>
                  {group.months.map((m) => (
                    <li key={m.month}>
                      <RailRow
                        label={`${Number(m.month.slice(5, 7))}월`}
                        count={m.count}
                        important={m.important}
                        active={activeMonth === m.month}
                        onClick={() => go('month', m.month)}
                      />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </nav>
  );
}

/** 목적지. 필터와 달리 **페이지가 바뀐다** — 그래서 링크이고, 숫자를 붙이지 않는다. */
function Destination({
  href,
  label,
  count,
  current,
}: {
  href: string;
  label: string;
  count?: number;
  current: boolean;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={current ? 'page' : undefined}
        className={`flex items-baseline justify-between gap-2 border-l-[3px] py-2 pl-2.5 pr-1 text-[14.5px] transition-colors ${
          current
            ? 'border-accent bg-accent-soft font-bold text-accent'
            : 'border-transparent font-semibold text-ink-2 hover:border-rule-strong hover:text-ink'
        }`}
      >
        {label}
        {count ? (
          <span className={`tabular text-[13px] ${current ? 'text-accent' : 'text-ink-3'}`}>
            {count}
          </span>
        ) : null}
      </Link>
    </li>
  );
}

function RailHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="border-b-2 border-band px-1 pb-2">
      <span className="label text-ink">{children}</span>
    </h2>
  );
}

function RailRow({
  label,
  count,
  important,
  active,
  onClick,
}: {
  label: string;
  count: number;
  important?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex w-full items-baseline justify-between gap-2 border-l-[3px] py-1.5 pl-2.5 pr-1 text-left transition-colors ${
        active
          ? 'border-accent bg-accent-soft font-bold text-accent'
          : 'border-transparent text-ink-2 hover:border-rule-strong hover:text-ink'
      }`}
    >
      <span className="min-w-0 truncate text-[14px]">{label}</span>
      <span className="flex shrink-0 items-baseline gap-1.5">
        {important ? (
          <span className="tabular text-[12px] font-bold text-seal">{important}</span>
        ) : null}
        <span className={`tabular text-[13px] ${active ? 'text-accent' : 'text-ink-3'}`}>
          {count}
        </span>
      </span>
    </button>
  );
}

interface YearGroup {
  year: string;
  months: MonthBucket[];
}

function groupByYear(months: MonthBucket[]): YearGroup[] {
  const map = new Map<string, MonthBucket[]>();
  months.forEach((m) => {
    const year = m.month.slice(0, 4);
    map.set(year, [...(map.get(year) ?? []), m]);
  });

  return Array.from(map.entries())
    .map(([year, list]) => ({
      year,
      // 같은 해 안에서는 최신 월이 위로 온다 — 새 소식을 먼저 본다.
      months: [...list].sort((a, b) => b.month.localeCompare(a.month)),
    }))
    .sort((a, b) => b.year.localeCompare(a.year));
}
