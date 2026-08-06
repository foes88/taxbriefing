import Link from 'next/link';

import { ContentRecord } from '@/components/ContentCard';
import { FilterBar } from '@/components/FilterBar';
import { Masthead } from '@/components/Masthead';
import { publicApi } from '@/lib/api';
import { recencyGroup, todayLabel } from '@/lib/format';
import type { PublicContentSummary, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function pick(params: Record<string, string | string[] | undefined>, key: string) {
  const value = params[key];
  if (value === undefined) return undefined;
  return Array.isArray(value) ? value : [value];
}

/**
 * 시간대 묶음은 장식이 아니라 정보다 — "언제 것인가"가 보이면 훑는 속도가 빨라진다.
 * 순서를 고정해 두어야 목록이 매번 같은 리듬으로 읽힌다.
 */
const GROUPS = ['오늘', '이번 주', '지난 소식'] as const;

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const filtered = Object.keys(params).length > 0;

  let feed: PublicFeed | null = null;
  let error: string | null = null;

  try {
    feed = await publicApi.feed({
      q,
      legal_status: pick(params, 'legal_status'),
      risk_level: pick(params, 'risk_level'),
      deadline_within_days: params.deadline === '7' ? 7 : undefined,
      limit: 40,
    });
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const grouped = new Map<string, PublicContentSummary[]>();
  feed?.items.forEach((item) => {
    const key = recencyGroup(item.updated_at);
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  });

  const urgent = feed?.items.filter((i) => i.risk_level === 'CRITICAL') ?? [];

  return (
    <div className="min-h-screen">
      <Masthead />

      <main className="mx-auto max-w-page px-4 pb-20">
        <section className="pb-2 pt-8">
          <p className="gutter-date">{todayLabel()}</p>
          <h1 className="mt-2 text-display text-ink">오늘 확인할 세무정보</h1>
          <p className="mt-2.5 max-w-[34rem] text-[15px] leading-relaxed text-ink-2">
            법령·관보 등 <strong className="font-semibold text-ink">공식 원문</strong>으로 사실을
            확인하고, 세무전문가가 검수한 내용만 올립니다.
          </p>
        </section>

        {urgent.length > 0 ? (
          <aside className="mt-4 border-l-2 border-seal bg-surface py-3 pl-4 pr-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.11em] text-seal">긴급</p>
            <ul className="mt-1.5 flex flex-col gap-1">
              {urgent.map((item) => (
                <li key={item.id}>
                  <Link
                    href={`/contents/${item.id}`}
                    className="text-[15px] font-bold text-ink underline decoration-seal decoration-1 underline-offset-4"
                  >
                    {item.title}
                  </Link>
                </li>
              ))}
            </ul>
          </aside>
        ) : null}

        <div className="mt-5">
          <FilterBar />
        </div>

        {error ? (
          <ErrorState message={error} />
        ) : feed && feed.items.length > 0 ? (
          <div className="mt-2">
            {GROUPS.filter((g) => grouped.has(g)).map((group) => (
              <section key={group} className="mt-7">
                <h2 className="flex items-baseline gap-3 border-b border-rule-strong pb-2">
                  <span className="text-[13px] font-bold tracking-tight text-ink">{group}</span>
                  <span className="tabular text-[11px] font-semibold text-ink-3">
                    {grouped.get(group)!.length}건
                  </span>
                </h2>
                <ul className="divide-y divide-rule">
                  {grouped.get(group)!.map((item) => (
                    <li key={item.id}>
                      <ContentRecord item={item} />
                    </li>
                  ))}
                </ul>
              </section>
            ))}

            <p className="mt-8 text-center text-[12px] text-ink-3">
              전체 <span className="tabular font-semibold">{feed.total}</span>건을 모두 보셨습니다.
            </p>
          </div>
        ) : (
          <EmptyState filtered={filtered} />
        )}
      </main>

      <footer className="border-t border-rule bg-surface">
        <div className="mx-auto max-w-page px-4 py-9 text-[13px] leading-relaxed text-ink-3">
          <p className="font-semibold text-ink-2">이 서비스는 일반적인 제도 변경을 안내합니다.</p>
          <p className="mt-1.5">
            개별 사업자의 세액이나 적용 여부는 사실관계에 따라 달라질 수 있습니다. 판단이 필요한
            사안은 세무전문가와 상담하시기 바랍니다.
          </p>
          <p className="mt-5 border-t border-rule pt-4">
            모든 내용은 공식 원문 링크와 함께 제공됩니다. · TaxBriefing
          </p>
        </div>
      </footer>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="mt-8 border border-rule-strong bg-surface p-7">
      <p className="text-headline text-seal">정보를 불러오지 못했습니다</p>
      <p className="mt-2 text-[15px] text-ink-2">{message}</p>
      <p className="mt-4 text-[12px] text-ink-3">
        백엔드가 실행 중인지 확인하세요 —{' '}
        <code className="bg-surface-sunk px-1.5 py-0.5 font-mono text-[12px]">
          uvicorn app.main:app
        </code>
      </p>
    </div>
  );
}

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="mt-8 border border-rule bg-surface px-6 py-16 text-center">
      <p className="text-headline text-ink">
        {filtered ? '조건에 맞는 정보가 없습니다' : '아직 게시된 브리핑이 없습니다'}
      </p>
      <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
        {filtered
          ? '필터를 줄이거나 검색어를 바꿔 보세요.'
          : '수집된 공식 원문을 세무전문가가 검수·승인하면 여기에 표시됩니다.'}
      </p>
      <Link href={filtered ? '/' : '/admin'} className="btn-quiet mt-6">
        {filtered ? '전체 보기' : '관리자 화면으로'}
      </Link>
    </div>
  );
}
