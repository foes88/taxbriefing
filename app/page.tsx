import Link from 'next/link';

import { LeadItem, RecordRow } from '@/components/ContentCard';
import { FilterBar } from '@/components/FilterBar';
import { IndexRail } from '@/components/IndexRail';
import { Masthead } from '@/components/Masthead';
import { MonthStrip } from '@/components/MonthNav';
import { API_BASE, API_BASE_IS_DEFAULT, publicApi } from '@/lib/api';
import { groupByDate, todayLabel } from '@/lib/format';
import type { IndustryBucket, MonthBucket, PublicContentSummary, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/**
 * "먼저 볼 것" 에 올릴 최대 건수.
 *
 * 다섯을 넘기면 그것도 목록이 되고, 목록이 두 개면 어느 쪽부터 볼지
 * 다시 고민하게 된다. 편집은 덜어내는 일이다.
 */
const LEAD_MAX = 4;

/**
 * 한 번에 보여줄 기록 수와, "더 보기"로 늘어나는 폭.
 *
 * 전부 내려받던 시절 이 페이지는 세로 21,600px 이었다. 118건이 한 화면에
 * 깔리면 스크롤바가 실오라기가 되고, 아래에 뭐가 있는지 감각이 사라진다.
 *
 * 페이지 번호를 쓰지 않는 이유: 목록이 날짜별로 묶여 있어서 번호로 자르면
 * 같은 날 공포분이 두 페이지에 걸쳐 쪼개진다. 그리고 사장님은 위에서부터
 * 훑다가 멈추지, "3페이지에 있었는데"로 기억하지 않는다.
 */
const PAGE_SIZE = 30;

function pick(params: Record<string, string | string[] | undefined>, key: string) {
  const value = params[key];
  if (value === undefined) return undefined;
  return Array.isArray(value) ? value : [value];
}

/**
 * "더 보기" 링크의 주소.
 *
 * 걸어 둔 조건(업종·월·검색어)을 **그대로 들고 간다.** 더 보기를 눌렀더니
 * 필터가 풀리면 처음부터 다시 좁혀야 한다.
 */
function nextPageQuery(
  params: Record<string, string | string[] | undefined>,
  show: number,
): string {
  const next = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (key === 'show' || value === undefined) continue;
    for (const v of Array.isArray(value) ? value : [value]) next.append(key, v);
  }
  next.set('show', String(show + PAGE_SIZE));
  return next.toString();
}

/**
 * 오늘 먼저 봐야 하는 것인가.
 *
 * 중요도만 보면 안 된다. 중요도는 법령 이름으로 정해지는데, 그 법이 개정됐어도
 * 실질 변경이 없을 수 있다. 실제로 "먼저 볼 것" 1번이 이랬다.
 *
 *   [중요] 국제경기대회 지원법에 따라 설립된 조직위원회가 부가가치세 면제
 *          대상임을 고시했으며, 사업자에게 실질적인 변경사항은 없습니다.
 *
 * 화면을 열자마자 "바뀐 것 없습니다"를 읽게 되면 그 자리는 죽은 자리가 된다.
 * 기록에는 남기되 먼저 볼 것에는 올리지 않는다.
 *
 * `actionable` 이 아직 없는 API 응답도 있다. 프론트가 먼저 배포되면 그렇다.
 * 그때 `!item.actionable` 로 쓰면 **모든 항목이 탈락해 이 구획이 통째로 사라진다.**
 * 실제로 그렇게 사라졌다. 없는 값은 "모른다"이지 "아니다"가 아니므로,
 * 명시적으로 false 일 때만 뺀다.
 */
