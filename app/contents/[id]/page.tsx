import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Comparison, readComparison } from '@/components/Comparison';
import { Block, DateRow, FactGrid, InfoRow, SourceList } from '@/components/DetailParts';
import { Masthead } from '@/components/Masthead';
import { ShareCard } from '@/components/ShareCard';
import { TribunalArticle } from '@/components/TribunalArticle';
import { ApiRequestError, publicApi } from '@/lib/api';
import { daysUntil, effectiveLabel, formatDateTime, stripRevisionSuffix } from '@/lib/format';
import type { PublicContentDetail, TribunalBody } from '@/lib/types';

/*
  **텔레그램 링크가 여는 화면이다.** 아침에 브리핑을 받고 누르는 그
  한 번이 이 서비스의 첫인상이라, 여기가 제일 빨라야 한다.

  force-dynamic 이면 방문마다 Vercel → Render → Neon 을 왕복한다.
  그런데 내용은 하루 한 번 배치가 돌 때만 바뀐다. 5분 캐시로 두면
  같은 링크를 여러 사람이 눌러도 첫 사람만 왕복한다.

  정정본이 5분 늦게 보일 수 있다. 그건 감수한다 — 정정은 드물고,
  매번 왕복하는 대가가 훨씬 크다.
*/
export const revalidate = 300;

