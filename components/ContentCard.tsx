import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark } from './Seal';
import { daysUntil, formatDateShort } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목은 두 가지 모양으로 나온다.
 *
 * **LeadItem** — "먼저 볼 것". 긴급·중요·마감 임박만 여기 온다.
 * **RecordRow** — "전체 기록". 일자 묶음 안에 들어가는 한 줄.
 *
 * 왜 나눴나. 예전에는 116건이 전부 같은 크기로 늘어서 있었다. 모두가 같은
 * 무게면 무게가 없는 것과 같고, 사장님은 어디부터 봐야 할지 알 수 없다.
 * "세무전문가가 검수했다"는 것이 이 서비스의 약속인데 그 판단이 화면에
 * 드러나지 않았다. 판단을 크기로 말한다.
 *
 * 날짜는 RecordRow 에 없다. 일자 묶음의 표제가 이미 말하고 있어서,
 * 행마다 반복하면 같은 숫자가 연달아 나올 뿐이다.
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
      className="group flex gap-4 py-4 transition-colors hover:bg-surface-sunk sm:gap-5"
    >
      {/*
        번호는 장식이 아니라 **우선순위**다. 중요도 → 마감 임박 → 최신 순으로
        서버가 정렬한 결과 그대로이므로, 1번이 오늘 가장 먼저 볼 건이다.
      */}
      <span
        aria-hidden
        className="tabular w-6 shrink-0 pt-0.5 text-[15px] font-extrabold leading-none text-seal"
      >
        {index + 1}
      </span>

      <div className="min-w-0 flex-1">
        <h3 className="text-headline text-ink decoration-1 underline-offset-4 group-hover:underline">
          <RiskMark risk={item.risk_level} />
          {item.corrected ? <span className="seal mr-1.5 border-seal text-seal">정정</span> : null}
          {item.title}
        </h3>

        {summary ? (
          <p className="mt-1.5 max-w-reading text-[15px] leading-relaxed text-ink-2">{summary}</p>
        ) : null}

        <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px] text-ink-3">
          <span className="tabular font-semibold text-ink-2">
            시행 {item.effective_date ? formatDateShort(item.effective_date) : '미정'}
          </span>
          <Dot />
          <span>{item.status_label}</span>
          {item.industry_labels.map((name) => (
            <span key={name} className="flex items-center gap-2.5">
              <Dot />
              {name}
            </span>
          ))}
          {showDeadline ? <DeadlineMark days={deadline} /> : null}
        </p>

        {item.status_caveat ? (
          <div className="mt-1.5">
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
      className="group -mx-3 block rounded-soft px-3 py-2.5 transition-colors hover:bg-surface-sunk"
    >
      <h3 className="text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
        <RiskMark risk={item.risk_level} />
        {item.corrected ? <span className="seal mr-1.5 border-seal text-seal">정정</span> : null}
        {item.title}
      </h3>

      {summary ? (
        <p className="mt-1 line-clamp-1 max-w-reading text-[14px] leading-relaxed text-ink-2">
          {summary}
        </p>
      ) : null}

      <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px] text-ink-3">
        <span className="tabular">
          시행 {item.effective_date ? formatDateShort(item.effective_date) : '미정'}
        </span>
        <Dot />
        <span>{item.status_label}</span>
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
