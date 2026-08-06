'use client';

import { useRouter, useSearchParams } from 'next/navigation';

import type { MonthBucket } from '@/lib/types';

/**
 * 월별 아카이브 (공포월 기준).
 *
 * 사업자는 "몇 월 개정"으로 기억한다 — "7월에 바뀐 거 뭐였지?"
 * 그래서 월이 1급 탐색 축이다. 중요 건수를 함께 보여줘야
 * 그 달을 열어볼지 판단할 수 있다.
 */
export function MonthNav({ months, active }: { months: MonthBucket[]; active?: string }) {
  const router = useRouter();
  const params = useSearchParams();

  if (months.length === 0) return null;

  const go = (month: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (month === null || next.get('month') === month) next.delete('month');
    else next.set('month', month);
    router.push(next.toString() ? `/?${next}` : '/');
  };

  const total = months.reduce((sum, m) => sum + m.count, 0);

  return (
    <nav aria-label="월별 보기" className="border border-rule bg-surface">
      <h2 className="border-b border-rule px-4 py-2.5">
        <span className="label">월별 보기</span>
      </h2>

      <ul className="max-h-[26rem] divide-y divide-rule overflow-y-auto">
        <li>
          <button
            type="button"
            onClick={() => go(null)}
            aria-current={!active ? 'true' : undefined}
            className={`flex w-full items-baseline justify-between gap-2 px-4 py-2.5 text-left transition-colors ${
              !active ? 'bg-surface-sunk font-bold text-ink' : 'text-ink-2 hover:bg-surface-sunk'
            }`}
          >
            <span className="text-[13.5px]">전체</span>
            <span className="tabular text-[12px] text-ink-3">{total}</span>
          </button>
        </li>

        {months.map((m) => {
          const on = active === m.month;
          return (
            <li key={m.month}>
              <button
                type="button"
                onClick={() => go(m.month)}
                aria-current={on ? 'true' : undefined}
                className={`flex w-full items-baseline justify-between gap-2 px-4 py-2.5 text-left transition-colors ${
                  on ? 'bg-surface-sunk font-bold text-ink' : 'text-ink-2 hover:bg-surface-sunk'
                }`}
              >
                <span className="text-[13.5px]">{m.label}</span>
                <span className="flex shrink-0 items-baseline gap-1.5">
                  {m.important > 0 ? (
                    <span
                      className="tabular text-[11px] font-bold text-seal"
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
    </nav>
  );
}

/** 좁은 화면용 가로 스크롤 월 선택. */
export function MonthStrip({ months, active }: { months: MonthBucket[]; active?: string }) {
  const router = useRouter();
  const params = useSearchParams();

  if (months.length === 0) return null;

  const go = (month: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (month === null || next.get('month') === month) next.delete('month');
    else next.set('month', month);
    router.push(next.toString() ? `/?${next}` : '/');
  };

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <Pill label="전체" on={!active} onClick={() => go(null)} />
      {months.map((m) => (
        <Pill
          key={m.month}
          label={m.label.replace(/^\d{4}년 /, (match) =>
            active || months[0]?.month.slice(0, 4) === m.month.slice(0, 4) ? '' : match,
          )}
          count={m.count}
          on={active === m.month}
          onClick={() => go(m.month)}
        />
      ))}
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
