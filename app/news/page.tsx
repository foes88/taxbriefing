import Link from 'next/link';

import { Masthead } from '@/components/Masthead';
import { NewsRecord } from '@/components/NewsRecord';
import { SectionTabs } from '@/components/SectionTabs';
import { publicApi } from '@/lib/api';
import { todayLabel } from '@/lib/format';
import type { NewsFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const RANGES = [
  { days: 7, label: '최근 7일' },
  { days: 30, label: '최근 30일' },
  { days: 90, label: '최근 90일' },
];

/**
 * 뉴스 탭.
 *
 * 이 화면의 목적은 "무슨 일이 논의되고 있는지" 알려주는 것이지,
 * "무엇이 확정됐는지" 알려주는 게 아니다. 후자는 정책 탭이 한다.
 * 그래서 여기엔 시행일도, 상태 도장도, 위험도도 없다 — 우리가 확인한 게 없으니
 * 확인한 척하는 표시를 붙일 수 없다.
 */
export default async function NewsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const days = Number(params.days) || 30;

  let feed: NewsFeed | null = null;
  let error: string | null = null;

  try {
    feed = await publicApi.news({ q, days, limit: 60 });
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  return (
    <div className="min-h-screen">
      <Masthead />
      <SectionTabs active="news" />

      <main className="mx-auto max-w-page px-4 pb-20">
        <section className="pb-2 pt-8">
          <p className="gutter-date">{todayLabel()}</p>
          <h1 className="mt-2 text-display text-ink">세무 관련 보도</h1>
          <p className="mt-2.5 max-w-reading text-[15px] leading-relaxed text-ink-2">
            언론에 나온 세무 관련 기사입니다. 제목과 링크만 모아둔 것이며, 내용을 확인하거나
            검수하지 않았습니다.
          </p>
        </section>

        {/*
          경고 문구는 서버가 내려준 것을 그대로 쓴다. 화면에서 문구를 지우거나
          작게 바꾸는 일이 생기지 않도록, 문안의 정본을 API 에 둔다.
        */}
        <aside className="mt-4 border-l-2 border-state-pending bg-surface py-3 pl-4 pr-3">
          <p className="text-[11px] font-bold uppercase tracking-[0.11em] text-state-pending">
            확인 전 정보
          </p>
          <p className="mt-1 max-w-reading text-[13.5px] leading-relaxed text-ink-2">
            {feed?.caveat ??
              '아래는 언론 보도입니다. 공식 원문으로 확인되지 않았으며 확정된 제도 변경이 아닐 수 있습니다.'}{' '}
            확정된 내용은{' '}
            <Link href="/" className="font-semibold text-ink underline underline-offset-2">
              정책·법령 탭
            </Link>
            에서 보세요.
          </p>
        </aside>

        <form className="mt-6 flex flex-wrap items-center gap-2" action="/news">
          <input
            type="search"
            name="q"
            defaultValue={q ?? ''}
            placeholder="기사 제목 검색"
            className="h-9 min-w-0 flex-1 rounded-sharp border border-rule-strong bg-surface px-3 text-[14px] text-ink placeholder:text-ink-3 focus:border-ink focus:outline-none sm:max-w-xs"
          />
          <input type="hidden" name="days" value={String(days)} />
          <button type="submit" className="btn-quiet h-9">
            검색
          </button>

          <div className="ml-auto flex items-center gap-1">
            {RANGES.map((range) => (
              <Link
                key={range.days}
                href={`/news?days=${range.days}${q ? `&q=${encodeURIComponent(q)}` : ''}`}
                className={`rounded-sharp border px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors ${
                  days === range.days
                    ? 'border-ink bg-ink text-paper'
                    : 'border-rule-strong text-ink-2 hover:border-ink'
                }`}
              >
                {range.label}
              </Link>
            ))}
          </div>
        </form>

        {error ? (
          <div className="mt-4 border border-rule-strong bg-surface p-7">
            <p className="text-headline text-seal">보도를 불러오지 못했습니다</p>
            <p className="mt-2 text-[15px] text-ink-2">{error}</p>
          </div>
        ) : feed && feed.items.length > 0 ? (
          <>
            <div className="mt-4 flex items-baseline justify-between gap-3 border-b border-rule-strong pb-2">
              <h2 className="text-[13px] font-bold tracking-tight text-ink">발행일 최신순</h2>
              <span className="tabular shrink-0 text-[12px] font-semibold text-ink-3">
                {feed.total}건
              </span>
            </div>

            <ul className="divide-y divide-rule">
              {feed.items.map((item) => (
                <li key={item.id}>
                  <NewsRecord item={item} />
                </li>
              ))}
            </ul>

            <p className="mt-6 text-center text-[12.5px] text-ink-3">
              링크를 누르면 해당 언론사 사이트로 이동합니다. TaxBriefing 은 기사 본문을
              저장하지 않습니다.
            </p>
          </>
        ) : (
          <div className="mt-4 border border-rule bg-surface px-6 py-16 text-center">
            <p className="text-headline text-ink">
              {q ? '조건에 맞는 기사가 없습니다' : '수집된 기사가 없습니다'}
            </p>
            <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
              {q
                ? '검색어를 바꾸거나 기간을 넓혀 보세요.'
                : '네이버 검색 API 키를 설정하면 매일 자동으로 모입니다.'}
            </p>
            {q ? (
              <Link href="/news" className="btn-quiet mt-6">
                전체 보기
              </Link>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
