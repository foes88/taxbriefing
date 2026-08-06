import type { LegalStatus, RiskLevel } from '@/lib/types';

/**
 * 상태 표시 (§10.4).
 *
 * 관보는 확정 사실을 **도장**으로 남긴다. 그래서 둥근 알약 대신 각진 테두리를 쓴다.
 * 채워진 도장 = 확정된 사실(공포·시행), 빈 도장 = 아직 확정 아님(예고·발의).
 * 색을 못 보는 사람도 테두리와 채움만으로 구분할 수 있어야 한다 (§NFR-013).
 *
 * 라벨 문구는 **서버가 내려준 값을 그대로 쓴다.** 프론트에서 다시 만들면
 * 웹·텔레그램·이메일의 표현이 갈라지고, "입법예고를 시행 중으로 표시"하는 사고가
 * 채널마다 따로 난다 (AT-04).
 */

type Tone = 'effective' | 'confirmed' | 'pending' | 'halted' | 'unknown';

const STATUS_TONE: Record<LegalStatus, Tone> = {
  EFFECTIVE: 'effective',
  PROMULGATED: 'confirmed',
  ASSEMBLY_PASSED: 'confirmed',
  GOV_ANNOUNCED: 'pending',
  PREANNOUNCED: 'pending',
  BILL_PROPOSED: 'pending',
  DISCUSSION: 'unknown',
  SUSPENDED: 'halted',
  ABOLISHED: 'halted',
  UNKNOWN: 'unknown',
};

/** 확정된 사실만 도장을 채운다. */
const FILLED: Record<Tone, boolean> = {
  effective: true,
  confirmed: true,
  halted: true,
  pending: false,
  unknown: false,
};

const TONE_CLASS: Record<Tone, { filled: string; hollow: string }> = {
  effective: {
    filled: 'bg-state-effective border-state-effective text-white',
    hollow: 'border-state-effective text-state-effective',
  },
  confirmed: {
    filled: 'bg-state-confirmed border-state-confirmed text-white',
    hollow: 'border-state-confirmed text-state-confirmed',
  },
  pending: {
    filled: 'bg-state-pending border-state-pending text-white',
    hollow: 'border-state-pending text-state-pending',
  },
  halted: {
    filled: 'bg-state-halted border-state-halted text-white',
    hollow: 'border-state-halted text-state-halted',
  },
  unknown: {
    filled: 'bg-state-unknown border-state-unknown text-white',
    hollow: 'border-state-unknown text-state-unknown',
  },
};

export function StatusSeal({ status, label }: { status: LegalStatus; label: string }) {
  const tone = STATUS_TONE[status];
  const style = FILLED[tone] ? TONE_CLASS[tone].filled : TONE_CLASS[tone].hollow;
  return <span className={`seal ${style}`}>{label}</span>;
}

/** 확정되지 않은 정책에 반드시 따라붙는 경고 (§10.4). */
export function Caveat({ text }: { text: string }) {
  return (
    <span className="inline-flex items-baseline gap-1 text-[12px] font-semibold text-state-pending">
      <span aria-hidden className="translate-y-[1px] text-[10px]">
        ▲
      </span>
      {text}
    </span>
  );
}

const RISK_LABEL: Record<RiskLevel, string> = {
  CRITICAL: '긴급',
  HIGH: '중요',
  MEDIUM: '안내',
  LOW: '참고',
};

/**
 * 중요도. 목록에서 가장 먼저 읽혀야 하므로 색이 아니라 **굵기와 여백**으로 구분한다.
 * 긴급만 인주색을 쓴다 — 페이지 전체에서 이 색이 나오는 곳은 여기와 제호선뿐이다.
 */
export function RiskMark({ risk }: { risk: RiskLevel }) {
  if (risk === 'CRITICAL') {
    return <span className="seal border-seal bg-seal text-white">{RISK_LABEL.CRITICAL}</span>;
  }
  if (risk === 'HIGH') {
    return <span className="seal border-ink bg-ink text-surface">{RISK_LABEL.HIGH}</span>;
  }
  return (
    <span className="text-[11px] font-semibold tracking-tight text-ink-3">{RISK_LABEL[risk]}</span>
  );
}

/** 출처 등급 (§3.1). A/B 만 공식이고, 그 사실이 이 서비스의 신뢰 근거다. */
export function AuthorityTag({ grade }: { grade: 'A' | 'B' | 'C' | 'D' }) {
  const official = grade === 'A' || grade === 'B';
  return (
    <span
      className={`seal ${
        official ? 'border-ink text-ink' : 'border-rule-strong text-ink-3'
      }`}
      title={official ? '공식 원문 — 확정 판단의 근거' : '참고 자료 — 단독 근거로 쓰지 않음'}
    >
      {grade}등급 {official ? '공식' : '참고'}
    </span>
  );
}

/** 마감 임박. D-7 이내만 띄운다 (§11.2). */
export function DeadlineMark({ days }: { days: number }) {
  return (
    <span className={`seal border-seal ${days <= 3 ? 'bg-seal text-white' : 'text-seal'}`}>
      {days === 0 ? '오늘 마감' : `마감 D-${days}`}
    </span>
  );
}
