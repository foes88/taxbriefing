import Link from 'next/link';

import { ContentCard } from '@/components/Card';
import { DeadlineCard } from '@/components/DeadlineCard';
import { Masthead } from '@/components/Masthead';
import { ShareCard } from '@/components/ShareCard';
import { publicApi } from '@/lib/api';
import { daysUntil, seoulToday } from '@/lib/format';
import type { Deadline, PublicContentSummary, PublicFeed, SharePlan } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/**
 * 일정.
 *
 * **성격이 다른 두 가지를 한 화면에 이어 붙였더니 너무 길었다.**
 *
 *   신고·납부 마감 — 이 날까지 해야 한다. 매달 돌아온다.
 *   시행 예정 법령 — 언젠가 바뀐다. 지금은 종전 기준이다.
 *
 * 앞의 것은 할 일이고 뒤의 것은 알아 둘 일이다. 하나로 흘려 두면
 * 마감을 보러 온 사람이 법령 쉰 건을 지나쳐야 했다. 안에서 갈랐다.
 *
 * 검색은 지금 보고 있는 쪽만 좁힌다. 두 목록을 한 검색창으로 뒤지면
 * "부가세" 를 쳤을 때 마감과 법령이 섞여 나오고, 그건 찾기 탭이 하는
 * 일이다. 여기서는 각자의 목록 안에서 좁히기만 한다.
 */
const VIEWS = [
  { key: 'deadline', label: '신고·납부 마감' },
  { key: 'law', label: '시행 예정 법령' },
] as const;

type ViewKey = (typeof VIEWS)[number]['key'];

const BUCKETS = [
  { key: 'month', label: '이번 달 안', note: '30일 이내', within: 30 },
  { key: 'quarter', label: '3개월 안', note: '31~90일', within: 90 },
  { key: 'later', label: '그 이후', note: '90일 넘음', within: Infinity },
] as const;

function bucketOf(item: PublicContentSummary) {
  const days = daysUntil(item.effective_date) ?? Infinity;
  return BUCKETS.find((b) => days <= b.within) ?? BUCKETS[BUCKETS.length - 1];
}

export default async function SchedulePage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const view = (params.view === 'law' ? 'law' : 'deadline') as ViewKey;
  const q = typeof params.q === 'string' ? params.q.trim() : '';

  let feed: PublicFeed | null = null;
  let deadlines: Deadline[] = [];
  let plan: SharePlan | null = null;
  let error: string | null = null;

  try {
    // 사장님께 돌릴 안내문. 마감 화면에서만 보여준다 — 카톡으로 보내는
    // 것은 "언제까지 뭘 내야 하나" 지 "무슨 법이 바뀌었나" 가 아니다.
    if (view === 'deadline') {
      plan = await publicApi.sharePlan(45);
    }
    if (view === 'law') {
      feed = await publicApi.feed({
        q: q || undefined,
        effective_from: seoulToday(),
        content_kind: ['POLICY', 'BILL', 'SUPPORT'],
        limit: 100,
      });
    } else {
      // 반년치를 받아 온다. 마감은 열세 개 규칙에서 나오는 것이라
      // 반년이어도 서른 건 안팎이고, DB 를 안 보므로 부담이 없다.
      deadlines = await publicApi.calendar(180);
    }
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  // 마감은 건수가 적어 화면에서 좁힌다. 서버에 검색을 붙일 이유가 없다.
  const shownDeadlines = q
    ? deadlines.filter((d) => (d.title + d.note + d.audience_label).includes(q))
    : deadlines;

  const items = [...(feed?.items ?? [])].sort(
    (a, b) => (daysUntil(a.effective_date) ?? 1e9) - (daysUntil(b.effective_date) ?? 1e9),
  );

  const href = (next: ViewKey) =>
    `/upcoming?view=${next}${q ? `&q=${encodeURIComponent(q)}` : ''}`;

  return (
    <div className="min-h-screen pb-20">
      <Masthead active="schedule" />

      <main className="mx-auto max-w-page px-4">
        <section className="pb-4 pt-5">
          <p className="text-meta font-semibold text-ink-3">앞으로 할 일</p>
          <h1 className="mt-1 text-display text-ink">일정</h1>
        </section>

        <form action="/upcoming" className="flex items-center gap-2 pb-3">
          <input type="hidden" name="view" value={view} />
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder={view === 'deadline' ? '부가세, 원천세, 법인세' : '법령명으로 좁히기'}
            aria-label="일정 검색"
            className="h-12 min-w-0 flex-1 rounded-field bg-surface px-4 text-[15px] text-ink shadow-[var(--lift)] outline-none placeholder:text-ink-3 focus:ring-2 focus:ring-accent"
          />
          <button type="submit" className="btn-primary shrink-0">
            검색
          </button>
        </form>

        <div className="chips pb-5">
          {VIEWS.map((v) => (
            <Link key={v.key} href={href(v.key)} className={`chip ${view === v.key ? 'chip-on' : ''}`}>
              {v.label}
            </Link>
          ))}
        </div>

        {plan?.text ? <ShareCard text={plan.text} title="사장님께 돌리기" note="이번 달" /> : null}

        {error ? (
          <div className="card pad">
            <p className="text-card text-danger">불러오지 못했습니다</p>
            <p className="mt-1.5 text-body text-ink-2">{error}</p>
          </div>
        ) : view === 'deadline' ? (
          <DeadlineView deadlines={shownDeadlines} q={q} />
        ) : (
          <LawView items={items} total={feed?.total ?? items.length} q={q} />
        )}
      </main>
    </div>
  );
}

