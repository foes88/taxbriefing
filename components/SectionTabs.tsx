import Link from 'next/link';

/**
 * 정책 / 뉴스 전환.
 *
 * 두 탭은 **성격이 다른 정보**다. 정책은 공식 원문으로 확인하고 세무전문가가
 * 검수한 내용이고, 뉴스는 확인 전 언론 보도다. 그래서 활성 표시 색을 다르게 둔다 —
 * 정책은 먹색, 뉴스는 미확정을 뜻하는 황토색. 같은 색으로 칠하면 두 탭이
 * 같은 무게로 읽히고, 그게 이 서비스에서 가장 위험한 오해다.
 */
export function SectionTabs({ active }: { active: 'policy' | 'news' }) {
  return (
    <nav className="border-b border-rule-strong" aria-label="구분">
      <div className="mx-auto flex max-w-page gap-6 px-4">
        <Tab href="/" label="정책·법령" note="검수 완료" current={active === 'policy'} />
        <Tab
          href="/news"
          label="뉴스"
          note="확인 전"
          current={active === 'news'}
          unverified
        />
      </div>
    </nav>
  );
}

function Tab({
  href,
  label,
  note,
  current,
  unverified = false,
}: {
  href: string;
  label: string;
  note: string;
  current: boolean;
  unverified?: boolean;
}) {
  const accent = unverified ? 'border-state-pending' : 'border-ink';
  return (
    <Link
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`-mb-px flex items-baseline gap-2 border-b-2 pb-2.5 pt-3 transition-colors ${
        current ? accent : 'border-transparent hover:border-rule-strong'
      }`}
    >
      <span
        className={`text-[14.5px] font-bold tracking-tight ${
          current ? 'text-ink' : 'text-ink-3'
        }`}
      >
        {label}
      </span>
      <span
        className={`text-[11px] font-semibold ${
          current && unverified ? 'text-state-pending' : 'text-ink-3'
        }`}
      >
        {note}
      </span>
    </Link>
  );
}
