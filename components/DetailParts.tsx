import { AuthorityTag } from '@/components/Seal';
import { formatDate } from '@/lib/format';
import type { PublicSource } from '@/lib/types';

/**
 * 상세 화면 조각들. 법령과 심판례가 함께 쓴다.
 *
 * 두 종류는 본문 구조가 다르지만 **서지 정보는 같다.** 언제 나온 것이고
 * 누가 낸 것이며 원문이 어디 있는지 — 이건 종류와 무관하게 신뢰의 근거다.
 */

/**
 * 한눈 표 (2×2).
 *
 * 상세 화면에 들어온 사람이 실제로 묻는 것은 넷이다.
 * 누구 얘기인가 · 언제부터인가 · 무엇이 달라지나 · 내가 뭘 해야 하나.
 *
 * 예전에는 이 넷을 알려면 본문을 끝까지 읽어야 했다. 시행일만 제목 아래
 * 따로 붙어 있었고 나머지는 아래 섹션에 흩어져 있었다.
 *
 * 그래서 시행일 줄을 없애고 이 표로 합쳤다. **같은 사실을 두 번 적지
 * 않는다** — 표가 헤더의 반복이 되면 화면만 길어진다.
 */
export function FactGrid({
  cells,
}: {
  cells: ({ label: string; value: string | null; tone?: 'soon' | 'plain' } | null)[];
}) {
  /*
    값이 없는 칸은 그리지 않는다.
    "처분청 · 원문 확인" 같은 칸이 세 개 늘어서면 표가 아무것도 알려주지
    않으면서 화면만 먹는다. 모르는 것은 조용히 빼고, 원문 링크는 옆 칸에
    이미 있다.
  */
  const shown = cells.filter(
    (cell): cell is { label: string; value: string; tone?: 'soon' | 'plain' } =>
      Boolean(cell && cell.value),
  );
  if (shown.length === 0) return null;

  return (
    /*
      휴대폰에서도 2열이다. 1열로 두면 네 칸이 세로로 384px 을 먹어서
      본문이 화면 밖으로 밀린다. 값이 길면 칸 안에서 줄바꿈될 뿐이고,
      그게 네 번 스크롤하는 것보다 낫다.
    */
    <dl className="grid grid-cols-2 border-b border-rule">
      {shown.map((cell, i) => (
        <div
          key={cell.label}
          className={`border-rule px-4 py-3.5 sm:px-8 sm:py-4 ${
            i % 2 === 0 ? 'border-r' : ''
          } ${i < shown.length - 2 ? 'border-b' : ''}`}
        >
          <dt className="label">{cell.label}</dt>
          <dd
            className={`mt-1.5 text-[15px] font-semibold leading-snug sm:mt-2 sm:text-[15.5px] ${
              cell.tone === 'soon' ? 'text-seal' : 'text-ink'
            }`}
          >
            {cell.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** 좁은 화면용 일자표. 각 날짜는 별도 필드다 (FR-VER-003). */
export function DateCell({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string | null;
  emphasis?: boolean;
}) {
  return (
    <div
      // 칸 수가 둘일 수도 셋일 수도 있다. "앞의 두 칸" 이 아니라
      // "마지막 줄이 아닌 칸" 에 아래 선을 긋는다.
      className={`border-rule px-4 py-3.5 [&:not(:nth-last-child(-n+2))]:border-b [&:nth-child(odd)]:border-r ${
        emphasis ? 'bg-surface-sunk' : ''
      }`}
    >
      <dt className="label">{label}</dt>
      <dd
        className={`tabular mt-1.5 text-[14px] ${
          value
            ? emphasis
              ? 'font-bold text-ink'
              : 'font-semibold text-ink-2'
            : 'font-semibold text-state-pending'
        }`}
      >
        {value ? formatDate(value) : '확인 필요'}
      </dd>
    </div>
  );
}

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
    <div
      className={`flex items-baseline justify-between gap-3 px-4 py-2.5 ${
        emphasis ? 'bg-surface-sunk' : ''
      }`}
    >
      <dt className="text-[12.5px] font-semibold text-ink-3">{label}</dt>
      <dd
        className={`tabular text-[13.5px] ${
          value
            ? emphasis
              ? 'font-bold text-ink'
              : 'font-semibold text-ink-2'
            : 'font-semibold text-state-pending'
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
    <div className="flex items-baseline justify-between gap-3 px-4 py-2.5">
      <dt className="shrink-0 text-[12.5px] font-semibold text-ink-3">{label}</dt>
      <dd className="text-right text-[13.5px] font-semibold text-ink-2">{value}</dd>
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
    <section className="border border-rule bg-surface">
      <h2 className="border-b border-rule px-4 py-2.5">
        <span className="label">공식 출처</span>
      </h2>
      <ul className="divide-y divide-rule">
        {sources.map((source) => (
          <li key={source.url} className="px-4 py-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <AuthorityTag grade={source.authority} />
              <span className="text-[12px] font-semibold text-ink-2">{source.publisher}</span>
              {source.role === 'PRIMARY' ? (
                <span className="text-[11px] font-semibold text-ink-3">주 근거</span>
              ) : null}
            </div>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 block text-[14px] font-semibold leading-snug text-ink underline decoration-rule-strong decoration-1 underline-offset-4 transition-colors hover:decoration-ink"
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
    <section className="prose-block">
      <h2 className="label">{title}</h2>
      <ul className="mt-2.5 flex flex-col gap-2">
        {items.map((item, i) => (
          <li
            key={i}
            className={`flex gap-2.5 text-[16px] leading-relaxed ${muted ? 'text-ink-2' : 'text-ink'}`}
          >
            <span aria-hidden className="mt-[0.72rem] h-px w-2.5 shrink-0 bg-ink-3" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
