import Link from 'next/link';

import { Caveat, DeadlineMark, RiskMark } from './Seal';
import { daysUntil, formatDateCompact } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 목록 항목 (U-02).
 *
 * 관보 색인의 구조 — 왼쪽에 일자, 오른쪽에 내용. 카드가 아니라 **기록(record)** 이라
 * 그림자 대신 헤어라인으로 나눈다.
 *
 * **제목이 맨 위에 온다.** 예전에는 중요도·상태 도장을 제목 위에 한 줄 깔았는데,
 * 목록을 훑을 때 눈이 매번 배지를 지나 제목을 찾아야 했다. 사람은 제목으로 훑는다.
 * 그래서 도장은 제목 아래 한 줄로 모으고, 긴급·중요만 제목과 같은 줄에 둔다 —
 * 신문이 [속보]를 헤드라인 안에 넣는 것과 같은 이유다.
 *
 * 글자 크기는 세 단계뿐이다. 제목 / 요약 / 메타. 예전에는 11px·11.5px·12px·14px 가
 * 한 항목 안에 섞여 있었고, 크기가 많으면 위계가 아니라 소음이 된다.
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

  const meta = [item.status_label, ...item.industry_labels];

  return (
    <Link
      href={`/contents/${item.id}`}
      className="group -mx-3 block rounded-soft px-3 py-4 transition-colors hover:bg-surface-sunk"
    >
      <div className="flex gap-3.5 sm:gap-5">
        {/* 일자 거터 — 관보 색인의 좌측 열 */}
        <div className="w-[3.25rem] shrink-0 pt-[3px] sm:w-[3.75rem]">
          <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-ink-3">시행</div>
          <div
            className={`tabular mt-0.5 text-[13px] font-bold leading-tight ${
              item.effective_date ? 'text-ink' : 'text-state-pending'
            }`}
          >
            {item.effective_date ? formatDateCompact(item.effective_date) : '미정'}
          </div>
          {showPromulgated && item.promulgation_date ? (
            <div className="tabular mt-1.5 text-[12px] leading-tight text-ink-3">
              공포
              <br />
              {formatDateCompact(item.promulgation_date)}
            </div>
          ) : null}
        </div>

        <div aria-hidden className="w-px shrink-0 bg-rule" />

        <div className="min-w-0 flex-1">
          <h3 className="text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
            {item.risk_level === 'CRITICAL' || item.risk_level === 'HIGH' ? (
              <RiskMark risk={item.risk_level} />
            ) : null}
            {item.corrected ? <span className="seal mr-1.5 border-seal text-seal">정정</span> : null}
            {item.title}
          </h3>

          {summary && !redundant ? (
            // 폭을 묶는다. 넓은 화면에서 요약이 화면을 가로지르면 한 줄에
            // 백 자가 넘고, 줄 끝에서 다음 줄 첫 글자를 못 찾는다.
            <p className="mt-1.5 line-clamp-2 max-w-reading text-[15px] leading-relaxed text-ink-2">
              {summary}
            </p>
          ) : null}

          {/*
            메타는 **한 줄**이다. 상태와 업종이 서로 다른 줄에 있으면 항목 하나가
            네 줄이 되고, 열 개만 늘어놔도 화면이 글자로 가득 찬다.
          */}
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-3">
            {meta.map((text, index) => (
              <span key={text} className="flex items-center gap-2">
                {index > 0 ? <span aria-hidden className="text-rule-strong">·</span> : null}
                {text}
              </span>
            ))}
            {showDeadline ? (
              <span className="ml-0.5">
                <DeadlineMark days={deadline} />
              </span>
            ) : null}
          </p>

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
