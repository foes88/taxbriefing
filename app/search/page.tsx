import Link from 'next/link';

import { ContentCard, NewsCard } from '@/components/Card';
import { Masthead } from '@/components/Masthead';
import { publicApi } from '@/lib/api';
import type { IndustryBucket, NewsFeed, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/**
 * 찾기.
 *
 * **상담 중에 쓰는 화면이다.**
 *
 * "학원 원장님이 4대보험 물어보시는데" 하고 검색창에 치는 자리다.
 * 그때 사용자는 답이 법령에 있는지 심판례에 있는지 모른다. 그래서
 * 예전처럼 자료 종류로 탭을 갈라 두면, 종류를 알아야 찾을 수 있는
 * 검색이 된다. 여기서는 한 번에 다 뒤지고 종류로 좁힌다.
 *
 * 검색은 제목만 보지 않는다. 정작 답은 개정 내용과 사업자 할 일에
 * 있고, 심판례는 판단 이유 안에 있다 (search_text).
 */
const KINDS = [
  { key: 'ALL', label: '전체' },
  { key: 'POLICY', label: '법령' },
  { key: 'TRIBUNAL', label: '심판례' },
  // 다투기 전에 물어본 답. 상담 중에 "이런 경우는 어떻게 되나요" 를
  // 만나면 실무자가 먼저 찾는 것이 이것이다.
  { key: 'INTERPRETATION', label: '해석' },
  // 심판원을 거쳐 법원까지 간 사건. 실무에서 가장 무겁게 인용된다.
  { key: 'PRECEDENT', label: '판례' },
  { key: 'BILL', label: '국회 법안' },
  { key: 'NEWS', label: '뉴스' },
] as const;

type KindKey = (typeof KINDS)[number]['key'];

const PAGE_SIZE = 20;

function keep(params: Record<string, string | undefined>, extra: Record<string, string> = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...params, ...extra })) {
    if (v) q.set(k, v);
  }
  const s = q.toString();
  return s ? `/search?${s}` : '/search';
}

