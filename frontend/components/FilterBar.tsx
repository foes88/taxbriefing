'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

/**
 * 필터 (U-02).
 *
 * MVP는 로그인이 없으므로(ADR-002) 개인화 대신 **사장님이 직접 고른다.**
 * 상태를 URL에 담아 공유·북마크가 되게 한다 — "부가세만 보기" 링크를
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

export function FilterBar() {
  const router = useRouter();
  const params = useSearchParams();

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

  const on = (key: string, value: string) => params.getAll(key).includes(value);
  const dirty = Array.from(params.keys()).length > 0;

  return (
    <search className="border-y border-rule bg-surface px-3 py-3">
      <form action="/" className="flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={params.get('q') ?? ''}
          placeholder="세목·제도명 검색 (예: 부가가치세)"
          aria-label="키워드 검색"
          className="min-w-0 flex-1 rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-ink-3 focus:border-ink"
        />
        <button type="submit" className="btn-primary shrink-0">
          검색
        </button>
      </form>

      <div className="mt-2.5 flex items-center gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <Chip
          label="마감 임박"
          active={params.get('deadline') === '7'}
          onClick={() => setFlag('deadline', '7')}
        />
        <Divider />
        {RISK.map((o) => (
          <Chip
            key={o.value}
            label={o.label}
            active={on('risk_level', o.value)}
            onClick={() => toggle('risk_level', o.value)}
          />
        ))}
        <Divider />
        {STATUS.map((o) => (
          <Chip
            key={o.value}
            label={o.label}
            active={on('legal_status', o.value)}
            onClick={() => toggle('legal_status', o.value)}
          />
        ))}
        {dirty ? (
          <button
            type="button"
            onClick={() => router.push('/')}
            className="ml-1 shrink-0 whitespace-nowrap px-1.5 text-[12px] font-semibold text-ink-3 underline underline-offset-4 hover:text-ink"
          >
            초기화
          </button>
        ) : null}
      </div>
    </search>
  );
}

function Divider() {
  return <span aria-hidden className="mx-1 h-3.5 w-px shrink-0 bg-rule-strong" />;
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
