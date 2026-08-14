import Link from 'next/link';

import { ContentCard, NewsCard } from '@/components/Card';
import { Masthead } from '@/components/Masthead';
import { API_BASE, API_BASE_IS_DEFAULT, publicApi } from '@/lib/api';
import { daysUntil, seoulToday, todayLabel } from '@/lib/format';
import type { NewsFeed, PublicContentSummary, PublicFeed } from '@/lib/types';

/*
  하루 한 번 배치가 돌 때만 내용이 바뀐다. 2분 캐시로 두면 아침에
  여러 사람이 같은 화면을 열어도 왕복은 한 번이다.
*/
export const revalidate = 120;

/**
 * 오늘.
 *
 * **하루에 한 번 여는 화면이고, 한 번 훑으면 끝나야 한다.**
 *
 * 예전에는 자료 종류대로 탭이 갈려 있어서 아침에 셋을 다 눌러 봐야
 * 오늘 뭐가 있는지 알 수 있었다. 그래서 한 화면으로 합쳤다.
 *
 *   지금 확인   — 오늘 읽어야 할 것
 *   곧 시행     — 미리 준비할 것 (몇 건인지만, 자세한 건 일정 탭)
 *   확인 전 소식 — 언론 보도. 확정 아님을 눈으로 구분되게
 *
 * 합치되 **확인된 것과 확인 전을 섞지 않는다.** 그 구분이 이 서비스가
 * 파는 것이고, 섞이는 순간 전부 못 믿을 것이 된다. 구획을 나누고
 * 알약 색을 다르게 두어 스크롤하다 경계를 지나는 것이 보이게 한다.
 */

/** "지금 확인" 에 올릴 최대 건수. 다섯을 넘기면 그것도 그냥 목록이 된다. */
const NOW_MAX = 4;

/** "지금 확인" 에 올릴 시행일 범위. 90일이면 다음 신고 한 번은 지나간다. */
const HORIZON_DAYS = 90;

/** 오늘 화면에 얹을 뉴스 수. 여기는 훑는 자리지 읽는 자리가 아니다. */
const PREANNOUNCE_MAX = 6;
const NEWS_MAX = 4;

/**
 * 오늘 먼저 봐야 하는가.
 *
 * 중요도만 보면 안 된다. 중요도는 법령 이름으로 정해지는데 그 법이
 * 개정됐어도 실질 변경이 없을 수 있다. 실제로 1번이 이랬다.
 *
 *   [중요] …부가가치세 면제 대상임을 고시했으며, 사업자에게
 *          실질적인 변경사항은 없습니다.
 *
 * 화면을 열자마자 "바뀐 것 없습니다" 를 읽으면 그 자리는 죽은 자리가 된다.
 *
 * `actionable` 이 없는 응답도 있다(프론트가 먼저 배포되면). 없는 값은
 * "모른다" 이지 "아니다" 가 아니므로 명시적으로 false 일 때만 뺀다.
 */
function isUrgent(item: PublicContentSummary): boolean {
  if (item.actionable === false) return false;
  if (item.risk_level !== 'CRITICAL' && item.risk_level !== 'HIGH') return false;
  const days = daysUntil(item.effective_date);
  return days === null || days <= HORIZON_DAYS;
}

