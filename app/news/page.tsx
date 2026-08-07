import Link from 'next/link';

import { Masthead } from '@/components/Masthead';
import { NewsRecord } from '@/components/NewsRecord';
import { publicApi } from '@/lib/api';
import { groupByDate, todayLabel } from '@/lib/format';
import type { NewsFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const RANGES = [
  { days: 7, label: '7일' },
  { days: 30, label: '30일' },
  { days: 90, label: '90일' },
];

/**
 * 뉴스 탭.
 *
 * 이 화면의 목적은 "무슨 일이 논의되고 있는지" 알려주는 것이지,
 * "무엇이 확정됐는지" 알려주는 게 아니다. 후자는 정책 탭이 한다.
 *
 * 그래서 결이 다르다. 정책은 사이드바를 두고 편집 판단을 앞세우지만,
 * 여기는 **속보 피드**다 — 좁은 한 열, 일자별로 흐르고, 편집하지 않는다.
 * 우리가 고르지 않았다는 사실이 화면 모양으로도 읽혀야 한다.
 */
export default async function NewsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const days = Number(params.days) || 30;

  let feed: NewsFeed | null = null;
  let error: string | null = null;

  try {
    feed = await publicApi.news({ q, days, limit: 80 });
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const groups = groupByDate(feed?.items ?? [], (i) => i.published_at);

  return (
    <div className="min-h-screen">
      <Masthead active="news" />

      {/* 한 열. 폭을 읽기 좋은 만큼만 준다 — 사이드바가 없어 예전에는 요약이
          화면을 가로질렀고, 한 줄에 백 자가 넘었다. */}
      <main className="mx-auto max-w-[52rem] px-4 pb-24">
        <section className="pb-4 pt-8">
          <p className="gutter-date">{todayLabel()}</p>
          <h1 className="mt-1.5 text-display text-ink">세무 관련 보도</h1>
        </section>

        {/*
          경고 문구는 서버가 내려준 것을 그대로 쓴다. 화면에서 문구를 지우거나
          작게 바꾸는 일이 생기지 않도록, 문안의 정본을 API 에 둔다.

          바탕을 깔지 않고 굵은 좌측 괘선만 쓴다. 회색 상자는 화면에서
          "덜 중요한 안내"로 읽히는데, 이건 이 페이지에서 가장 중요한 문장이다.
        */}
        <aside className="border-l-[3px] border-state-pending py-1 pl-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.13em] text-state-pending">
            확인 전 정보
          </p>
          <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2">
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
            className="h-10 min-w-0 flex-1 rounded-sharp border border-rule-strong bg-surface px-3.5 text-[14.5px] text-ink placeholder:text-ink-3 focus:border-ink focus:outline-none"
          />
          <input type="hidden" name="days" value={String(days)} />
          <button type="submit" className="btn-primary h-10 shrink-0 py-0">
            검색
          </button>

          <div className="flex items-center gap-1">
            <span className="label pr-0.5">최근</span>
            {RANGES.map((range) => (
              <Link
                key={range.days}
                href={`/news?days=${range.days}${q ? `&q=${encodeURIComponent(q)}` : ''}`}
                className={`rounded-sharp border px-2.5 py-[7px] text-[12.5px] font-semibold transition-colors ${
                  days === range.days
                    ? 'border-ink bg-ink text-surface'
                    : 'border-rule-strong text-ink-2 hover:border-ink'
                }`}
              >
                {range.label}
              </Link>
            ))}
          </div>
        </form>

        {error ? (
          <div className="mt-7 border-l-[3px] border-seal bg-surface p-6">
            <p className="text-headline text-seal">보도를 불러오지 못했습니다</p>
            <p className="mt-2 text-[15px] text-ink-2">{error}</p>
          </div>
        ) : groups.length > 0 ? (
          <>
            <div className="mt-7 flex items-center justify-between gap-3 pb-2.5">
              <h2 className="section-mark">발행일 최신순</h2>
              <span className="tabular shrink-0 text-[12.5px] font-semibold text-ink-3">
                {feed?.total ?? 0}건
              </span>
            </div>

            <div className="panel overflow-hidden">
              {groups.map((group) => (
                <section key={group.date ?? 'undated'}>
                  <h3 className="flex items-baseline gap-3 border-y border-rule bg-surface-sunk px-4 py-2 first:border-t-0">
                    <span className="tabular text-[13px] font-extrabold tracking-tight text-ink">
                      {group.heading}
                    </span>
                    <span className="tabular ml-auto text-[12px] font-semibold text-ink-3">
                      {group.items.length}
                    </span>
                  </h3>
                  <ul className="divide-y divide-rule">
                    {group.items.map((item) => (
                      <li key={item.id}>
                        <NewsRecord item={item} />
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>

            <p className="mt-6 text-center text-[13px] text-ink-3">
              링크를 누르면 해당 언론사 사이트로 이동합니다. TaxBriefing 은 기사 본문을
              저장하지 않습니다.
            </p>
          </>
        ) : (
          <div className="mt-7 border border-rule bg-surface px-6 py-16 text-center">
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
