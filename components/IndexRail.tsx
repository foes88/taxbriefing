'use client';

import { useRouter, useSearchParams } from 'next/navigation';

import type { IndustryBucket, MonthBucket } from '@/lib/types';

/**
 * 색인 레일 — 업종과 월별을 한 열에 세운다.
 *
 * 업종은 원래 필터 칩 줄에 있었다. 그런데 업종은 **상시 탐색축**이지
 * 가끔 켜는 필터가 아니다. "요식업 상담 중"이면 그 상태로 계속 머문다.
 * 가로 칩 줄은 아홉 개가 넘어가면 스크롤이 생기고, 스크롤 안에 든 항목은
 * 사실상 없는 항목이 된다.
 *
 * 관보의 색인이 그렇듯 세로 목록은 훑기 쉽고, 건수를 오른쪽에 정렬해 두면
 * 어디에 뭐가 많은지가 한눈에 읽힌다.
 */

function useNavigate() {
  const router = useRouter();
  const params = useSearchParams();

  return {
    params,
    toggle(key: string, value: string | null) {
      const next = new URLSearchParams(params.toString());
      if (key === 'month') {
        // 월을 고르면 기간 검색은 해제한다 — 둘이 겹치면 결과를 설명할 수 없다.
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
    },
  };
}

export function IndexRail({
  industries,
  months,
}: {
  industries: IndustryBucket[];
  months: MonthBucket[];
}) {
  const { params, toggle } = useNavigate();
  const activeIndustries = params.getAll('industries');
  const activeMonth = params.get('month');

  const years = groupByYear(months);
  const total = months.reduce((sum, m) => sum + m.count, 0);

  return (
    <nav aria-label="업종·월별 색인" className="flex flex-col gap-7">
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
                  onClick={() => toggle('industries', item.code)}
                />
              </li>
            ))}
          </ul>
          {activeIndustries.length > 0 ? (
            <button
              type="button"
              onClick={() => toggle('industries', null)}
              className="mt-1.5 px-1 text-[12px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
            >
              업종 해제
            </button>
          ) : null}
        </section>
      ) : null}

      {months.length > 0 ? (
        <section>
          <RailHeading>공포월</RailHeading>
          <ul className="mt-1">
            <li>
              <RailRow
                label="전체 기간"
                count={total}
                active={!activeMonth}
                onClick={() => toggle('month', null)}
              />
            </li>
            {years.map((group) => (
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
                        onClick={() => toggle('month', m.month)}
                      />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </nav>
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
