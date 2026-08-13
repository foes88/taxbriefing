import type { ComparisonBody, DiffSegment } from '@/lib/types';

/**
 * 조문 신구 대조.
 *
 * **실무자가 가장 먼저 묻는 것** — "이 조문이 정확히 어떻게 바뀌었나."
 *
 * 개정이유는 왜 바꿨는지를 말하고, 개정문은 "제3항 중 '30일'을 '60일'로
 * 한다" 처럼 지시문으로 말한다. 둘 다 조문 전문을 옆에 놓고 읽어야
 * 이해된다. 그래서 나란히 놓는다.
 *
 * 바뀐 부분은 법제처가 표시해 준 그대로다. 우리가 diff 를 돌리지 않았고
 * 모델에게 물어보지도 않았다 — 틀릴 여지가 없다.
 */

/**
 * 색만으로 구분하지 않는다 (NFR-013).
 *
 * 변경 전은 취소선, 변경 후는 굵게 + 바탕색이다. 화면을 흑백으로 봐도
 * 어느 쪽이 없어지고 어느 쪽이 들어오는지 알 수 있다.
 *
 * 빨강은 쓰지 않는다. 이 화면에서 빨강은 긴급 하나에만 쓰기로 했고,
 * 조문이 바뀌는 것은 긴급이 아니다.
 */
function Segments({ segments, side }: { segments: DiffSegment[]; side: 'old' | 'new' }) {
  return (
    <>
      {segments.map((segment, i) =>
        segment.changed ? (
          <mark
            key={i}
            className={
              side === 'old'
                ? 'bg-surface-sunk px-0.5 text-ink-3 line-through decoration-ink-3 decoration-1'
                : 'bg-accent-soft px-0.5 font-bold text-ink'
            }
          >
            {segment.text}
          </mark>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </>
  );
}

function Row({ row, index }: { row: ComparisonBody['rows'][number]; index: number }) {
  return (
    <li className="border-t border-rule first:border-t-0">
      <div className="grid gap-0 sm:grid-cols-2">
        <div className="border-b border-rule bg-surface-sunk px-5 py-4 sm:border-b-0 sm:border-r sm:px-6">
          <p className="label">
            변경 전 <span className="tabular ml-1 text-ink-3">#{index + 1}</span>
          </p>
          <p className="mt-2 whitespace-pre-wrap text-[14.5px] leading-relaxed text-ink-2">
            <Segments segments={row.old} side="old" />
          </p>
        </div>
        <div className="px-5 py-4 sm:px-6">
          <p className="label">변경 후</p>
          <p className="mt-2 whitespace-pre-wrap text-[14.5px] leading-relaxed text-ink">
            <Segments segments={row.new} side="new" />
          </p>
        </div>
      </div>
    </li>
  );
}

/** 접지 않고 바로 보여줄 조문 수. 나머지는 펼쳐서 본다. */
const OPEN_ROWS = 3;

export function Comparison({ comparison }: { comparison: ComparisonBody }) {
  const rows = comparison.rows;
  if (rows.length === 0) return null;

  const head = rows.slice(0, OPEN_ROWS);
  const rest = rows.slice(OPEN_ROWS);

  return (
    <section className="border-t border-rule">
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-5 pb-3 pt-7 sm:px-8">
        <h2 className="section-mark">조문 신구 대조</h2>
        <p className="text-[13px] text-ink-3">
          변경 조문 <span className="tabular font-semibold text-ink-2">{rows.length}개</span>
          {/*
            자른 것을 말없이 넘어가지 않는다. 40개만 보여주고 조용히 있으면
            "이게 전부" 로 읽힌다. 조세특례제한법 개정 한 건이 277개다.
          */}
          {comparison.dropped > 0 ? (
            <span className="ml-1.5">· 외 {comparison.dropped}개는 원문에서 확인</span>
          ) : null}
        </p>
      </header>

      <ul className="border-t border-rule">
        {head.map((row, i) => (
          <Row key={row.no} row={row} index={i} />
        ))}
      </ul>

      {rest.length > 0 ? (
        <details className="group border-t border-rule">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-[14px] font-bold text-accent hover:bg-surface-sunk sm:px-8 [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">나머지 {rest.length}개 조문 보기</span>
            <span className="hidden group-open:inline">접기</span>
            <span aria-hidden className="text-ink-3 transition-transform group-open:rotate-180">
              ▾
            </span>
          </summary>
          <ul className="border-t border-rule">
            {rest.map((row, i) => (
              <Row key={row.no} row={row} index={i + OPEN_ROWS} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/**
 * 본문에서 대조표를 꺼낸다. 없거나 모양이 다르면 null.
 *
 * 모양을 확인하고 꺼내는 이유 — 이 값은 나중에 붙인 것이라 예전에
 * 만들어진 콘텐츠에는 없다. 없는 걸 그리려다 빈 제목만 남기지 않는다.
 */
export function readComparison(body: Record<string, unknown>): ComparisonBody | null {
  const value = body.comparison;
  if (!value || typeof value !== 'object') return null;
  const c = value as Partial<ComparisonBody>;
  if (!Array.isArray(c.rows) || c.rows.length === 0) return null;

  const rows = c.rows.filter(
    (row) => row && Array.isArray(row.old) && Array.isArray(row.new) && (row.old.length || row.new.length),
  );
  if (rows.length === 0) return null;

  return {
    rows,
    dropped: typeof c.dropped === 'number' ? c.dropped : 0,
    law_name: String(c.law_name ?? ''),
    revision_type: String(c.revision_type ?? ''),
  };
}
