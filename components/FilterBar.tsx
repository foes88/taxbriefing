'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useState } from 'react';

import type { IndustryBucket } from '@/lib/types';

/**
 * 검색·필터 (U-02).
 *
 * 회원 개인화가 없으므로(ADR-002) **사장님이 직접 고른다.**
 * 상태는 URL 에 담아 공유·북마크가 되게 한다 — "부가세만 보기" 링크를
 * 단톡방에 던질 수 있어야 한다.
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

export function FilterBar({ industries = [] }: { industries?: IndustryBucket[] }) {
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
    <search className="border-y border-rule bg-surface px-3 py-3">
      <form action="/" className="flex gap-2">
        {/* 키워드 검색 시 기존 필터를 유지한다. */}
        {params.get('month') ? (
          <input type="hidden" name="month" value={params.get('month')!} />
        ) : null}
        {params.getAll('risk_level').map((v) => (
          <input key={v} type="hidden" name="risk_level" value={v} />
        ))}
        {params.getAll('legal_status').map((v) => (
          <input key={v} type="hidden" name="legal_status" value={v} />
        ))}

        {params.getAll('industries').map((v) => (
          <input key={v} type="hidden" name="industries" value={v} />
        ))}

        <input
          type="search"
          name="q"
          defaultValue={params.get('q') ?? ''}
          placeholder="상담 내용으로 검색 (예: 학원 4대보험, 배달 원천징수)"
          aria-label="키워드 검색"
          className="min-w-0 flex-1 rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-ink-3 focus:border-ink"
        />
        <button type="submit" className="btn-primary shrink-0">
          검색
        </button>
      </form>

      {/*
        업종은 별도 줄에 둔다. 상담 중에 가장 먼저 좁히는 축이라
        중요도·상태 칩과 같은 줄에 섞이면 매번 눈으로 찾아야 한다.
      */}
      {industries.length > 0 ? (
        <div className="mt-2.5 flex items-center gap-1.5 overflow-x-auto border-t border-rule pt-2.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <span className="label shrink-0 pr-0.5">업종</span>
          {industries.map((item) => (
            <Chip
              key={item.code}
              label={item.label}
              count={item.count}
              active={on('industries', item.code)}
              onClick={() => toggle('industries', item.code)}
            />
          ))}
        </div>
      ) : null}

      {/*
        중요도·상태·기간은 **접어 둔다.**
        예전에는 업종 9개와 함께 열일곱 개가 늘 펼쳐져 있었고, 첫 항목이
        나오기까지 조작 요소만 지나갔다. 자주 쓰는 축(검색·업종)만 남기고
        나머지는 필요할 때 연다. 걸려 있는 조건 수는 접힌 채로도 보인다.
      */}
      <div className="mt-2.5 flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          aria-expanded={moreOpen}
          className={`shrink-0 whitespace-nowrap rounded-sharp border px-2.5 py-1.5 text-[12px] font-semibold transition-colors ${
            narrowCount > 0
              ? 'border-ink bg-ink text-surface'
              : 'border-rule-strong bg-surface text-ink-2 hover:border-ink hover:text-ink'
          }`}
        >
          <span aria-hidden className="mr-1 inline-block">
            {moreOpen ? '−' : '+'}
          </span>
          좁혀 보기
          {narrowCount > 0 ? <span className="tabular ml-1.5">{narrowCount}</span> : null}
        </button>

        {dirty ? (
          <button
            type="button"
            onClick={() => router.push('/')}
            className="shrink-0 whitespace-nowrap px-1.5 text-[12px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
          >
            전체 해제
          </button>
        ) : null}
      </div>

      {moreOpen ? (
        <div className="mt-2.5 flex flex-col gap-2.5 border-t border-rule pt-3">
          <div className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <span className="label shrink-0 pr-0.5">중요도</span>
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
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <span className="label shrink-0 pr-0.5">상태</span>
            {STATUS.map((o) => (
              <Chip
                key={o.value}
                label={o.label}
                active={on('legal_status', o.value)}
                onClick={() => toggle('legal_status', o.value)}
              />
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="label shrink-0 pr-0.5">기간</span>
            <Chip
              label={from || to ? `${from || '처음'} ~ ${to || '오늘'}` : '공포일로 좁히기'}
              active={rangeOpen || Boolean(from || to)}
              onClick={() => setRangeOpen((v) => !v)}
            />
          </div>
        </div>
      ) : null}

      {rangeOpen ? (
        <form
          onSubmit={applyRange}
          className="mt-2.5 flex flex-wrap items-end gap-2 border-t border-rule pt-3"
        >
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
          {from || to ? (
            <button
              type="button"
              onClick={() => {
                const next = new URLSearchParams(params.toString());
                next.delete('from');
                next.delete('to');
                push(next);
              }}
              className="shrink-0 px-1.5 pb-2 text-[12px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
            >
              기간 해제
            </button>
          ) : null}
        </form>
      ) : null}
    </search>
  );
}

function Chip({
  label,
  active,
  onClick,
  count,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
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
      {count !== undefined ? (
        <span
          className={`tabular ml-1.5 font-medium ${active ? 'text-surface/70' : 'text-ink-3'}`}
        >
          {count}
        </span>
      ) : null}
    </button>
  );
}
