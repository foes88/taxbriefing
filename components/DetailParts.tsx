import { AuthorityTag } from '@/components/Authority';
import { formatDate } from '@/lib/format';
import type { PublicSource } from '@/lib/types';

/**
 * 상세 화면 조각들. 법령과 심판례가 함께 쓴다.
 *
 * 두 종류는 본문 구조가 다르지만 **서지 정보는 같다.** 언제 나온 것이고
 * 누가 낸 것이며 원문이 어디 있는지 — 이건 종류와 무관하게 신뢰의 근거다.
 */

/**
 * 한눈 표.
 *
 * 상세에 들어온 사람이 실제로 묻는 것은 넷이다.
 * 누구 얘기인가 · 언제부터인가 · 무엇이 달라지나 · 내가 뭘 해야 하나.
 *
 * 예전에는 이 넷을 알려면 본문을 끝까지 읽어야 했다. 시행일만 제목 아래
 * 따로 붙어 있었고 나머지는 아래 섹션에 흩어져 있었다.
 *
 * **값이 없는 칸은 그리지 않는다.** "원문 확인" 같은 칸이 세 개 늘어서면
 * 표가 아무것도 알려주지 않으면서 자리만 먹는다.
 */
export function FactGrid({
  cells,
}: {
  cells: ({ label: string; value: string | null; tone?: 'soon' | 'plain' } | null)[];
}) {
  const shown = cells.filter(
    (cell): cell is { label: string; value: string; tone?: 'soon' | 'plain' } =>
      Boolean(cell && cell.value),
  );
  if (shown.length === 0) return null;

  return (
    // 휴대폰에서도 2열이다. 1열이면 네 칸이 세로로 화면 하나를 먹는다.
    <dl className="grid grid-cols-2 gap-x-4 gap-y-4 rounded-field bg-surface-sunk px-4 py-4">
      {shown.map((cell) => (
        <div key={cell.label} className="min-w-0">
          <dt className="field-label">{cell.label}</dt>
          {/*
            세 줄에서 자른다. "무엇이" 칸에 개정문이 통째로 들어와 일곱
            줄이 된 적이 있는데, 그러면 한눈 표가 아니라 그냥 본문이다.
            전문은 바로 아래 "달라지는 점" 에 있다.
          */}
          <dd
            className={`mt-1.5 line-clamp-3 text-[15px] font-bold leading-snug ${
              cell.tone === 'soon' ? 'text-danger' : 'text-ink'
            }`}
          >
            {cell.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** 날짜 한 줄. */
export function DateRow({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string | null;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <dt className="text-meta font-semibold text-ink-3">{label}</dt>
      <dd
        className={`tabular text-[14px] ${
          value ? (emphasis ? 'font-bold text-ink' : 'font-semibold text-ink-2') : 'text-warn'
        }`}
      >
        {value ? formatDate(value) : '확인 필요'}
      </dd>
    </div>
  );
}

/** 글자로 된 서지 항목. 날짜가 아닌 것(청구번호·세목)에 쓴다. */
export function InfoRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <dt className="shrink-0 text-meta font-semibold text-ink-3">{label}</dt>
      <dd className="text-right text-[14px] font-semibold text-ink-2">{value}</dd>
    </div>
  );
}

/**
 * 공식 출처. 접지 않고 그대로 노출한다 (§10.4).
 *
 * 이게 신뢰의 근거다. 우리가 정리한 문장이 미덥지 않으면 원문으로 가면
 * 된다는 것을, 매번 보이게 둔다.
 */
export function SourceList({ sources }: { sources: PublicSource[] }) {
  return (
    <section className="card pad">
      <h2 className="section-title">공식 출처</h2>
      <ul className="mt-3 flex flex-col gap-3">
        {sources.map((source) => (
          <li key={source.url}>
            <div className="flex flex-wrap items-center gap-1.5">
              <AuthorityTag grade={source.authority} />
              <span className="text-meta font-semibold text-ink-2">{source.publisher}</span>
              {source.role === 'PRIMARY' ? (
                <span className="text-meta text-ink-3">주 근거</span>
              ) : null}
            </div>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 block text-[15px] font-bold leading-snug text-accent hover:underline"
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
  );
}

/** 항목 목록 구획. 값이 없으면 표제도 그리지 않는다. */
export function Block({
  title,
  items,
  muted,
}: {
  title: string;
  items: string[];
  muted?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <section className="mt-7 first:mt-0">
      <h2 className="section-title">{title}</h2>
      <ul className="mt-2.5 flex flex-col gap-2">
        {items.map((item, i) => (
          <li
            key={i}
            className={`flex gap-2.5 text-body ${muted ? 'text-ink-3' : 'text-ink-2'}`}
          >
            <span aria-hidden className="mt-[0.62rem] h-[3px] w-[3px] shrink-0 rounded-full bg-ink-3" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
