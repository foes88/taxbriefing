import Link from 'next/link';

/**
 * 제호(masthead).
 *
 * 인주색 규칙선을 아래에 한 줄 긋는다. 페이지에서 이 색이 쓰이는 곳은
 * 여기와 '긴급' 표시뿐이다. 강조를 한 곳에 몰아야 그 강조가 힘을 갖는다.
 */
export function Masthead({ compact = false }: { compact?: boolean }) {
  return (
    <header className="border-b border-rule bg-surface">
      <div className="mx-auto flex max-w-page items-center justify-between px-4 py-3.5">
        <Link href="/" className="flex items-baseline gap-2.5">
          <span className="text-[17px] font-extrabold tracking-[-0.02em] text-ink">
            TaxBriefing
          </span>
          {!compact ? (
            <span className="hidden text-[12px] font-medium text-ink-3 sm:inline">
              공식 원문으로 확인한 세무 브리핑
            </span>
          ) : null}
        </Link>

        <Link
          href="/admin"
          className="text-[12px] font-semibold text-ink-3 transition-colors hover:text-ink"
        >
          관리자
        </Link>
      </div>
      <div aria-hidden className="h-[2px] bg-seal" />
    </header>
  );
}
