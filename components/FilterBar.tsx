'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useState } from 'react';

/**
 * 검색과 좁히기 (U-02).
 *
 * 회원 개인화가 없으므로(ADR-002) **사장님이 직접 고른다.**
 * 상태는 URL 에 담아 공유·북마크가 되게 한다 — "부가세만 보기" 링크를
 * 단톡방에 던질 수 있어야 한다.
 *
 * 업종은 여기 없다. 색인 레일로 옮겼다 — 상시 탐색축이지 가끔 켜는 필터가 아니다.
 * 남은 것들(중요도·상태·기간)은 접어 둔다. 예전에는 열일곱 개가 늘 펼쳐져
 * 있어서 사장님이 보러 온 목록이 화면 아래에 있었다.
 */

const RISK = [
  { value: 'CRITICAL', label: '긴급' },
  { value: 'HIGH', label: '중요' },
] as const;

const STATUS = [
  { value: 'EFFECTIVE', label: '시행 중' },
  { value: 'PROMULGATED', label: '공포' },
  { value: 'PREANNOUNCED', label: '입법예고' },
  { value: 'BILL_PROPOSED', label: '발의' },
] as const;

export function FilterBar() {
  const router = useRouter();
  const params = useSearchParams();

  const from = params.get('from') ?? '';
  const to = params.get('to') ?? '';
  const [rangeOpen, setRangeOpen] = useState(Boolean(from || to));

  // 접힌 영역에 걸려 있는 조건 수. 접어 두면 안 보이므로 숫자로 알린다.
  const narrowCount =
    params.getAll('risk_level').length +
    params.getAll('legal_status').length +
    (params.get('deadline') ? 1 : 0) +
    (from || to ? 1 : 0);
  const [moreOpen, setMoreOpen] = useState(narrowCount > 0);

  const push = useCallback(
    (next: URLSearchParams) => router.push(next.toString() ? `/?${next}` : '/'),
    [router],
  );

  const toggle = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      const current = next.getAll(key);
      next.delete(key);
      const remaining = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      remaining.forEach((v) => next.append(key, v));
      push(next);
    },
    [params, push],
  );

  const setFlag = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (next.get(key) === value) next.delete(key);
      else next.set(key, value);
      push(next);
    },
    [params, push],
  );

  const applyRange = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const next = new URLSearchParams(params.toString());
      // 기간을 지정하면 월 선택은 해제한다 — 둘이 겹치면 결과를 설명할 수 없다.
      next.delete('month');
      for (const key of ['from', 'to'] as const) {
        const value = String(form.get(key) ?? '').trim();
        if (value) next.set(key, value);
        else next.delete(key);
      }
      push(next);
    },
    [params, push],
  );

  const on = (key: string, value: string) => params.getAll(key).includes(value);
  const dirty = Array.from(params.keys()).length > 0;

  return (
    <search className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <form action="/" className="flex min-w-0 flex-1 gap-2">
          {/* 검색해도 고른 업종·월은 유지한다. */}
          {params.get('month') ? (
            <input type="hidden" name="month" value={params.get('month')!} />
          ) : null}
          {params.getAll('industries').map((v) => (
            <input key={v} type="hidden" name="industries" value={v} />
          ))}
          {params.getAll('risk_level').map((v) => (
            <input key={v} type="hidden" name="risk_level" value={v} />
          ))}
          {params.getAll('legal_status').map((v) => (
            <input key={v} type="hidden" name="legal_status" value={v} />
          ))}

          <input
            type="search"
            name="q"
            defaultValue={params.get('q') ?? ''}
            placeholder="상담 내용으로 검색 — 학원 4대보험, 배달 원천징수"
            aria-label="키워드 검색"
            className="h-10 min-w-0 flex-1 rounded-sharp border border-rule-strong bg-surface px-3.5 text-[14.5px] text-ink placeholder:text-ink-3 focus:border-ink focus:outline-none"
          />
          <button type="submit" className="btn-primary h-10 shrink-0 py-0">
            검색
          </button>
        </form>

        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          aria-expanded={moreOpen}
          className={`h-10 shrink-0 whitespace-nowrap rounded-sharp border px-3 text-[12.5px] font-semibold transition-colors ${
            narrowCount > 0
              ? 'border-ink bg-ink text-surface'
              : 'border-rule-strong bg-surface text-ink-2 hover:border-ink hover:text-ink'
          }`}
        >
          좁혀 보기
          {narrowCount > 0 ? <span className="tabular ml-1.5">{narrowCount}</span> : null}
        </button>

        {dirty ? (
          <button
            type="button"
            onClick={() => router.push('/')}
            className="shrink-0 whitespace-nowrap px-1 text-[12.5px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
          >
            해제
          </button>
        ) : null}
      </div>

      {moreOpen ? (
        <div className="flex flex-col gap-2.5 border-t border-rule pt-3">
          <Row label="중요도">
            {RISK.map((o) => (
              <Chip
                key={o.value}
                label={o.label}
                active={on('risk_level', o.value)}
                onClick={() => toggle('risk_level', o.value)}
              />
            ))}
            <Chip
              label="마감 임박"
              active={params.get('deadline') === '7'}
              onClick={() => setFlag('deadline', '7')}
            />
          </Row>

          <Row label="상태">
            {STATUS.map((o) => (
              <Chip
                key={o.value}
                label={o.label}
                active={on('legal_status', o.value)}
                onClick={() => toggle('legal_status', o.value)}
              />
            ))}
          </Row>

          <Row label="기간">
            <Chip
              label={from || to ? `${from || '처음'} ~ ${to || '오늘'}` : '공포일로 좁히기'}
              active={rangeOpen || Boolean(from || to)}
              onClick={() => setRangeOpen((v) => !v)}
            />
          </Row>

          {rangeOpen ? (
            <form onSubmit={applyRange} className="flex flex-wrap items-end gap-2">
              <label className="flex-1 basis-[9rem]">
                <span className="label">공포일 시작</span>
                <input
                  type="date"
                  name="from"
                  defaultValue={from}
                  className="mt-1 w-full rounded-sharp border border-rule-strong bg-surface px-2.5 py-2 text-[14px] text-ink focus:border-ink"
                />
              </label>
              <label className="flex-1 basis-[9rem]">
                <span className="label">공포일 종료</span>
                <input
                  type="date"
                  name="to"
                  defaultValue={to}
                  className="mt-1 w-full rounded-sharp border border-rule-strong bg-surface px-2.5 py-2 text-[14px] text-ink focus:border-ink"
                />
              </label>
              <button type="submit" className="btn-quiet shrink-0 py-2">
                적용
              </button>
            </form>
          ) : null}
        </div>
      ) : null}
    </search>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <span className="label w-[3.25rem] shrink-0">{label}</span>
      {children}
    </div>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`shrink-0 whitespace-nowrap rounded-sharp border px-2.5 py-1.5 text-[12px] font-semibold transition-colors ${
        active
          ? 'border-ink bg-ink text-surface'
          : 'border-rule-strong bg-surface text-ink-2 hover:border-ink hover:text-ink'
      }`}
    >
      {label}
    </button>
  );
}
