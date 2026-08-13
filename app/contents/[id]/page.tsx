import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Block, DateCell, DateRow, FactGrid, InfoRow, SourceList } from '@/components/DetailParts';
import { Masthead } from '@/components/Masthead';
import { Caveat, DeadlineMark, RiskMark, StatusSeal } from '@/components/Seal';
import { TribunalArticle } from '@/components/TribunalArticle';
import { ApiRequestError, publicApi } from '@/lib/api';
import { daysUntil, effectiveLabel, formatDateTime } from '@/lib/format';
import type { PublicContentDetail, TribunalBody } from '@/lib/types';

export const dynamic = 'force-dynamic';

/**
 * 콘텐츠 상세 (U-03, §10.3 표준 블록).
 *
 * 폼이 아니라 **기록**으로 읽혀야 한다. 관보 한 건을 펼쳐 놓은 모양이다.
 * 배치는 사장님이 판단하는 순서를 따른다.
 *   상태 → 제목 → 한눈 표 → 할 일 → 대상 → 현재/변경
 *
 * 넓은 화면에서는 서지 정보(일자표·출처)를 오른쪽 열로 보낸다.
 * 본문은 읽기 좋은 폭을 유지하면서 화면은 비지 않게 하기 위해서다.
 *
 * **종류에 따라 본문 틀이 갈린다.** 법령과 심판례는 성격이 다르다 —
 * 하나로 처리하면 심판례에 시행일과 "할 일"이 붙는다. 둘 다 거짓이다.
 * 그 갈림은 여기서 한 번만 하고, 아래로는 각자의 틀을 그린다.
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
  const tribunal = readTribunal(body);

  return (
    <div className="min-h-screen">
      <Masthead active={tribunal ? 'tips' : 'policy'} />

      <main className="mx-auto max-w-page px-4 pb-20">
        <nav className="py-4">
          <Link
            href={tribunal ? '/tips' : '/'}
            className="text-[13px] font-semibold text-ink-3 transition-colors hover:text-ink"
          >
            ← {tribunal ? '실무 TIP' : '오늘의 브리핑'}
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
          {tribunal ? (
            <TribunalArticle content={content} tribunal={tribunal} />
          ) : (
            <PolicyArticle content={content} body={body} />
          )}

          {/* ── 서지 정보 (넓은 화면에서만 우측 열) ── */}
          <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
            {tribunal ? (
              <div className="hidden border border-rule bg-surface lg:block">
                <h2 className="border-b border-rule px-4 py-2.5">
                  <span className="label">사건 정보</span>
                </h2>
                <dl className="divide-y divide-rule">
                  <InfoRow label="청구번호" value={tribunal.case_no} />
                  <InfoRow label="세목" value={tribunal.tax_type} />
                  <InfoRow label="처분청" value={tribunal.disposition_agency} />
                  <DateRow label="의결일" value={content.promulgation_date} emphasis />
                </dl>
                {/*
                  관련 법령은 조문 나열이라 한 줄에 안 들어간다. 표에 억지로
                  넣지 않고 아래에 따로 흘린다.
                */}
                {tribunal.related_laws ? (
                  <div className="border-t border-rule px-4 py-3">
                    <p className="label">관련 법령</p>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
                      {tribunal.related_laws}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
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
            )}

            <SourceList sources={content.sources} />

            <p className="text-[12px] leading-relaxed text-ink-3">
              이 안내는 일반적인 제도 변경을 설명합니다. 개별 사업자의 적용 여부와 세액은
              사실관계에 따라 달라질 수 있으므로 세무전문가와 상담하시기 바랍니다.
            </p>

            <Link href={tribunal ? '/tips' : '/'} className="btn-quiet w-full">
              {tribunal ? '다른 사례 보기' : '다른 브리핑 보기'}
            </Link>
          </aside>
        </div>
      </main>
    </div>
  );
}

/**
 * 본문에서 심판례 구조를 꺼낸다. 없으면 null — 법령 틀로 그린다.
 *
 * `content_kind` 가 아니라 **본문 모양**을 본다. 종류는 TRIBUNAL 인데
 * 아직 예전 틀로 저장된 건이 남아 있을 수 있고, 그럴 때 심판례 화면을
 * 그리면 빈 껍데기가 나온다. 그릴 것이 실제로 있을 때만 그린다.
 */
function readTribunal(body: Record<string, unknown>): TribunalBody | null {
  const value = body.tribunal;
  if (!value || typeof value !== 'object') return null;
  const t = value as Partial<TribunalBody>;
  if (!Array.isArray(t.sections) || t.sections.length === 0) return null;
  return {
    tax_type: String(t.tax_type ?? ''),
    outcome: String(t.outcome ?? ''),
    case_no: String(t.case_no ?? ''),
    disposition_agency: String(t.disposition_agency ?? ''),
    related_laws: String(t.related_laws ?? ''),
    sections: t.sections.filter((s) => s && s.label && s.text),
  };
}