/**
 * 콘텐츠 상세 (U-03, §10.3 표준 블록).
 *
 * 배치는 사장님이 판단하는 순서를 따른다.
 *   급한 정도 → 무엇이 바뀌나 → 한눈 표 → 할 일 → 대상 → 조문 대조
 *
 * **종류에 따라 본문 틀이 갈린다.** 법령과 심판례는 성격이 다르다 —
 * 하나로 처리하면 심판례에 시행일과 "할 일" 이 붙는다. 둘 다 거짓이다.
 * 그 갈림은 여기서 한 번만 하고, 아래로는 각자의 틀을 그린다.
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
    <div className="min-h-screen pb-20">
      <Masthead />

      <main className="mx-auto max-w-page px-4">
        <nav className="py-3">
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-meta font-bold text-ink-3 transition-colors hover:text-ink"
          >
            ← 오늘
          </Link>
        </nav>

        {content.corrected ? (
          <div className="card mb-3 border-l-4 border-danger px-4 py-3.5">
            <p className="text-[14.5px] font-bold text-danger">정정</p>
            <p className="mt-1 text-body text-ink-2">
              이전에 안내드린 내용에 수정이 있었습니다. 아래 최신 내용을 확인해 주세요.
            </p>
          </div>
        ) : null}

        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:gap-5">
          <div className="min-w-0 flex-1">
            {tribunal ? (
              <TribunalArticle content={content} tribunal={tribunal} />
            ) : (
              <PolicyArticle content={content} body={body} />
            )}
          </div>

          <aside className="flex w-full flex-col gap-3 lg:sticky lg:top-24 lg:w-[19rem] lg:shrink-0">
            {/*
              옆칸의 맨 위. 넓은 화면에서는 본문과 나란히 붙어 있고,
              좁은 화면에서는 본문을 다 읽은 뒤에 나온다.

              좁은 화면에서 위로 올리지 않았다. 읽고 나서 보내는 순서가
              맞다 — 무엇을 보내는지 모른 채 복사부터 하면, 사무소를 떠난
              뒤에는 고칠 방법이 없다.
            */}
            <ShareCard text={content.share_text ?? ''} />

            <section className="card pad">
              <h2 className="section-title">{tribunal ? '사건 정보' : '주요 일자'}</h2>
              <dl className="mt-2 divide-y divide-line">
                {tribunal ? (
                  <>
                    <InfoRow label="청구번호" value={tribunal.case_no} />
                    <InfoRow label="세목" value={tribunal.tax_type} />
                    <InfoRow label="처분청" value={tribunal.disposition_agency} />
                    <DateRow label="의결일" value={content.promulgation_date} emphasis />
                  </>
                ) : (
                  <>
                    <DateRow label="발표일" value={content.announcement_date} />
                    <DateRow label="공포일" value={content.promulgation_date} />
                    <DateRow label="시행일" value={content.effective_date} emphasis />
                    {content.application_end ? (
                      <DateRow label="신청 마감" value={content.application_end} />
                    ) : null}
                  </>
                )}
              </dl>

              {tribunal?.related_laws ? (
                <div className="mt-3 border-t border-line pt-3">
                  <p className="field-label">관련 법령</p>
                  <p className="mt-1.5 text-meta leading-relaxed text-ink-2">
                    {tribunal.related_laws}
                  </p>
                </div>
              ) : null}
            </section>

            <SourceList sources={content.sources} />

            <p className="px-1 text-meta leading-relaxed text-ink-3">
              이 안내는 일반적인 제도 변경을 설명합니다. 개별 사업자의 적용 여부와 세액은
              사실관계에 따라 달라질 수 있으므로 세무전문가와 상담하시기 바랍니다.
            </p>
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

  const comparison = readComparison(body);
  const deadline = daysUntil(content.application_end);
  const actions = list('required_actions');
  const changes = list('changes');
  const targets = list('affected_users');
  const effective = effectiveLabel(content.effective_date);

  // 목록과 같은 규칙 — 요약이 제목을 통째로 품고 있으면 제목을 그대로 쓴다.
  // 개정 표시는 뗀다. 오른쪽 일자표가 공포일·시행일을 이미 말한다.
  const name = stripRevisionSuffix(content.title);
  const summary = content.one_line_summary?.trim();
  const strip = (s: string) => s.replace(/[「」·\s()]/g, '');
  const useSummary = !!summary && !strip(summary).includes(strip(content.title));
  const headline = useSummary ? summary! : name;
  const statute = useSummary ? name : null;

  return (
    <article className="flex flex-col gap-3">
      <div className="card pad">
        <div className="flex flex-wrap items-center gap-1.5">
          {content.risk_level === 'CRITICAL' ? (
            <span className="pill pill-danger">긴급</span>
          ) : content.risk_level === 'HIGH' ? (
            <span className="pill pill-accent">중요</span>
          ) : null}
          {content.status_label ? (
            <span className="pill pill-calm">{content.status_label}</span>
          ) : null}
          {deadline !== null && deadline >= 0 && deadline <= 7 ? (
            <span className="pill pill-danger">마감 D-{deadline}</span>
          ) : null}
        </div>

        {/*
          **무엇이 바뀌는지를 제목으로 삼는다.**
          텔레그램 링크를 타고 들어온 사장님이 처음 보는 줄이 "국세기본법
          시행령 (일부개정)" 이면 자기와 무슨 상관인지 알 수 없다.
          법령명은 출처지 제목이 아니다.
        */}
        <h1 className="mt-3 max-w-reading text-display text-ink">{headline}</h1>
        {statute ? <p className="mt-2 text-meta font-semibold text-ink-3">{statute}</p> : null}

        {content.status_caveat ? (
          <p className="mt-3 text-[14px] font-bold text-warn">{content.status_caveat}</p>
        ) : null}

        {/* 누구에게·언제부터·무엇이·할 일. 상세에 들어온 사람이 묻는 넷. */}
        <div className="mt-4">
          <FactGrid
            cells={[
              { label: '누구에게', value: targets[0] ?? '사업자 일반' },
              {
                label: '언제부터',
                value: effective.text,
                tone: effective.tone === 'soon' ? 'soon' : 'plain',
              },
              { label: '무엇이', value: changes[0] ?? null },
              {
                label: '할 일',
                value: actions.length > 0 ? `${actions.length}가지` : '별도 조치 없음',
              },
            ]}
          />
        </div>
      </div>

      {/*
        번호를 붙이는 이유: 이건 실제로 순서가 있는 절차다.
        순서가 없는 목록에는 번호를 쓰지 않는다.
      */}
      {actions.length > 0 ? (
        <section className="card pad">
          <h2 className="section-title">지금 해야 할 일</h2>
          <ol className="mt-3 flex flex-col gap-3">
            {actions.map((item, i) => (
              <li key={i} className="flex gap-3">
                <span className="tabular mt-[3px] flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-weak text-[12px] font-extrabold text-accent-ink">
                  {i + 1}
                </span>
                <span className="text-[15.5px] leading-relaxed text-ink">{item}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {targets.length > 0 ||
      changes.length > 0 ||
      list('excluded_users').length > 0 ||
      list('current_basis').length > 0 ||
      list('business_impact').length > 0 ||
      list('needs_expert').length > 0 ? (
        <section className="card pad max-w-reading">
          <Block title="달라지는 점" items={changes} />
          <Block title="적용 대상" items={targets} />
          <Block title="제외 대상" items={list('excluded_users')} muted />
          <Block title="현재 적용 기준" items={list('current_basis')} />
          <Block title="사업자에게 미치는 영향" items={list('business_impact')} />
          <Block title="전문가 확인이 필요한 항목" items={list('needs_expert')} muted />
        </section>
      ) : null}

      {/* 조문 대조는 구/신 두 칸을 나란히 놓아야 읽힌다. 폭을 다 쓴다. */}
      {comparison ? <Comparison comparison={comparison} /> : null}

      {/*
        대조표가 붙어 있으면 "아직 작성되지 않았다" 가 아니다. 조문이
        어떻게 바뀌는지가 바로 위에 있는데 없다고 하면 그냥 나간다.
      */}
      {actions.length === 0 && changes.length === 0 && !comparison ? (
        <div className="card pad">
          <p className="text-body text-ink-2">
            상세 분석이 아직 작성되지 않았습니다. 옆의 공식 원문을 확인해 주세요.
          </p>
        </div>
      ) : null}

      <p className="flex flex-wrap items-center justify-between gap-2 px-2 text-meta">
        <span className="font-bold text-good">세무전문가 검수 완료</span>
        <span className="tabular text-ink-3">최종 확인 {formatDateTime(content.updated_at)}</span>
      </p>
    </article>
  );
}
