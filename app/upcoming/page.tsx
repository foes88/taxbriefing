import { ContentCard } from '@/components/Card';
import { DeadlineCard } from '@/components/DeadlineCard';
import { Masthead } from '@/components/Masthead';
import { publicApi } from '@/lib/api';
import { daysUntil, seoulToday } from '@/lib/format';
import type { Deadline, PublicContentSummary, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

/**
 * 일정.
 *
 * **공포는 됐지만 아직 시행되지 않은 법령**을 남은 기간으로 묶는다.
 * 사장님이 묻는 것은 "몇 건인가" 가 아니라 "언제까지 준비하면 되나" 다.
 *
 * 지금은 종전 기준이 적용된다는 사실을 화면 위에 크게 둔다. 이 화면에서
 * 가장 위험한 오해가 "이미 바뀌었구나" 이기 때문이다.
 */
const BUCKETS = [
  { key: 'month', label: '이번 달 안', note: '30일 이내', within: 30 },
  { key: 'quarter', label: '3개월 안', note: '31~90일', within: 90 },
  { key: 'later', label: '그 이후', note: '90일 넘음', within: Infinity },
] as const;

function bucketOf(item: PublicContentSummary) {
  const days = daysUntil(item.effective_date) ?? Infinity;
  return BUCKETS.find((b) => days <= b.within) ?? BUCKETS[BUCKETS.length - 1];
}

export default async function UpcomingPage() {
  let feed: PublicFeed | null = null;
  let deadlines: Deadline[] = [];
  let error: string | null = null;

  try {
    [feed, deadlines] = await Promise.all([
      // 시행일이 오늘 이후인 것. 종류는 법령·법안 둘 다 — 둘 다 앞으로 올 일이다.
      publicApi.feed({
        effective_from: seoulToday(),
        content_kind: ['POLICY', 'BILL', 'SUPPORT'],
        limit: 100,
      }),
      publicApi.calendar(90),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const items = [...(feed?.items ?? [])].sort(
    (a, b) => (daysUntil(a.effective_date) ?? 1e9) - (daysUntil(b.effective_date) ?? 1e9),
  );

  return (
    <div className="min-h-screen pb-20">
      <Masthead active="schedule" />

      <main className="mx-auto max-w-page px-4">
        <section className="pb-4 pt-5">
          <p className="text-meta font-semibold text-ink-3">앞으로 할 일</p>
          <h1 className="mt-1 text-display text-ink">일정</h1>
        </section>

        {/*
          **마감이 먼저다.**
          시행 예정 법령은 "언젠가 바뀐다" 지만 신고 기한은 "이 날까지
          해야 한다" 다. 실무자의 하루를 굴리는 것은 뒤쪽이다.

          날짜는 법에 정해져 있어 수집도 AI 도 쓰지 않는다 —
          기한을 하루 틀리면 가산세가 붙는다.
        */}
        {deadlines.length > 0 ? (
          <section className="pb-2">
            <div className="flex items-baseline justify-between gap-3 pb-3">
              <h2 className="section-title">신고·납부 마감</h2>
              <span className="shrink-0 text-meta text-ink-3">앞으로 3개월</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {deadlines.slice(0, 8).map((d) => (
                <DeadlineCard key={`${d.date}-${d.title}`} deadline={d} />
              ))}
            </div>
            <p className="px-1 pt-3 text-meta leading-relaxed text-ink-3">
              일반 일정입니다. 과세유형·결산월·반기납부 여부에 따라 기한이 다를 수 있고,
              마감일이 공휴일이면 다음 영업일로 밀립니다.
            </p>
          </section>
        ) : null}

        <div className="flex items-baseline justify-between gap-3 pb-3 pt-8">
          <h2 className="section-title">시행 예정 법령</h2>
          <span className="tabular shrink-0 text-meta text-ink-3">
            {feed?.total ?? items.length}건
          </span>
        </div>

        {/*
          이 구획에서 가장 위험한 오해는 "이미 바뀌었구나" 다.
          알약이 아니라 문장으로, 목록보다 먼저 둔다.
        */}
        <div className="card mb-4 border-l-4 border-warn px-4 py-3.5">
          <p className="text-[14.5px] font-bold text-ink">지금은 종전 기준이 적용됩니다.</p>
          <p className="mt-1 text-meta leading-relaxed text-ink-2">
            아래는 공포는 됐지만 아직 시행되지 않은 것들입니다. 시행일 전까지는 예전 기준으로
            신고·납부하시면 됩니다.
          </p>
        </div>

        {error ? (
          <div className="card pad">
            <p className="text-card text-danger">불러오지 못했습니다</p>
            <p className="mt-1.5 text-body text-ink-2">{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="card px-6 py-14 text-center">
            <p className="text-card text-ink">시행 예정인 것이 없습니다</p>
            <p className="mx-auto mt-2 max-w-sm text-body text-ink-2">
              공포된 개정이 모두 시행됐거나, 아직 수집되지 않았습니다.
            </p>
          </div>
        ) : (
          BUCKETS.map((bucket) => {
            const rows = items.filter((i) => bucketOf(i).key === bucket.key);
            if (rows.length === 0) return null;
            return (
              <section key={bucket.key} className="pt-6 first:pt-0">
                <div className="flex items-baseline justify-between gap-3 pb-3">
                  <h2 className="section-title">{bucket.label}</h2>
                  <span className="shrink-0 text-meta text-ink-3">
                    {bucket.note} · <span className="tabular font-semibold">{rows.length}건</span>
                  </span>
                </div>
                <div className="flex flex-col gap-2.5">
                  {rows.map((item) => (
                    <ContentCard key={item.id} item={item} />
                  ))}
                </div>
              </section>
            );
          })
        )}
      </main>
    </div>
  );
}
