import Link from 'next/link';

import { daysUntil } from '@/lib/format';
import type { PublicContentSummary } from '@/lib/types';

/**
 * 오늘 화면을 여는 사람이 처음 보는 것.
 *
 * **숫자 대시보드를 만들지 않는다.**
 * "수집 123 · 분석 87 · 법령 24" 같은 값은 만든 사람에게만 의미가 있다.
 * 세무사무소 직원이 알고 싶은 것은 "몇 건 들어왔나" 가 아니라
 * "내가 지금 봐야 하는 게 있나" 다.
 *
 * 그래서 세 개만 센다. 각각이 서로 다른 행동으로 이어진다.
 *   지금 확인   — 오늘 읽어야 할 것
 *   곧 시행     — 미리 준비할 것
 *   마감 임박   — 놓치면 못 돌리는 것
 *
 * 0 이면 숫자를 띄우지 않고 문장으로 말한다. "0" 이 세 개 늘어선 화면은
 * 아무 일도 없다는 사실조차 알려주지 못한다.
 */
export function TodayBrief({
  leadCount,
  upcomingCount,
  items,
}: {
  /** "먼저 볼 것" 에 실제로 올라간 건수. 목록과 숫자가 어긋나면 안 된다. */
  leadCount: number;
  upcomingCount: number;
  items: PublicContentSummary[];
}) {
  // 중요도가 HIGH 인 것을 전부 세니 28 이 나왔다. 오늘 볼 게 28 개면
  // 아무것도 아닌 것과 같다. 아래 목록에 실제로 올라간 것만 센다.
  const urgent = leadCount;

  const deadline = items.filter((i) => {
    const days = daysUntil(i.application_end);
    return days !== null && days >= 0 && days <= 14;
  }).length;

  if (urgent === 0 && upcomingCount === 0 && deadline === 0) {
    return (
      <p className="panel px-5 py-4 text-[15px] leading-relaxed text-ink-2">
        오늘 새로 확인할 중요한 변화는 없습니다. 아래 기록에서 지난 개정을 찾아보실 수 있습니다.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap gap-2.5">
      <Metric
        value={urgent}
        label="지금 확인"
        note="중요·긴급"
        href="?risk_level=CRITICAL&risk_level=HIGH"
        tone={urgent > 0 ? 'urgent' : 'quiet'}
      />
      <Metric value={upcomingCount} label="곧 시행" note="미리 준비" href="/upcoming" />
      {deadline > 0 ? (
        <Metric value={deadline} label="마감 임박" note="2주 안" href="?deadline=7" tone="urgent" />
      ) : null}
    </div>
  );
}

function Metric({
  value,
  label,
  note,
  href,
  tone = 'quiet',
}: {
  value: number;
  label: string;
  note: string;
  href: string;
  tone?: 'urgent' | 'quiet';
}) {
  return (
    <Link
      href={href}
      className="panel group flex min-w-[8.5rem] flex-1 items-baseline gap-3 px-4 py-3 transition-colors hover:bg-surface-sunk"
    >
      <span
        className={`tabular text-[26px] font-extrabold leading-none ${
          tone === 'urgent' && value > 0 ? 'text-seal' : 'text-ink'
        }`}
      >
        {value}
      </span>
      <span className="min-w-0">
        <span className="block text-[13.5px] font-bold text-ink group-hover:underline">
          {label}
        </span>
        <span className="block text-[12px] text-ink-3">{note}</span>
      </span>
    </Link>
  );
}

/**
 * 정책 진행 단계별 건수.
 *
 * 개편안의 Policy Radar 다. 다만 **있는 단계만 보여준다** —
 * 입법예고·국회심사는 아직 수집기가 없어서 0 이고, 0 을 늘어놓으면
 * 화면이 "준비 중" 이라고 말하는 셈이 된다.
 */
export function PolicyRadar({ items }: { items: PublicContentSummary[] }) {
  const stages = [
    { status: 'PREANNOUNCED', label: '입법예고' },
    { status: 'BILL_PROPOSED', label: '국회 발의' },
    { status: 'ASSEMBLY_PASSED', label: '국회 통과' },
    { status: 'PROMULGATED', label: '공포·시행 대기' },
    { status: 'EFFECTIVE', label: '시행 중' },
  ] as const;

  const counted = stages
    .map((s) => ({ ...s, count: items.filter((i) => i.legal_status === s.status).length }))
    .filter((s) => s.count > 0);

  if (counted.length < 2) return null;

  return (
    <section className="mt-8">
      <h2 className="section-mark pb-2.5">정책 진행 단계</h2>
      <ol className="panel flex flex-wrap divide-y divide-rule sm:divide-x sm:divide-y-0">
        {counted.map((stage) => (
          <li key={stage.status} className="flex-1 basis-[7rem] px-4 py-3">
            <Link
              href={`?legal_status=${stage.status}`}
              className="group block"
            >
              <span className="tabular block text-[20px] font-extrabold leading-none text-ink">
                {stage.count}
              </span>
              <span className="mt-1 block text-[12.5px] font-semibold text-ink-2 group-hover:underline">
                {stage.label}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