export default async function SearchPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q.trim() : '';
  const kind = (typeof params.kind === 'string' ? params.kind : 'ALL') as KindKey;
  const industry = typeof params.industry === 'string' ? params.industry : '';
  const show = Math.min(200, Math.max(PAGE_SIZE, Number(params.show) || PAGE_SIZE));
  const carried = { q: q || undefined, kind: kind === 'ALL' ? undefined : kind, industry: industry || undefined };

  let feed: PublicFeed | null = null;
  let news: NewsFeed | null = null;
  let industries: IndustryBucket[] = [];
  let error: string | null = null;

  try {
    if (kind === 'NEWS') {
      [news, industries] = await Promise.all([
        publicApi.news({ q: q || undefined, days: 365, limit: show }),
        publicApi.industries(),
      ]);
    } else {
      [feed, industries] = await Promise.all([
        publicApi.feed({
          q: q || undefined,
          // 전체일 때는 종류를 안 넘긴다. 서버 기본값이 법령만이라
          // 명시적으로 넷을 다 적어 준다.
          content_kind:
            kind === 'ALL'
              ? ['POLICY', 'TRIBUNAL', 'INTERPRETATION', 'PRECEDENT', 'BILL', 'SUPPORT']
              : [kind],
          industries: industry ? [industry] : undefined,
          limit: show,
        }),
        publicApi.industries(),
      ]);
    }
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const total = feed?.total ?? news?.total ?? 0;
  const shown = feed?.items.length ?? news?.items.length ?? 0;

  return (
    <div className="min-h-screen pb-20">
      <Masthead active="search" />

      <main className="mx-auto max-w-page px-4">
        <form action="/search" className="flex items-center gap-2 pb-3 pt-5">
          {kind !== 'ALL' ? <input type="hidden" name="kind" value={kind} /> : null}
          {industry ? <input type="hidden" name="industry" value={industry} /> : null}
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="학원 4대보험, 가지급금, 배달 원천징수"
            aria-label="검색"
            className="h-12 min-w-0 flex-1 rounded-field bg-surface px-4 text-[15px] text-ink shadow-[var(--lift)] outline-none placeholder:text-ink-3 focus:ring-2 focus:ring-accent"
          />
          <button type="submit" className="btn-primary shrink-0">
            검색
          </button>
        </form>

        {/* 종류 칩. 상담 중에는 종류를 모르고 찾으므로 전체가 기본이다. */}
        <div className="rail pb-2">
          {KINDS.map((k) => (
            <Link
              key={k.key}
              href={keep({ ...carried, kind: k.key === 'ALL' ? undefined : k.key })}
              className={`chip ${kind === k.key ? 'chip-on' : ''}`}
            >
              {k.label}
            </Link>
          ))}
        </div>

        {/*
          업종은 상담 참고용 색인이지 적용 판정이 아니다 (§1.3).
          "이 개정이 요식업 사장님께 적용되는가" 는 사실관계를 봐야 알고,
          그건 세무전문가의 일이다. 우리는 "요식업 상담할 때 한 번 보시라"
          까지만 한다.
        */}
        {kind !== 'NEWS' && industries.length > 0 ? (
          <div className="rail pb-4">
            <Link
              href={keep({ ...carried, industry: undefined })}
              className={`chip ${industry ? '' : 'chip-on'}`}
            >
              모든 업종
            </Link>
            {industries.map((b) => (
              <Link
                key={b.code}
                href={keep({ ...carried, industry: b.code })}
                className={`chip ${industry === b.code ? 'chip-on' : ''}`}
              >
                {b.label}
                <span className="tabular text-[13px] font-medium opacity-60">{b.count}</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="pb-4" />
        )}

        {error ? (
          <div className="card pad">
            <p className="text-card text-danger">불러오지 못했습니다</p>
            <p className="mt-1.5 text-body text-ink-2">{error}</p>
          </div>
        ) : total === 0 ? (
          <div className="card px-6 py-14 text-center">
            <p className="text-card text-ink">
              {q ? `"${q}" 로 찾은 것이 없습니다` : '아직 게시된 것이 없습니다'}
            </p>
            <p className="mx-auto mt-2 max-w-sm text-body text-ink-2">
              {q
                ? '다른 낱말로 찾아보시거나, 종류를 넓혀 보세요.'
                : '수집된 공식 원문을 세무전문가가 검수하면 여기에 표시됩니다.'}
            </p>
            {q || kind !== 'ALL' || industry ? (
              <Link href="/search" className="btn-quiet mt-5">
                조건 없이 보기
              </Link>
            ) : null}
          </div>
        ) : (
          <>
            <div className="flex items-baseline justify-between gap-3 pb-3">
              <h1 className="section-title">
                {q ? `"${q}"` : KINDS.find((k) => k.key === kind)?.label}
              </h1>
              <span className="tabular shrink-0 text-meta font-semibold text-ink-3">{total}건</span>
            </div>

            <div className="flex flex-col gap-2.5">
              {news
                ? news.items.map((item) => <NewsCard key={item.id} item={item} />)
                : feed?.items.map((item) => <ContentCard key={item.id} item={item} />)}
            </div>

            {total > shown ? (
              <div className="flex flex-col items-center gap-2 pt-6">
                <Link
                  href={keep({ ...carried, show: String(show + PAGE_SIZE) })}
                  scroll={false}
                  className="btn-quiet w-full max-w-xs"
                >
                  {Math.min(PAGE_SIZE, total - shown)}건 더 보기
                </Link>
                <p className="tabular text-meta text-ink-3">
                  {shown} / {total}건
                </p>
              </div>
            ) : (
              <p className="pt-6 text-center text-meta text-ink-3">전체 {total}건을 모두 보셨습니다.</p>
            )}
          </>
        )}
      </main>
    </div>
  );
}