export default async function TodayPage() {
  let feed: PublicFeed | null = null;
  let upcoming: PublicFeed | null = null;
  let preannounced: PublicFeed | null = null;
  let tribunal: PublicFeed | null = null;
  let news: NewsFeed | null = null;
  let error: string | null = null;

  try {
    [feed, upcoming, preannounced, tribunal, news] = await Promise.all([
      publicApi.feed({ limit: 40 }),
      // 건수는 서버에 묻는다. 화면에 나온 것에서 세면 틀린다 —
      // 예전에 레일에 15 라고 떴는데 실제로는 34 건이었다.
      publicApi.feed({ effective_from: seoulToday(), limit: 1 }),
      // 입법예고. 이 서비스가 파는 것이 여기다 — 공포된 뒤에 아는 사람과
      // 예고 단계에서 아는 사람은 고객에게 할 말이 다르다.
      publicApi.feed({ legal_status: ['PREANNOUNCED'], limit: PREANNOUNCE_MAX }),
      publicApi.feed({ content_kind: ['TRIBUNAL'], limit: 3 }),
      publicApi.news({ days: 7, limit: NEWS_MAX }),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  // **예고는 확정된 것과 섞지 않는다.**
  //
  // 상태만 다른 같은 모양의 카드로 이어 붙이면, 스크롤하다 「소득세법
  // 일부개정법률안」을 이미 바뀐 것으로 읽는다. 이 화면에서 가장 위험한
  // 오해가 그것이다. 자리를 따로 주고 제목에서 확정이 아니라고 먼저 말한다.
  const items = (feed?.items ?? []).filter((i) => i.legal_status !== 'PREANNOUNCED');
  const urgent = items.filter(isUrgent).slice(0, NOW_MAX);
  const urgentIds = new Set(urgent.map((i) => i.id));
  const recent = items.filter((i) => !urgentIds.has(i.id)).slice(0, 6);
  const upcomingCount = upcoming?.total ?? 0;
  const notices = preannounced?.items ?? [];
  const noticeTotal = preannounced?.total ?? 0;

  const deadlineCount = items.filter((i) => {
    const days = daysUntil(i.application_end);
    return days !== null && days >= 0 && days <= 14;
  }).length;

  return (
    <div className="min-h-screen pb-20">
      <Masthead active="today" />

      <main className="mx-auto max-w-page px-4">
        <section className="pb-5 pt-5">
          <p className="text-meta font-semibold text-ink-3">{todayLabel()}</p>
          <h1 className="mt-1 text-display text-ink">
            {urgent.length > 0
              ? `오늘 확인할 것 ${urgent.length}건`
              : '오늘 새로 확인할 것은 없습니다'}
          </h1>
        </section>

        {error ? <ErrorCard message={error} /> : null}

        {/*
          숫자 세 개를 대시보드처럼 늘어놓지 않는다. 각각이 서로 다른
          행동으로 이어질 때만 자리를 준다 — 0 이면 아예 안 그린다.
          "0" 이 세 개 늘어선 화면은 아무 일도 없다는 사실조차 못 알려준다.
        */}
        {/*
          하나뿐일 때는 가로로 눕힌다. 두 칸짜리 격자에 한 장만 놓으면
          오른쪽이 비어 "뭔가 안 불러와졌나" 로 읽힌다.
        */}
        {upcomingCount > 0 || deadlineCount > 0 ? (
          <div
            className={`grid gap-2.5 pb-6 ${
              deadlineCount > 0 && upcomingCount > 0 ? 'grid-cols-2' : 'grid-cols-1'
            }`}
          >
            {deadlineCount > 0 ? (
              <Stat
                value={deadlineCount}
                label="마감 임박"
                note="2주 안"
                href="/?deadline=7"
                wide={upcomingCount === 0}
                danger
              />
            ) : null}
            {upcomingCount > 0 ? (
              <Stat
                value={upcomingCount}
                label="곧 시행"
                note="미리 준비"
                href="/upcoming"
                wide={deadlineCount === 0}
              />
            ) : null}
          </div>
        ) : null}

        {urgent.length > 0 ? (
          <Section title="지금 확인" note="중요도·마감 순">
            {urgent.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </Section>
        ) : null}

        {/*
          확정된 것보다 **먼저** 놓는다. 공포는 이미 끝난 일이고, 예고는
          아직 의견을 낼 수 있는 기간이 남아 있다. 지금 움직일 수 있는
          쪽이 위에 있어야 한다.
        */}
        {notices.length > 0 ? (
          <Section
            title="예고 단계"
            href="/search?kind=PREANNOUNCED"
            hrefLabel={noticeTotal > notices.length ? `전체 ${noticeTotal}건` : '전체 보기'}
          >
            <p className="-mt-1 pb-1 text-meta leading-relaxed text-ink-3">
              정부가 이렇게 바꾸겠다고 내놓고 의견을 받는 중입니다. 아직 확정된 개정이 아니며
              내용이 달라지거나 무산될 수 있습니다.
            </p>
            {notices.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </Section>
        ) : null}

        {recent.length > 0 ? (
          <Section title="최근 확정된 것" href="/search" hrefLabel="전체 보기">
            {recent.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </Section>
        ) : null}

        {tribunal && tribunal.items.length > 0 ? (
          <Section
            title="비슷한 사안, 이렇게 판단됐습니다"
            note="조세심판원"
            href="/search?kind=TRIBUNAL"
            hrefLabel="더 보기"
          >
            {tribunal.items.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </Section>
        ) : null}

        {/*
          경계를 눈에 보이게 둔다. 위는 검수를 거친 것이고 아래는 아니다.
          같은 모양으로 이어 붙이면 스크롤하다 경계를 못 알아챈다.
        */}
        {news && news.items.length > 0 ? (
          <section className="pt-9">
            <div className="flex items-baseline justify-between gap-3 pb-1">
              <h2 className="section-title">확인 전 소식</h2>
              <Link
                href="/search?kind=NEWS"
                className="shrink-0 text-meta font-bold text-accent hover:underline"
              >
                더 보기
              </Link>
            </div>
            <p className="pb-3 text-meta leading-relaxed text-ink-3">
              {news.caveat ??
                '언론 보도입니다. 공식 원문으로 확인되지 않았으며 확정된 제도 변경이 아닐 수 있습니다.'}
            </p>
            <div className="flex flex-col gap-2.5">
              {news.items.map((item) => (
                <NewsCard key={item.id} item={item} />
              ))}
            </div>
          </section>
        ) : null}

        <footer className="mt-14 px-1 text-meta leading-relaxed text-ink-3">
          <p className="font-semibold text-ink-2">이 서비스는 일반적인 제도 변경을 안내합니다.</p>
          <p className="mt-1 max-w-reading">
            개별 사업자의 세액이나 적용 여부는 사실관계에 따라 달라질 수 있습니다. 판단이 필요한
            사안은 세무전문가와 상담하시기 바랍니다.
          </p>
          <p className="mt-4">모든 내용은 공식 원문 링크와 함께 제공됩니다 · TaxBriefing</p>
        </footer>
      </main>
    </div>
  );
}

function Section({
  title,
  note,
  href,
  hrefLabel,
  children,
}: {
  title: string;
  note?: string;
  href?: string;
  hrefLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="pt-7 first:pt-0">
      <div className="flex items-baseline justify-between gap-3 pb-3">
        <h2 className="section-title">{title}</h2>
        {href ? (
          <Link href={href} className="shrink-0 text-meta font-bold text-accent hover:underline">
            {hrefLabel ?? '더 보기'}
          </Link>
        ) : note ? (
          <span className="shrink-0 text-meta text-ink-3">{note}</span>
        ) : null}
      </div>
      <div className="flex flex-col gap-2.5">{children}</div>
    </section>
  );
}

function Stat({
  value,
  label,
  note,
  href,
  wide,
  danger,
}: {
  value: number;
  label: string;
  note: string;
  href: string;
  wide?: boolean;
  danger?: boolean;
}) {
  const number = (
    <span
      className={`tabular text-[28px] font-extrabold leading-none ${
        danger ? 'text-danger' : 'text-ink'
      }`}
    >
      {value}
    </span>
  );

  if (wide) {
    return (
      <Link href={href} className="card-tap flex items-center gap-3.5 px-5 py-4">
        {number}
        <span className="min-w-0">
          <span className="block text-[15px] font-bold text-ink">{label}</span>
          <span className="block text-meta text-ink-3">{note}</span>
        </span>
        <span aria-hidden className="ml-auto text-[18px] text-ink-3">
          ›
        </span>
      </Link>
    );
  }

  return (
    <Link href={href} className="card-tap px-4 py-4">
      {number}
      <span className="mt-2 block text-[14.5px] font-bold text-ink">{label}</span>
      <span className="mt-0.5 block text-meta text-ink-3">{note}</span>
    </Link>
  );
}

/**
 * 실패 화면은 **어디에 연결하려 했는지**를 보여준다.
 * 그게 없으면 "환경변수를 확인하세요"만 반복하게 된다.
 */
function ErrorCard({ message }: { message: string }) {
  return (
    <div className="card pad">
      <p className="text-card text-danger">정보를 불러오지 못했습니다</p>
      <p className="mt-1.5 text-body text-ink-2">{message}</p>
      <p className="mt-4 break-all font-mono text-meta text-ink-3">{API_BASE}</p>
      {API_BASE_IS_DEFAULT ? (
        <p className="mt-3 text-meta leading-relaxed text-ink-2">
          <strong className="font-bold text-danger">NEXT_PUBLIC_API_BASE 가 없습니다.</strong> 배포
          환경의 환경변수에 API 주소를 넣고 재배포하세요.
        </p>
      ) : (
        <p className="mt-3 text-meta leading-relaxed text-ink-3">
          주소는 설정돼 있으나 응답이 없습니다. API 서버가 켜져 있는지, 이 사이트 주소가 서버의
          허용 목록(CORS)에 있는지 확인하세요.
        </p>
      )}
    </div>
  );
}
