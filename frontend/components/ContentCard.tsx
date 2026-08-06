import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark, StatusSeal } from './Seal';
import { daysUntil, formatDateCompact } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목 (U-02).
 *
 * 관보 색인의 구조를 그대로 가져왔다 — 왼쪽에 일자, 오른쪽에 내용.
 * 그래서 카드가 아니라 **기록(record)** 이고, 그림자 대신 헤어라인으로 나눈다.
 *
 * 읽는 순서: 시행일 → 중요도·상태 → 제목 → 요약
 * 사장님이 가장 먼저 묻는 것이 "언제부터인가"이기 때문이다.
 */
export function ContentRecord({ item }: { item: PublicContentSummary }) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group -mx-3 block rounded-soft px-3 py-4 transition-colors hover:bg-surface"
    >
      <div className="flex gap-3.5 sm:gap-5">
        {/* 일자 거터 — 관보 색인의 좌측 열 */}
        <div className="w-[3.25rem] shrink-0 pt-[3px] sm:w-[4.5rem]">
          <div className="gutter-date">시행</div>
          <div
            className={`mt-1 text-[13px] font-bold tabular leading-tight ${
              item.effective_date ? 'text-ink' : 'text-state-pending'
            }`}
          >
            {item.effective_date ? formatDateCompact(item.effective_date) : '미정'}
          </div>
        </div>

        {/* 세로 규칙선 */}
        <div aria-hidden className="w-px shrink-0 bg-rule" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <RiskMark risk={item.risk_level} />
            <StatusSeal status={item.legal_status} label={item.status_label} />
            {showDeadline ? <DeadlineMark days={deadline} /> : null}
            {item.corrected ? (
              <span className="seal border-seal text-seal">정정</span>
            ) : null}
          </div>

          <h3 className="mt-2 text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
            {item.title}
          </h3>

          {item.one_line_summary ? (
            <p className="mt-1.5 line-clamp-2 text-[15px] leading-relaxed text-ink-2">
              {item.one_line_summary}
            </p>
          ) : null}

          {item.status_caveat ? (
            <div className="mt-2">
              <Caveat text={item.status_caveat} />
            </div>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