function isLead(item: PublicContentSummary): boolean {
  if (item.actionable === false) return false;
  return item.risk_level === 'CRITICAL' || item.risk_level === 'HIGH';
}

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const month = typeof params.month === 'string' ? params.month : undefined;
  const from = typeof params.from === 'string' ? params.from : undefined;
  const to = typeof params.to === 'string' ? params.to : undefined;
  // show 는 "몇 건까지 펼쳐 봤는가"다. URL 에 있으므로 뒤로 가기와 공유가 된다.
  const show = Math.min(300, Math.max(PAGE_SIZE, Number(params.show) || PAGE_SIZE));
  const filtered = Object.keys(params).some((k) => k !== 'show');

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
        limit: show,
      }),
      publicApi.months(),
      publicApi.industries(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const items = feed?.items ?? [];
  const activeMonth = months.find((m) => m.month === month);
  const activeIndustries = industries.filter((item) =>
    (pick(params, 'industries') ?? []).includes(item.code),
  );

  // 서버가 이미 중요도 → 마감 임박 → 최신 순으로 정렬해 준다.
  // 앞에서부터 자르면 그게 곧 우선순위다 (§FR-USR-001).
  const lead = items.filter(isLead).slice(0, LEAD_MAX);
  const leadIds = new Set(lead.map((i) => i.id));
  const rest = items.filter((i) => !leadIds.has(i.id));
  const groups = groupByDate(rest, (i) => i.promulgation_date);

  const scope = [
    activeIndustries.map((i) => i.label).join(' · '),
    activeMonth?.label,
    from || to ? `${from ?? '처음'}~${to ?? '오늘'} 공포` : '',
    q ? `"${q}"` : '',
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="min-h-screen">
      <Masthead active="policy" />

      <main className="mx-auto max-w-page px-4 pb-24">
        <section className="flex flex-wrap items-end justify-between gap-x-8 gap-y-2 pb-4 pt-8">
          <div className="min-w-0">
            <p className="gutter-date">{todayLabel()}</p>
            <h1 className="mt-1.5 text-display text-ink">
              {scope || '오늘 확인할 세무정보'}
            </h1>
          </div>
          <p className="max-w-[22rem] text-[13px] leading-relaxed text-ink-3">
            법령·관보 등 <strong className="font-semibold text-ink-2">공식 원문</strong>으로 사실을
            확인하고, 세무전문가가 검수한 내용만 올립니다.
          </p>
        </section>

        {months.length > 0 ? (
          <div className="border-y border-rule py-2.5 lg:hidden">
            <MonthStrip months={months} active={month} />
          </div>
        ) : null}

        <div className="grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
          {/* ── 좌측: 색인 레일 ── */}
          <div className="hidden lg:sticky lg:top-6 lg:block lg:self-start">
            <IndexRail industries={industries} months={months} />
          </div>

          <div className="min-w-0">
            <div className="panel px-4 py-3.5">
              <FilterBar />
            </div>

            {error ? (
              <ErrorState message={error} />
            ) : items.length === 0 ? (
              <EmptyState filtered={filtered} />
            ) : (
              <>
                {lead.length > 0 ? (
                  <section className="mt-7">
                    <div className="flex items-center justify-between gap-3 pb-2.5">
                      <h2 className="section-mark">먼저 볼 것</h2>
                      <span className="text-[12.5px] text-ink-3">중요도·마감 순</span>
                    </div>
                    {/* 판(panel)에 올린다. 배경이 다르면 "골라 놓은 것"으로 읽힌다. */}
                    <ul className="panel divide-y divide-rule">
                      {lead.map((item, index) => (
                        <li key={item.id}>
                          <LeadItem item={item} index={index} />
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                <section className="mt-10">
                  <div className="flex items-center justify-between gap-3 pb-2.5">
                    <h2 className="section-mark">전체 기록</h2>
                    <span className="tabular shrink-0 text-[12.5px] font-semibold text-ink-3">
                      {feed?.total ?? items.length}건
                    </span>
                  </div>

                  {/*
                    일자가 표제이고 그 아래에 항목이 딸린다. 관보가 호(號)로
                    묶이는 방식이다. 행마다 날짜를 반복하던 거터를 없앴다 —
                    같은 날 공포분이 여러 건이면 같은 숫자만 연달아 나왔다.
                  */}
                  <div className="panel overflow-hidden">
                    {groups.map((group) => (
                      <section key={group.date ?? 'undated'}>
                        <h3 className="flex items-baseline gap-3 border-y border-rule bg-surface-sunk px-4 py-2 first:border-t-0 sm:px-5">
                          <span className="tabular text-[13px] font-extrabold tracking-tight text-ink">
                            {group.heading}
                          </span>
                          <span className="text-[11.5px] text-ink-3">공포</span>
                          <span className="tabular ml-auto text-[12px] font-semibold text-ink-3">
                            {group.items.length}
                          </span>
                        </h3>
                        <ul className="divide-y divide-rule">
                          {group.items.map((item) => (
                            <li key={item.id}>
                              <RecordRow item={item} />
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>

                  {feed && feed.total > items.length ? (
                    <div className="mt-8 flex flex-col items-center gap-2.5">
                      <Link
                        href={`?${nextPageQuery(params, show)}`}
                        scroll={false}
                        className="btn-quiet w-full max-w-xs justify-center"
                      >
                        {Math.min(PAGE_SIZE, feed.total - items.length)}건 더 보기
                      </Link>
                      <p className="tabular text-[12.5px] text-ink-3">
                        {items.length} / {feed.total}건
                      </p>
                    </div>
                  ) : feed && feed.total > PAGE_SIZE ? (
                    <p className="mt-8 text-center text-[12.5px] text-ink-3">
                      전체 {feed.total}건을 모두 보셨습니다.
                    </p>
                  ) : null}
                </section>
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="mt-8 border-t-4 border-band bg-surface">
        <div className="mx-auto max-w-page px-4 py-10 text-[13px] leading-relaxed text-ink-3">
          <p className="font-semibold text-ink-2">이 서비스는 일반적인 제도 변경을 안내합니다.</p>
          <p className="mt-1.5 max-w-reading">
            개별 사업자의 세액이나 적용 여부는 사실관계에 따라 달라질 수 있습니다. 판단이 필요한
            사안은 세무전문가와 상담하시기 바랍니다.
          </p>
          <p className="mt-6 border-t border-rule pt-4">
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
    <div className="mt-7 border-l-[3px] border-seal bg-surface p-6">
      <p className="text-headline text-seal">정보를 불러오지 못했습니다</p>
      <p className="mt-2 text-[15px] text-ink-2">{message}</p>

      <dl className="mt-5 border-t border-rule pt-4 text-[13px]">
        <dt className="label">연결 시도한 주소</dt>
        <dd className="mt-1.5 break-all font-mono text-[12.5px] text-ink">{API_BASE}</dd>
      </dl>

      {API_BASE_IS_DEFAULT ? (
        <p className="mt-4 text-[13px] leading-relaxed text-ink-2">
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
    <div className="mt-7 border border-rule bg-surface px-6 py-16 text-center">
      <p className="text-headline text-ink">
        {filtered ? '조건에 맞는 정보가 없습니다' : '아직 게시된 브리핑이 없습니다'}
      </p>
      <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
        {filtered
          ? '조건을 줄이거나 다른 달을 선택해 보세요.'
          : '수집된 공식 원문을 세무전문가가 검수·승인하면 여기에 표시됩니다.'}
      </p>
      <Link href={filtered ? '/' : '/admin'} className="btn-quiet mt-6">
        {filtered ? '전체 보기' : '관리자 화면으로'}
      </Link>
    </div>
  );
}