/** 법령·행정규칙 본문. 시행일과 정책 상태를 갖는 종류다. */
function PolicyArticle({
  content,
  body,
}: {
  content: PublicContentDetail;
  body: Record<string, unknown>;
}) {
  const list = (key: string): string[] => {
    const value = body[key];
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    if (typeof value === 'string' && value.trim()) return [value.trim()];
    return [];
  };

  const deadline = daysUntil(content.application_end);
  const actions = list('required_actions');
  const changes = list('changes');
  const targets = list('affected_users');
  const effective = effectiveLabel(content.effective_date);

  // 목록과 같은 규칙 — 요약이 제목을 통째로 품고 있으면 제목을 그대로 쓴다.
  const summary = content.one_line_summary?.trim();
  const strip = (s: string) => s.replace(/[「」·\s()]/g, '');
  const useSummary = !!summary && !strip(summary).includes(strip(content.title));
  const headline = useSummary ? summary! : content.title;
  const statute = useSummary ? content.title : null;

  return (
    <article className="min-w-0 border border-rule bg-surface">
      {/*
        **무엇이 바뀌는지를 제목으로 삼는다.**
        텔레그램 링크를 타고 들어온 사장님이 처음 보는 줄이
        "국세기본법 시행령 (일부개정)"이면 자기와 무슨 상관인지 알 수 없다.
        법령명은 출처지 제목이 아니다. 요약이 없을 때만 법령명이 제목이 된다 —
        없는 문장을 지어내지 않는다.
      */}
      <header className="border-b border-rule px-5 py-7 sm:px-8">
        <div className="flex flex-wrap items-center gap-2.5">
          <RiskMark risk={content.risk_level} />
          <StatusSeal status={content.legal_status} label={content.status_label} />
          {deadline !== null && deadline >= 0 && deadline <= 7 ? (
            <DeadlineMark days={deadline} />
          ) : null}
        </div>

        <h1 className="mt-3.5 max-w-reading text-display text-ink">{headline}</h1>

        {statute ? <p className="mt-3 text-[14px] font-medium text-ink-3">{statute}</p> : null}

        {content.status_caveat ? (
          <p className="mt-4 border-t border-rule pt-3.5">
            <Caveat text={content.status_caveat} />
          </p>
        ) : null}
      </header>

      {/*
        누가·언제·무엇이·할 일. 상세에 들어온 사람이 실제로 묻는 넷이다.
        예전에는 시행일만 제목 아래 따로 있고 나머지 셋은 본문에 흩어져
        있어서, 넷을 다 알려면 끝까지 읽어야 했다.
      */}
      <FactGrid
        cells={[
          { label: '누구에게', value: targets[0] ?? '사업자 일반' },
          { label: '언제부터', value: effective.text, tone: effective.tone === 'soon' ? 'soon' : 'plain' },
          { label: '무엇이', value: changes[0] ?? '원문 확인 필요' },
          {
            label: '할 일',
            value: actions.length > 0 ? `${actions.length}가지 — 아래 확인` : '별도 조치 없음',
          },
        ]}
      />

      {/* 좁은 화면에서는 일자표도 본문 안에 둔다. */}
      <div className="lg:hidden">
        <dl className="grid grid-cols-2 border-b border-rule">
          <DateCell label="발표일" value={content.announcement_date} />
          <DateCell label="공포일" value={content.promulgation_date} />
          <DateCell label="시행일" value={content.effective_date} emphasis />
          <DateCell label="신청 마감" value={content.application_end} />
        </dl>
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

        <Block title="적용 대상" items={targets} />
        <Block title="제외 대상" items={list('excluded_users')} muted />
        <Block title="현재 적용 기준" items={list('current_basis')} />
        <Block title="달라지는 점" items={changes} />
        <Block title="사업자에게 미치는 영향" items={list('business_impact')} />
        <Block title="전문가 확인이 필요한 항목" items={list('needs_expert')} muted />

        {actions.length === 0 && changes.length === 0 ? (
          <p className="text-[15px] leading-relaxed text-ink-2">
            상세 분석이 아직 작성되지 않았습니다. 아래 공식 원문을 확인해 주세요.
          </p>
        ) : null}
      </div>

      {/* 검수 상태는 AI 생성 여부보다 우선해 표시한다 (§10.4). */}
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-rule bg-surface-sunk px-5 py-4 sm:px-8">
        <span className="text-[13px] font-semibold text-state-effective">세무전문가 검수 완료</span>
        <span className="tabular text-[12px] text-ink-3">
          최종 확인 {formatDateTime(content.updated_at)}
        </span>
      </footer>
    </article>
  );
}
