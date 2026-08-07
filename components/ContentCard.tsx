import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark, StatusSeal } from './Seal';
import { daysUntil, effectiveLabel } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목은 두 가지 모양으로 나온다.
 *
 * **LeadItem** — "먼저 볼 것". 긴급·중요만 여기 온다.
 * **RecordRow** — "전체 기록". 일자 묶음 안에 들어가는 한 줄.
 *
 * 판단을 크기로 말한다. 예전에는 108건이 전부 같은 크기로 늘어서 있었고,
 * 모두가 같은 무게면 무게가 없는 것과 같다. "세무전문가가 검수했다"가
 * 이 서비스의 약속인데 그 판단이 화면에 드러나지 않았다.
 *
 * **제목과 요약을 뒤집었다.**
 * 목록을 훑을 때 첫 줄이 "국세기본법 시행령 (일부개정)"이면 사장님은
 * 자기와 무슨 상관인지 알 수 없다. 정작 답은 그 아래 요약에 있었다.
 * 법령명은 **출처**지 제목이 아니다. 그래서 무엇이 바뀌는지를 앞에 놓고,
 * 법령명은 아래 메타 줄로 내렸다.
 *
 * 요약이 없으면 법령명이 제목이 된다 — 없는 문장을 지어내지 않는다.
 */

/**
 * 훑을 때 읽을 한 줄과, 그 아래 출처 표기.
 *
 * 요약이 **제목을 통째로 품고 있으면 제목을 그대로 쓴다.**
 * AI 요약이 아직 없는 건에는 자동 생성 문구가 들어 있는데,
 * 그게 이렇게 생겼다.
 *
 *   「소득세법 (일부개정)」이(가) 일부개정되어 2026년 7월 1일부터 시행됩니다.
 *
 * 이걸 제목 자리에 올리면 법령명보다 길기만 하고 새로 알려주는 게 없다.
 * 시행일은 바로 아래 줄이 이미 말하고 있어 같은 말을 두 번 하게 된다.
 */
function headlineOf(item: PublicContentSummary): { headline: string; statute: string | null } {
  const summary = item.one_line_summary?.trim();
  if (!summary) return { headline: item.title, statute: null };

  const strip = (s: string) => s.replace(/[「」·\s()]/g, '');
  if (strip(summary).includes(strip(item.title))) {
    return { headline: item.title, statute: null };
  }
  return { headline: summary, statute: item.title };
}

export function LeadItem({ item, index }: { item: PublicContentSummary; index: number }) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;
  const { headline, statute } = headlineOf(item);
  const effective = effectiveLabel(item.effective_date);

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group flex gap-4 px-4 py-5 transition-colors hover:bg-surface-sunk sm:gap-5 sm:px-5"
    >
      {/*
        번호는 장식이 아니라 **우선순위**다. 중요도 → 마감 임박 → 최신 순으로
        서버가 정렬한 결과 그대로이므로, 1번이 오늘 가장 먼저 볼 건이다.
      */}
      <span
        aria-hidden
        className="tabular w-7 shrink-0 pt-1 text-[17px] font-extrabold leading-none text-accent"
      >
        {index + 1}
      </span>

      <div className="min-w-0 flex-1">
        <h3 className="max-w-reading text-headline text-ink decoration-1 underline-offset-4 group-hover:underline">
          <RiskMark risk={item.risk_level} />
          {item.corrected ? (
            <span className="tag mr-2 border border-seal align-[2px] text-seal">정정</span>
          ) : null}
          {headline}
        </h3>

        <p className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-3">
          <span
            className={`font-bold ${
              effective.tone === 'soon' ? 'text-seal' : 'text-ink-2'
            }`}
          >
            {effective.text}
          </span>
          <StatusSeal status={item.legal_status} label={item.status_label} />
          {showDeadline ? <DeadlineMark days={deadline} /> : null}
        </p>

        <p className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] text-ink-3">
          {statute ? <span className="font-medium">{statute}</span> : null}
          {statute && item.industry_labels.length > 0 ? <Dot /> : null}
          {item.industry_labels.join(' · ')}
        </p>

        {item.status_caveat ? (
          <div className="mt-2">
            <Caveat text={item.status_caveat} />
          </div>
        ) : null}
      </div>
    </Link>
  );
}

/** 일자 묶음 안의 한 줄. 두 줄로 끝난다 — 제목 한 줄, 메타 한 줄. */
export function RecordRow({ item }: { item: PublicContentSummary }) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;
  const { headline, statute } = headlineOf(item);
  const effective = effectiveLabel(item.effective_date);

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group block px-4 py-3.5 transition-colors hover:bg-surface-sunk sm:px-5"
    >
      <h3 className="max-w-reading text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
        <RiskMark risk={item.risk_level} />
        {item.corrected ? (
          <span className="tag mr-2 border border-seal align-[2px] text-seal">정정</span>
        ) : null}
        {headline}
      </h3>

      <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[13px] text-ink-3">
        <span
          className={`font-semibold ${effective.tone === 'soon' ? 'text-seal' : 'text-ink-2'}`}
        >
          {effective.text}
        </span>
        <Dot />
        <StatusSeal status={item.legal_status} label={item.status_label} />
        {statute ? (
          <>
            <Dot />
            <span>{statute}</span>
          </>
        ) : null}
        {item.industry_labels.map((name) => (
          <span key={name} className="flex items-center gap-2.5">
            <Dot />
            {name}
          </span>
        ))}
        {showDeadline ? <DeadlineMark days={deadline} /> : null}
      </p>
    </Link>
  );
}

function Dot() {
  return (
    <span aria-hidden className="text-rule-strong">
      ·
    </span>
  );
}