function DeadlineView({ deadlines, q }: { deadlines: Deadline[]; q: string }) {
  if (deadlines.length === 0) {
    return (
      <div className="card px-6 py-14 text-center">
        <p className="text-card text-ink">
          {q ? `"${q}" 로 찾은 마감이 없습니다` : '다가오는 마감이 없습니다'}
        </p>
        {q ? (
          <Link href="/upcoming" className="btn-quiet mt-5">
            전체 보기
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-2.5">
        {deadlines.map((d) => (
          <DeadlineCard key={`${d.date}-${d.title}`} deadline={d} />
        ))}
      </div>
      {/*
        **누구에게 어느 것이 해당하는지는 말하지 않는다.**
        과세유형·결산월·반기납부 여부에 따라 갈리고, 그걸 알려면 사업자
        정보가 있어야 하는데 우리에겐 없다. 없는 것을 아는 척하지 않는다.
      */}
      <p className="px-1 pt-4 text-meta leading-relaxed text-ink-3">
        일반 일정입니다. 과세유형·결산월·반기납부 여부에 따라 기한이 다를 수 있고, 마감일이
        공휴일이면 다음 영업일로 밀립니다.
      </p>
    </>
  );
}

function LawView({
  items,
  total,
  q,
}: {
  items: PublicContentSummary[];
  total: number;
  q: string;
}) {
  if (items.length === 0) {
    return (
      <div className="card px-6 py-14 text-center">
        <p className="text-card text-ink">
          {q ? `"${q}" 로 찾은 것이 없습니다` : '시행 예정인 것이 없습니다'}
        </p>
        <p className="mx-auto mt-2 max-w-sm text-body text-ink-2">
          {q ? '다른 낱말로 찾아보세요.' : '공포된 개정이 모두 시행됐거나, 아직 수집되지 않았습니다.'}
        </p>
        {q ? (
          <Link href="/upcoming?view=law" className="btn-quiet mt-5">
            전체 보기
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <>
      {/*
        이 목록에서 가장 위험한 오해는 "이미 바뀌었구나" 다.
        알약이 아니라 문장으로, 목록보다 먼저 둔다.
      */}
      <div className="card mb-4 border-l-4 border-warn px-4 py-3.5">
        <p className="text-[14.5px] font-bold text-ink">지금은 종전 기준이 적용됩니다.</p>
        <p className="mt-1 text-meta leading-relaxed text-ink-2">
          아래는 공포는 됐지만 아직 시행되지 않은 것들입니다. 시행일 전까지는 예전 기준으로
          신고·납부하시면 됩니다.
        </p>
      </div>

      {BUCKETS.map((bucket) => {
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
      })}

      <p className="pt-6 text-center text-meta text-ink-3">전체 {total}건</p>
    </>
  );
}
