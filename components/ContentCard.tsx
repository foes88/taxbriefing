import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark, StatusSeal } from './Seal';
import { daysUntil, formatDateCompact } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목 (U-02).
 *
 * 관보 색인의 구조 — 왼쪽에 일자, 오른쪽에 내용. 카드가 아니라 **기록(record)** 이라
 * 그림자 대신 헤어라인으로 나눈다.
 *
 * 일자 거터는 **시행일**이다. 사장님이 가장 먼저 묻는 게 "언제부터인가"이기 때문이다.
 * 다만 목록의 월 묶음은 **공포월** 기준이라 두 날짜가 다를 수 있다.
 * 그래서 공포일을 메타 줄에 함께 적는다 — 안 적으면 "5월 목록인데 왜 7월?"이 된다.
 */
export function ContentRecord({
  item,
  showPromulgated = true,
}: {
  item: PublicContentSummary;
  showPromulgated?: boolean;
}) {
  const deadline = daysUntil(item.application_end);
  const showDeadline = deadline !== null && deadline >= 0 && deadline <= 7;

  // 요약이 제목을 그대로 되풀이하면 읽을 게 없다.
  const summary = item.one_line_summary?.trim();
  const redundant =
    !!summary && summary.replace(/[「」·\s()]/g, '').includes(item.title.replace(/[「」·\s()]/g, ''));

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group -mx-3 block rounded-soft px-3 py-3 transition-colors hover:bg-surface-sunk"
    >
      <div className="flex gap-3 sm:gap-4">
        {/* 일자 거터 — 관보 색인의 좌측 열 */}
        <div className="w-[3.5rem] shrink-0 pt-[2px] sm:w-[4rem]">
          <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-ink-3">시행</div>
          <div
            className={`tabular mt-0.5 text-[13px] font-bold leading-tight ${
              item.effective_date ? 'text-ink' : 'text-state-pending'
            }`}
          >
            {item.effective_date ? formatDateCompact(item.effective_date) : '미정'}
          </div>
          {showPromulgated && item.promulgation_date ? (
            <div className="tabular mt-1 text-[10.5px] leading-tight text-ink-3">
              공포 {formatDateCompact(item.promulgation_date)}
            </div>
          ) : null}
        </div>

        <div aria-hidden className="w-px shrink-0 bg-rule" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <RiskMark risk={item.risk_level} />
            <StatusSeal status={item.legal_status} label={item.status_label} />
            {showDeadline ? <DeadlineMark days={deadline} /> : null}
            {item.corrected ? <span className="seal border-seal text-seal">정정</span> : null}
          </div>

          <h3 className="mt-1.5 text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
            {item.title}
          </h3>

          {summary && !redundant ? (
            <p className="mt-1 line-clamp-2 text-[14px] leading-relaxed text-ink-2">{summary}</p>
          ) : null}

          {/*
            업종은 상태 도장과 같은 줄에 두지 않는다. 도장은 "확정됐는가"를,
            업종은 "누구 얘기인가"를 말한다. 성격이 다른 표시를 붙여 놓으면
            둘 다 안 읽힌다.
          */}
          {item.industry_labels.length > 0 ? (
            <p className="mt-1.5 flex flex-wrap gap-x-1.5 gap-y-1 text-[11.5px] text-ink-3">
              {item.industry_labels.map((name) => (
                <span key={name} className="border-l border-rule-strong pl-1.5">
                  {name}
                </span>
              ))}
            </p>
          ) : null}

          {item.status_caveat ? (
            <div className="mt-1.5">
              <Caveat text={item.status_caveat} />
            </div>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
