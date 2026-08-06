'use client';

import { useRouter, useSearchParams } from 'next/navigation';

import type { MonthBucket } from '@/lib/types';

/**
 * 연도·월 아카이브 (공포월 기준).
 *
 * 사업자는 "몇 월 개정"으로 기억한다 — "7월에 바뀐 거 뭐였지?"
 * 그래서 월이 1급 탐색 축이고, 연도가 바뀌면 목록도 그 해 것만 따로 묶인다.
 * 중요 건수를 함께 보여줘야 그 달을 열어볼지 판단할 수 있다.
 */

interface YearGroup {
  year: string;
  months: MonthBucket[];
  count: number;
  important: number;
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
      count: list.reduce((sum, m) => sum + m.count, 0),
      important: list.reduce((sum, m) => sum + m.important, 0),
    }))
    .sort((a, b) => b.year.localeCompare(a.year));
}

function useMonthNavigation() {
  const router = useRouter();
  const params = useSearchParams();

  const go = (month: string | null) => {
    const next = new URLSearchParams(params.toString());
    // 월을 고르면 기간 검색은 해제한다 — 둘이 겹치면 결과를 설명할 수 없다.
    next.delete('from');
    next.delete('to');
    if (month === null || next.get('month') === month) next.delete('month');
    else next.set('month', month);
    router.push(next.toString() ? `/?${next}` : '/');
  };

  return go;
}

export function MonthNav({ months, active }: { months: MonthBucket[]; active?: string }) {
  const go = useMonthNavigation();
  if (months.length === 0) return null;

  const years = groupByYear(months);
  const total = months.reduce((sum, m) => sum + m.count, 0);

  return (
    <nav aria-label="연도·월별 보기" className="border border-rule bg-surface">
      <h2 className="border-b border-rule px-4 py-2.5">
        <span className="label">연도·월별</span>
      </h2>

      <div className="max-h-[30rem] overflow-y-auto">
        <button
          type="button"
          onClick={() => go(null)}
          aria-current={!active ? 'true' : undefined}
          className={`flex w-full items-baseline justify-between gap-2 border-b border-rule px-4 py-2.5 text-left transition-colors ${
            !active ? 'bg-surface-sunk font-bold text-ink' : 'text-ink-2 hover:bg-surface-sunk'
          }`}
        >
          <span className="text-[13.5px]">전체 기간</span>
          <span className="tabular text-[12px] text-ink-3">{total}</span>
        </button>

        {years.map((group) => (
          <section key={group.year}>
            <h3 className="flex items-baseline justify-between gap-2 border-b border-rule bg-surface-sunk px-4 py-1.5">
              <span className="tabular text-[12px] font-extrabold tracking-tight text-ink">
                {group.year}년
              </span>
              <span className="flex items-baseline gap-1.5">
                {group.important > 0 ? (
                  <span className="tabular text-[10.5px] font-bold text-seal">
                    중요 {group.important}
                  </span>
                ) : null}
                <span className="tabular text-[11px] text-ink-3">{group.count}</span>
              </span>
            </h3>

            <ul className="divide-y divide-rule">
              {group.months.map((m) => {
                const on = active === m.month;
                const monthNo = Number(m.month.slice(5, 7));
                return (
                  <li key={m.month}>
                    <button
                      type="button"
                      onClick={() => go(m.month)}
                      aria-current={on ? 'true' : undefined}
                      className={`flex w-full items-baseline justify-between gap-2 py-2 pl-6 pr-4 text-left transition-colors ${
                        on
                          ? 'bg-surface-sunk font-bold text-ink'
                          : 'text-ink-2 hover:bg-surface-sunk'
                      }`}
                    >
                      <span className="tabular text-[13.5px]">{monthNo}월</span>
                      <span className="flex shrink-0 items-baseline gap-1.5">
                        {m.important > 0 ? (
                          <span
                            className="tabular text-[10.5px] font-bold text-seal"
                            title={`중요 이상 ${m.important}건`}
                          >
                            !{m.important}
                          </span>
                        ) : null}
                        <span className="tabular text-[12px] text-ink-3">{m.count}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </nav>
  );
}

/** 좁은 화면용 가로 스크롤. 연도가 바뀌는 지점에 연도 표시를 끼워 넣는다. */
export function MonthStrip({ months, active }: { months: MonthBucket[]; active?: string }) {
  const go = useMonthNavigation();
  if (months.length === 0) return null;

  const sorted = [...months].sort((a, b) => b.month.localeCompare(a.month));
  let lastYear = '';

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <Pill label="전체" on={!active} onClick={() => go(null)} />
      {sorted.map((m) => {
        const year = m.month.slice(0, 4);
        const showYear = year !== lastYear;
        lastYear = year;
        return (
          <span key={m.month} className="flex shrink-0 items-center gap-1.5">
            {showYear ? (
              <span className="tabular shrink-0 border-l border-rule-strong pl-2 text-[11px] font-bold text-ink-3">
                {year}
              </span>
            ) : null}
            <Pill
              label={`${Number(m.month.slice(5, 7))}월`}
              count={m.count}
              on={active === m.month}
              onClick={() => go(m.month)}
            />
          </span>
        );
      })}
    </div>
  );
}

function Pill({
  label,
  count,
  on,
  onClick,
}: {
  label: string;
  count?: number;
  on: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={`shrink-0 whitespace-nowrap rounded-sharp border px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors ${
        on
          ? 'border-ink bg-ink text-surface'
          : 'border-rule-strong bg-surface text-ink-2 hover:border-ink hover:text-ink'
      }`}
    >
      {label}
      {count !== undefined ? (
        <span className={`tabular ml-1.5 text-[11px] ${on ? 'text-white/70' : 'text-ink-3'}`}>
          {count}
        </span>
      ) : null}
    </button>
  );
}
