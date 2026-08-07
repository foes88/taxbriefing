import Link from 'next/link';

import { ContentRecord } from '@/components/ContentCard';
import { FilterBar } from '@/components/FilterBar';
import { Masthead } from '@/components/Masthead';
import { MonthNav, MonthStrip } from '@/components/MonthNav';
import { SectionTabs } from '@/components/SectionTabs';
import { API_BASE, API_BASE_IS_DEFAULT, publicApi } from '@/lib/api';
import { todayLabel } from '@/lib/format';
import type { IndustryBucket, MonthBucket, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function pick(params: Record<string, string | string[] | undefined>, key: string) {
  const value = params[key];
  if (value === undefined) return undefined;
  return Array.isArray(value) ? value : [value];
}

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const month = typeof params.month === 'string' ? params.month : undefined;
  const from = typeof params.from === 'string' ? params.from : undefined;
  const to = typeof params.to === 'string' ? params.to : undefined;
  const filtered = Object.keys(params).length > 0;

  let feed: PublicFeed | null = null;
  let months: MonthBucket[] = [];
  let industries: IndustryBucket[] = [];
  let error: string | null = null;

  try {
    [feed, months, industries] = await Promise.all([
      publicApi.feed({
        q,
        month,
        promulgated_from: from,
        promulgated_to: to,
        legal_status: pick(params, 'legal_status'),
        risk_level: pick(params, 'risk_level'),
        industries: pick(params, 'industries'),
        deadline_within_days: params.deadline === '7' ? 7 : undefined,
        limit: 60,
      }),
      publicApi.months(),
      publicApi.industries(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const activeIndustries = industries.filter((item) =>
    (pick(params, 'industries') ?? []).includes(item.code),
  );

  const activeMonth = months.find((m) => m.month === month);
  const rangeLabel =
    from || to ? `${from ?? '처음'} ~ ${to ?? '오늘'} 공포분` : null;
  const urgent = feed?.items.filter((i) => i.risk_level === 'CRITICAL') ?? [];

  return (
    <div className="min-h-screen">
      <Masthead />
      <SectionTabs active="policy" />

      <main className="mx-auto max-w-page px-4 pb-20">
        <section className="pb-2 pt-8">
          <p className="gutter-date">{todayLabel()}</p>
          <h1 className="mt-2 text-display text-ink">
            {activeMonth
              ? `${activeMonth.label} 세무정보`
              : rangeLabel
                ? '기간 검색 결과'
                : '오늘 확인할 세무정보'}
          </h1>
          <p className="mt-2.5 max-w-[36rem] text-[15px] leading-relaxed text-ink-2">
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

        {/* 좁은 화면에서는 월 선택을 가로 스트립으로 둔다. */}
        {months.length > 0 ? (
          <div className="mt-5 lg:hidden">
            <MonthStrip months={months} active={month} />
          </div>
        ) : null}

        <div className="mt-4 grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-start lg:gap-8">
          {/* ── 좌측: 월별 아카이브 ── */}
          <div className="hidden lg:sticky lg:top-4 lg:block">
            <MonthNav months={months} active={month} />
          </div>

          {/* ── 본문 ── */}
          <div className="min-w-0">
            <FilterBar industries={industries} />

            {error ? (
              <ErrorState message={error} />
            ) : feed && feed.items.length > 0 ? (
              <>
                <div className="mt-4 flex items-baseline justify-between gap-3 border-b border-rule-strong pb-2">
                  <h2 className="min-w-0 text-[13px] font-bold tracking-tight text-ink">
                    {activeIndustries.length > 0
                      ? activeIndustries.map((i) => i.label).join(' · ')
                      : activeMonth
                        ? `${activeMonth.label} 공포분`
                        : (rangeLabel ?? '전체')}
                    {activeMonth && activeIndustries.length === 0 ? (
                      <span className="ml-2 text-[11.5px] font-medium text-ink-3">
                        시행일은 이보다 늦을 수 있습니다
                      </span>
                    ) : null}
                  </h2>
                  <span className="tabular shrink-0 text-[12px] font-semibold text-ink-3">
                    {feed.total}건
                  </span>
                </div>

                <ul className="divide-y divide-rule">
                  {feed.items.map((item) => (
                    <li key={item.id}>
                      {/* 특정 월을 보고 있으면 공포일은 이미 알고 있으니 반복하지 않는다. */}
                      <ContentRecord item={item} showPromulgated={!activeMonth} />
                    </li>
                  ))}
                </ul>

                <p className="mt-6 text-center text-[12.5px] text-ink-3">
                  {feed.total > feed.items.length
                    ? `${feed.items.length}건 표시 · 전체 ${feed.total}건. 월을 선택해 좁혀 보세요.`
                    : `전체 ${feed.total}건을 모두 보셨습니다.`}
                </p>
              </>
            ) : (
              <EmptyState filtered={filtered} />
            )}
          </div>
        </div>
      </main>

      <footer className="border-t border-rule bg-surface">
        <div className="mx-auto max-w-page px-4 py-9 text-[13px] leading-relaxed text-ink-3">
          <p className="font-semibold text-ink-2">이 서비스는 일반적인 제도 변경을 안내합니다.</p>
          <p className="mt-1.5 max-w-[44rem]">
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

/**
 * 실패 화면은 **어디에 연결하려 했는지**를 보여준다.
 * 그게 없으면 "환경변수를 확인하세요"만 반복하게 되고, 실제로 무엇이 잘못됐는지
 * 알 수 없다. API 주소는 비밀이 아니므로 그대로 노출해도 된다.
 */
function ErrorState({ message }: { message: string }) {
  return (
    <div className="mt-4 border border-rule-strong bg-surface p-7">
      <p className="text-headline text-seal">정보를 불러오지 못했습니다</p>
      <p className="mt-2 text-[15px] text-ink-2">{message}</p>

      <dl className="mt-5 border-t border-rule pt-4 text-[13px]">
        <dt className="label">연결 시도한 주소</dt>
        <dd className="mt-1.5 break-all font-mono text-[12.5px] text-ink">{API_BASE}</dd>
      </dl>

      {API_BASE_IS_DEFAULT ? (
        <p className="mt-4 border-l-2 border-seal bg-surface-sunk px-3 py-2.5 text-[13px] leading-relaxed text-ink-2">
          <strong className="font-bold text-seal">NEXT_PUBLIC_API_BASE 가 설정되지 않았습니다.</strong>
          <br />
          배포 환경의 환경변수에 API 주소를 넣고(Production 체크) 재배포하세요.
        </p>
      ) : (
        <p className="mt-4 text-[13px] leading-relaxed text-ink-3">
          주소는 설정돼 있으나 응답이 없습니다. API 서버가 켜져 있는지, 그리고 이 사이트
          주소가 서버의 허용 목록(CORS)에 있는지 확인하세요.
        </p>
      )}
    </div>
  );
}

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="mt-4 border border-rule bg-surface px-6 py-16 text-center">
      <p className="text-headline text-ink">
        {filtered ? '조건에 맞는 정보가 없습니다' : '아직 게시된 브리핑이 없습니다'}
      </p>
      <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
        {filtered
          ? '필터를 줄이거나 다른 달을 선택해 보세요.'
          : '수집된 공식 원문을 세무전문가가 검수·승인하면 여기에 표시됩니다.'}
      </p>
      <Link href={filtered ? '/' : '/admin'} className="btn-quiet mt-6">
        {filtered ? '전체 보기' : '관리자 화면으로'}
      </Link>
    </div>
  );
}
