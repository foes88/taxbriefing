import Link from 'next/link';

import { Masthead } from '@/components/Masthead';
import { publicApi } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { PublicContentSummary, PublicFeed } from '@/lib/types';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const PAGE_SIZE = 20;

/**
 * 실무 TIP — 조세심판원 심판례.
 *
 * **법령은 "무엇이 바뀌었나" 를, 심판례는 "그래서 어떻게 판단되나" 를 알려준다.**
 * 같은 조문을 읽어도 심판례를 아는 사람이 다른 답을 낸다. 세무사무소 직원이
 * 남보다 앞서는 지점이 여기다.
 *
 * 정책 화면과 **다르게 그린다.** 심판례에는 시행일도 정책 상태도 없다.
 * 그 자리에 들어가는 것은 세목과 결론(인용/기각)이다 — 비슷한 사안을 맡았을 때
 * 다툴 만한지 아닌지가 그 두 값에서 갈린다.
 */
const OUTCOMES = [
  { key: '인용', label: '인용', note: '납세자 주장이 받아들여짐' },
  { key: '일부인용', label: '일부인용', note: '일부만 받아들여짐' },
  { key: '기각', label: '기각', note: '처분이 유지됨' },
] as const;

/** 제목 끝의 " — 인용" 에서 결론을 읽는다. 수집기가 주문에서 뽑아 붙인 값이다. */
function outcomeOf(item: PublicContentSummary): string | null {
  const match = item.title.match(/—\s*(인용|일부인용|기각|각하|재조사)\s*$/);
  return match ? match[1] : null;
}

function titleWithoutOutcome(item: PublicContentSummary): string {
  return item.title.replace(/\s*—\s*(인용|일부인용|기각|각하|재조사)\s*$/, '');
}

export default async function TipsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === 'string' ? params.q : undefined;
  const outcome = typeof params.outcome === 'string' ? params.outcome : undefined;
  const show = Math.min(200, Math.max(PAGE_SIZE, Number(params.show) || PAGE_SIZE));

  let feed: PublicFeed | null = null;
  let error: string | null = null;

  try {
    feed = await publicApi.feed({ q, content_kind: ['TRIBUNAL'], limit: show });
  } catch (e) {
    error = e instanceof Error ? e.message : '알 수 없는 오류';
  }

  const all = feed?.items ?? [];
  const items = outcome ? all.filter((i) => outcomeOf(i) === outcome) : all;
  const counts = Object.fromEntries(
    OUTCOMES.map((o) => [o.key, all.filter((i) => outcomeOf(i) === o.key).length]),
  );

  return (
    <div className="min-h-screen">
      <Masthead active="tips" />

      <main className="mx-auto max-w-[56rem] px-4 pb-24">
        <section className="flex flex-wrap items-end justify-between gap-x-8 gap-y-2 pb-4 pt-8">
          <div>
            <p className="gutter-date">조세심판원 결정</p>
            <h1 className="mt-1.5 text-display text-ink">실무 TIP</h1>
          </div>
          <p className="max-w-[24rem] text-[13px] leading-relaxed text-ink-3">
            같은 조문이라도 실제로 어떻게 판단되는지는 다릅니다. 비슷한 사안을 맡았을 때
            <strong className="font-semibold text-ink-2"> 다툴 만한지</strong>를 여기서 가늠하세요.
          </p>
        </section>

        <form action="/tips" className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            name="q"
            defaultValue={q ?? ''}
            placeholder="쟁점으로 검색 — 가지급금, 업무용승용차, 세금계산서"
            className="h-10 min-w-0 flex-1 rounded-[4px] border border-rule-strong bg-surface px-3.5 text-[15px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <button type="submit" className="btn-primary h-10 shrink-0 py-0">
            검색
          </button>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="label pr-0.5">결론</span>
          <Chip href="/tips" label="전체" count={all.length} active={!outcome} />
          {OUTCOMES.map((o) => (
            <Chip
              key={o.key}
              href={`/tips?outcome=${encodeURIComponent(o.key)}`}
              label={o.label}
              count={counts[o.key] ?? 0}
              active={outcome === o.key}
              title={o.note}
            />
          ))}
        </div>

        {error ? (
          <div className="mt-7 border-l-[3px] border-seal bg-surface p-6">
            <p className="text-headline text-seal">불러오지 못했습니다</p>
            <p className="mt-2 text-[15px] text-ink-2">{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="mt-7 border border-rule bg-surface px-6 py-16 text-center">
            <p className="text-headline text-ink">해당하는 심판례가 없습니다</p>
            <p className="mx-auto mt-2.5 max-w-sm text-[15px] leading-relaxed text-ink-2">
              {q ? '검색어를 바꿔 보세요.' : '수집된 심판례가 아직 없습니다.'}
            </p>
            {q || outcome ? (
              <Link href="/tips" className="btn-quiet mt-6">
                전체 보기
              </Link>
            ) : null}
          </div>
        ) : (
          <>
            <div className="mt-7 flex items-center justify-between gap-3 pb-2.5">
              <h2 className="section-mark">최근 결정</h2>
              <span className="tabular shrink-0 text-[12.5px] font-semibold text-ink-3">
                {items.length}건
              </span>
            </div>
            <ul className="panel divide-y divide-rule">
              {items.map((item) => (
                <li key={item.id}>
                  <TipRow item={item} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}

/**
 * 심판례 한 건.
 *
 * 결론을 **제목 앞**에 둔다. 인용인지 기각인지가 읽을지 말지를 정한다.
 * 시행일·상태 배지는 없다 — 심판례는 제도가 아니다.
 */
function TipRow({ item }: { item: PublicContentSummary }) {
  const outcome = outcomeOf(item);
  const accepted = outcome === '인용' || outcome === '일부인용';

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group block px-4 py-4 transition-colors hover:bg-surface-sunk sm:px-5"
    >
      <h3 className="max-w-reading text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
        {outcome ? (
          <span
            className={`tag mr-2 align-[2px] ${
              accepted ? 'bg-state-effective text-white' : 'border border-rule-strong text-ink-3'
            }`}
          >
            {outcome}
          </span>
        ) : null}
        {titleWithoutOutcome(item)}
      </h3>

      <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] text-ink-3">
        {item.promulgation_date ? <span>{formatDate(item.promulgation_date)} 결정</span> : null}
        {item.industry_labels.map((name) => (
          <span key={name} className="flex items-center gap-2.5">
            <span aria-hidden className="text-rule-strong">
              ·
            </span>
            {name}
          </span>
        ))}
      </p>
    </Link>
  );
}

function Chip({
  href,
  label,
  count,
  active,
  title,
}: {
  href: string;
  label: string;
  count: number;
  active: boolean;
  title?: string;
}) {
  return (
    <Link
      href={href}
      title={title}
      className={`shrink-0 whitespace-nowrap rounded-[4px] border px-3 py-1.5 text-[13px] font-semibold transition-colors ${
        active
          ? 'border-accent bg-accent text-white'
          : 'border-rule-strong bg-surface text-ink-2 hover:border-accent hover:text-accent'
      }`}
    >
      {label}
      <span className={`tabular ml-1.5 text-[12px] ${active ? 'text-white/75' : 'text-ink-3'}`}>
        {count}
      </span>
    </Link>
  );
}
