import Link from 'next/link';

import { RecordRow } from '@/components/ContentCard';
import { IndexRail } from '@/components/IndexRail';
import { Masthead } from '@/components/Masthead';
import { API_BASE, publicApi } from '@/lib/api';
import { daysUntil, formatDate, seoulToday } from '@/lib/format';
import type { IndustryBucket, MonthBucket, PublicContentSummary, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

/**
 * 시행 예정.
 *
 * **이 화면이 이 서비스의 차별점이다.**
 *
 * 공포된 법령만 보면 이미 늦다 — 관보에 실릴 때쯤이면 다들 안다.
 * 세무사무소 직원이 남보다 앞서려면 "앞으로 이렇게 바뀝니다" 를 미리 말할 수
 * 있어야 하고, 그 재료가 여기 있다.
 *
 * 남은 기간으로 묶는다. 날짜순 목록보다 "언제까지 준비해야 하나" 가 먼저다.
 */
const BUCKETS = [
  { key: 'soon', label: '한 달 안', note: '지금 준비하세요', max: 30 },
  { key: 'quarter', label: '3개월 안', note: '다음 신고 전에 확인', max: 90 },
  { key: 'later', label: '그 이후', note: '알아두면 되는 것', max: Infinity },
] as const;

function bucketOf(item: PublicContentSummary): (typeof BUCKETS)[number]['key'] {
  const days = daysUntil(item.effective_date) ?? Infinity;
  if (days <= 30) return 'soon';
  if (days <= 90) return 'quarter';
  return 'later';
}

export default async function UpcomingPage() {
  let feed: PublicFeed | null = null;
  let months: MonthBucket[] = [];
  let industries: IndustryBucket[] = [];
  let error: string | null = null;

  try {
    [feed, months, industries] = await Promise.all([
      // 시행일이 오늘 이후인 것. 서버가 이미 이 조건을 지원한다.
      publicApi.feed({ effective_from: seoulToday(), limit: 100 }),
      publicApi.months(),
      publicApi.industries(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const items = feed?.items ?? [];
  // 서버는 중요도 순으로 준다. 여기서는 **시행일 순**이 맞다 —
  // 무엇이 먼저 닥치는가가 준비 순서를 정한다.
  const sorted = [...items].sort((a, b) =>
    (a.effective_date ?? '9999').localeCompare(b.effective_date ?? '9999'),
  );

  return (
    <div className="min-h-screen">
      <Masthead active="policy" />

      <main className="mx-auto max-w-page px-4 pb-24">
        <section className="flex flex-wrap items-end justify-between gap-x-8 gap-y-2 pb-4 pt-8">
          <div>
            <p className="gutter-date">앞으로 바뀝니다</p>
            <h1 className="mt-1.5 text-display text-ink">시행 예정</h1>
          </div>
          <p className="max-w-[24rem] text-[13px] leading-relaxed text-ink-3">
            공포는 됐지만 아직 시행되지 않은 법령입니다.{' '}
            <strong className="font-semibold text-ink-2">지금은 종전 기준이 적용됩니다.</strong>
          </p>
        </section>

        <div className="grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
          <div className="hidden lg:sticky lg:top-6 lg:block lg:self-start">
            <IndexRail industries={industries} months={months} upcomingCount={items.length} />
          </div>

          <div className="min-w-0">
            {error ? (
              <div className="border-l-[3px] border-seal bg-surface p-6">
                <p className="text-headline text-seal">불러오지 못했습니다</p>
                <p className="mt-2 text-[15px] text-ink-2">{error}</p>
                <p className="mt-4 break-all font-mono text-[12.5px] text-ink-3">{API_BASE}</p>
              </div>
            ) : sorted.length === 0 ? (
              <div className="border border-rule bg-surface px-6 py-16 text-center">
                <p className="text-headline text-ink">시행 예정인 법령이 없습니다</p>
                <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
                  공포됐지만 아직 시행되지 않은 법령이 확인되면 여기에 표시됩니다.
                </p>
                <Link href="/" className="btn-quiet mt-6">
                  오늘의 브리핑
                </Link>
              </div>
            ) : (
              BUCKETS.map((bucket) => {
                const rows = sorted.filter((i) => bucketOf(i) === bucket.key);
                if (rows.length === 0) return null;
                return (
                  <section key={bucket.key} className="mb-10">
                    <div className="flex items-center justify-between gap-3 pb-2.5">
                      <h2 className="section-mark">{bucket.label}</h2>
                      <span className="text-[12.5px] text-ink-3">
                        {bucket.note} · {rows.length}건
                      </span>
                    </div>
                    <div className="panel overflow-hidden">
                      {rows.map((item) => (
                        <div key={item.id} className="border-b border-rule last:border-b-0">
                          <DDay date={item.effective_date} />
                          <RecordRow item={item} />
                        </div>
                      ))}
                    </div>
                  </section>
                );
              })
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

/**
 * 남은 날짜.
 *
 * "2027년 1월 1일" 만 있으면 매번 오늘과 머리로 빼야 한다.
 * 며칠 남았는지가 준비할지 말지를 정한다.
 */
function DDay({ date }: { date: string | null }) {
  const days = daysUntil(date);
  if (days === null) return null;
  const urgent = days <= 30;
  return (
    <p
      className={`tabular flex items-baseline gap-2 px-4 pt-3 text-[12.5px] font-bold sm:px-5 ${
        urgent ? 'text-seal' : 'text-ink-3'
      }`}
    >
      <span>D-{days}</span>
      <span className="font-medium">{formatDate(date)}</span>
    </p>
  );
}
