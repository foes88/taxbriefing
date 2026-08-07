import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark, StatusSeal } from './Seal';
import { daysUntil, formatDateShort } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목은 두 가지 모양으로 나온다.
 *
 * **LeadItem** — "먼저 볼 것". 긴급·중요만 여기 온다.
 * **RecordRow** — "전체 기록". 일자 묶음 안에 들어가는 한 줄.
 *
 * 왜 나눴나. 예전에는 116건이 전부 같은 크기로 늘어서 있었다. 모두가 같은
 * 무게면 무게가 없는 것과 같고, 사장님은 어디부터 봐야 할지 알 수 없다.
 * "세무전문가가 검수했다"가 이 서비스의 약속인데 그 판단이 화면에 드러나지
 * 않았다. 판단을 크기로 말한다.
 *
 * 날짜는 RecordRow 에 반복하지 않는다. 일자 묶음의 표제가 이미 말하고 있다.
 */

function summaryOf(item: PublicContentSummary): string | null {
  const text = item.one_line_summary?.trim();
  if (!text) return null;
  // 요약이 제목을 그대로 되풀이하면 읽을 게 없다.
  const strip = (s: string) => s.replace(/[「」·\s()]/g, '');
  return strip(text).includes(strip(item.title)) ? null : text;
}

export function LeadItem({ item, index }: { item: PublicContentSummary; index: number }) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;
  const summary = summaryOf(item);

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
        <h3 className="text-headline text-ink decoration-1 underline-offset-4 group-hover:underline">
          <RiskMark risk={item.risk_level} />
          {item.corrected ? (
            <span className="tag mr-2 border border-seal align-[2px] text-seal">정정</span>
          ) : null}
          {item.title}
        </h3>

        {summary ? (
          <p className="mt-2 max-w-reading text-[15.5px] leading-relaxed text-ink-2">{summary}</p>
        ) : null}

        <p className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-3">
          <span className="tabular font-bold text-ink-2">
            시행 {item.effective_date ? formatDateShort(item.effective_date) : '미정'}
          </span>
          <StatusSeal status={item.legal_status} label={item.status_label} />
          {item.industry_labels.map((name) => (
            <span key={name}>{name}</span>
          ))}
          {showDeadline ? <DeadlineMark days={deadline} /> : null}
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

/** 일자 묶음 안의 한 줄. 밀도가 목적이라 요약은 한 줄로 자른다. */
export function RecordRow({ item }: { item: PublicContentSummary }) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;
  const summary = summaryOf(item);

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group block px-4 py-3.5 transition-colors hover:bg-surface-sunk sm:px-5"
    >
      <h3 className="text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
        <RiskMark risk={item.risk_level} />
        {item.corrected ? (
          <span className="tag mr-2 border border-seal align-[2px] text-seal">정정</span>
        ) : null}
        {item.title}
      </h3>

      {summary ? (
        <p className="mt-1.5 line-clamp-1 max-w-reading text-[14.5px] leading-relaxed text-ink-2">
          {summary}
        </p>
      ) : null}

      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-3">
        <span className="tabular font-semibold text-ink-2">
          시행 {item.effective_date ? formatDateShort(item.effective_date) : '미정'}
        </span>
        <StatusSeal status={item.legal_status} label={item.status_label} />
        {item.industry_labels.map((name) => (
          <span key={name}>{name}</span>
        ))}
        {showDeadline ? <DeadlineMark days={deadline} /> : null}
      </p>
    </Link>
  );
}
