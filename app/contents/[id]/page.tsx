import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Masthead } from '@/components/Masthead';
import { AuthorityTag, Caveat, DeadlineMark, RiskMark, StatusSeal } from '@/components/Seal';
import { ApiRequestError, publicApi } from '@/lib/api';
import { daysUntil, formatDate, formatDateTime } from '@/lib/format';
import type { PublicContentDetail } from '@/lib/types';

export const dynamic = 'force-dynamic';

/**
 * 콘텐츠 상세 (U-03, §10.3 표준 블록).
 *
 * 폼이 아니라 **기록**으로 읽혀야 한다. 관보 한 건을 펼쳐 놓은 모양이다.
 * 배치는 사장님이 판단하는 순서를 따른다.
 *   상태 → 제목 → 요약 → 할 일 → 대상 → 현재/변경
 *
 * 넓은 화면에서는 서지 정보(일자표·출처)를 오른쪽 열로 보낸다.
 * 본문은 읽기 좋은 폭을 유지하면서 화면은 비지 않게 하기 위해서다.
 *
 * §10.4: 현재 기준과 변경 예정을 **같은 문단에 섞지 않는다.**
 */
export default async function ContentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let content: PublicContentDetail;
  try {
    content = await publicApi.content(id);
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) notFound();
    throw e;
  }

  const body = content.body as Record<string, unknown>;
  const list = (key: string): string[] => {
    const value = body[key];
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    if (typeof value === 'string' && value.trim()) return [value.trim()];
    return [];
  };

  const deadline = daysUntil(content.application_end);
  const actions = list('required_actions');

  return (
    <div className="min-h-screen">
      <Masthead compact />

      <main className="mx-auto max-w-page px-4 pb-20">
        <nav className="py-4">
          <Link
            href="/"
            className="text-[13px] font-semibold text-ink-3 transition-colors hover:text-ink"
          >
            ← 오늘의 브리핑
          </Link>
        </nav>

        {content.corrected ? (
          <div className="mb-5 border-l-2 border-seal bg-surface py-3 pl-4 pr-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.11em] text-seal">정정</p>
            <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">
              이전에 안내드린 내용에 수정이 있었습니다. 아래 최신 내용을 확인해 주세요.
            </p>
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start lg:gap-8">
          {/* ── 본문 ── */}
          <article className="min-w-0 border border-rule bg-surface">
            <header className="border-b border-rule px-5 py-7 sm:px-8">
              <div className="flex flex-wrap items-center gap-1.5">
                <RiskMark risk={content.risk_level} />
                <StatusSeal status={content.legal_status} label={content.status_label} />
                {deadline !== null && deadline >= 0 && deadline <= 7 ? (
                  <DeadlineMark days={deadline} />
                ) : null}
              </div>

              <h1 className="mt-3.5 max-w-reading text-display text-ink">{content.title}</h1>

              {content.one_line_summary ? (
                <p className="mt-3.5 max-w-reading text-[16px] leading-relaxed text-ink-2">
                  {content.one_line_summary}
                </p>
              ) : null}

              {content.status_caveat ? (
                <p className="mt-4 border-t border-rule pt-3.5">
                  <Caveat text={content.status_caveat} />
                </p>
              ) : null}
            </header>

            {/* 좁은 화면에서는 일자표를 본문 안에 둔다. */}
            <div className="lg:hidden">
              <DateTable content={content} />
            </div>

            <div className="max-w-reading px-5 py-7 sm:px-8">
              {/*
                번호를 붙이는 이유: 이건 실제로 순서가 있는 절차다.
                순서가 없는 목록에는 번호를 쓰지 않는다.
              */}
              {actions.length > 0 ? (
                <section className="prose-block border-l-2 border-ink pl-4">
                  <h2 className="label">지금 해야 할 일</h2>
                  <ol className="mt-3 flex flex-col gap-2.5">
                    {actions.map((item, i) => (
                      <li key={i} className="flex gap-3 text-[16px] leading-relaxed text-ink">
                        <span className="tabular mt-[2px] shrink-0 text-[13px] font-bold text-ink-3">
                          {String(i + 1).padStart(2, '0')}
                        </span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              <Block title="적용 대상" items={list('affected_users')} />
              <Block title="제외 대상" items={list('excluded_users')} muted />
              <Block title="현재 적용 기준" items={list('current_basis')} />
              <Block title="달라지는 점" items={list('changes')} />
              <Block title="사업자에게 미치는 영향" items={list('business_impact')} />
              <Block title="전문가 확인이 필요한 항목" items={list('needs_expert')} muted />

              {actions.length === 0 && list('changes').length === 0 ? (
                <p className="text-[15px] leading-relaxed text-ink-2">
                  상세 분석이 아직 작성되지 않았습니다. 아래 공식 원문을 확인해 주세요.
                </p>
              ) : null}
            </div>

            {/* 검수 상태는 AI 생성 여부보다 우선해 표시한다 (§10.4). */}
            <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-rule bg-surface-sunk px-5 py-4 sm:px-8">
              <span className="text-[13px] font-semibold text-state-effective">
                세무전문가 검수 완료
              </span>
              <span className="tabular text-[12px] text-ink-3">
                최종 확인 {formatDateTime(content.updated_at)}
              </span>
            </footer>
          </article>

          {/* ── 서지 정보 (넓은 화면에서만 우측 열) ── */}
          <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
            <div className="hidden border border-rule bg-surface lg:block">
              <h2 className="border-b border-rule px-4 py-2.5">
                <span className="label">주요 일자</span>
              </h2>
              <dl className="divide-y divide-rule">
                <DateRow label="발표일" value={content.announcement_date} />
                <DateRow label="공포일" value={content.promulgation_date} />
                <DateRow label="시행일" value={content.effective_date} emphasis />
                <DateRow label="신청 마감" value={content.application_end} />
              </dl>
            </div>

            {/* 공식 출처 — 접지 않고 그대로 노출한다 (§10.4). 이게 신뢰의 근거다. */}
            <section className="border border-rule bg-surface">
              <h2 className="border-b border-rule px-4 py-2.5">
                <span className="label">공식 출처</span>
              </h2>
              <ul className="divide-y divide-rule">
                {content.sources.map((source) => (
                  <li key={source.url} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <AuthorityTag grade={source.authority} />
                      <span className="text-[12px] font-semibold text-ink-2">
                        {source.publisher}
                      </span>
                      {source.role === 'PRIMARY' ? (
                        <span className="text-[11px] font-semibold text-ink-3">주 근거</span>
                      ) : null}
                    </div>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1.5 block text-[14px] font-semibold leading-snug text-ink underline decoration-rule-strong decoration-1 underline-offset-4 transition-colors hover:decoration-ink"
                    >
                      {source.title}
                      <span aria-hidden className="ml-1 text-ink-3">
                        ↗
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>

            <p className="text-[12px] leading-relaxed text-ink-3">
              이 안내는 일반적인 제도 변경을 설명합니다. 개별 사업자의 적용 여부와 세액은
              사실관계에 따라 달라질 수 있으므로 세무전문가와 상담하시기 바랍니다.
            </p>

            <Link href="/" className="btn-quiet w-full">
              다른 브리핑 보기
            </Link>
          </aside>
        </div>
      </main>
    </div>
  );
}

/** 좁은 화면용 일자표. 각 날짜는 별도 필드다 (FR-VER-003). */
function DateTable({ content }: { content: PublicContentDetail }) {
  return (
    <dl className="grid grid-cols-2 border-b border-rule">
      <DateCell label="발표일" value={content.announcement_date} />
      <DateCell label="공포일" value={content.promulgation_date} />
      <DateCell label="시행일" value={content.effective_date} emphasis />
      <DateCell label="신청 마감" value={content.application_end} />
    </dl>
  );
}

function DateCell({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string | null;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`border-rule px-4 py-3.5 [&:nth-child(-n+2)]:border-b [&:nth-child(odd)]:border-r ${
        emphasis ? 'bg-surface-sunk' : ''
      }`}
    >
      <dt className="label">{label}</dt>
      <dd
        className={`tabular mt-1.5 text-[14px] ${
          value
            ? emphasis
              ? 'font-bold text-ink'
              : 'font-semibold text-ink-2'
            : 'font-semibold text-state-pending'
        }`}
      >
        {value ? formatDate(value) : '확인 필요'}
      </dd>
    </div>
  );
}

function DateRow({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string | null;
  emphasis?: boolean;
}) {
  return (
    <div className={`flex items-baseline justify-between gap-3 px-4 py-2.5 ${emphasis ? 'bg-surface-sunk' : ''}`}>
      <dt className="text-[12.5px] font-semibold text-ink-3">{label}</dt>
      <dd
        className={`tabular text-[13.5px] ${
          value
            ? emphasis
              ? 'font-bold text-ink'
              : 'font-semibold text-ink-2'
            : 'font-semibold text-state-pending'
        }`}
      >
        {value ? formatDate(value) : '확인 필요'}
      </dd>
    </div>
  );
}

function Block({ title, items, muted }: { title: string; items: string[]; muted?: boolean }) {
  if (items.length === 0) return null;
  return (
    <section className="prose-block">
      <h2 className="label">{title}</h2>
      <ul className="mt-2.5 flex flex-col gap-2">
        {items.map((item, i) => (
          <li
            key={i}
            className={`flex gap-2.5 text-[16px] leading-relaxed ${muted ? 'text-ink-2' : 'text-ink'}`}
          >
            <span aria-hidden className="mt-[0.72rem] h-px w-2.5 shrink-0 bg-ink-3" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
