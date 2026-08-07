import type { LegalStatus, RiskLevel } from '@/lib/types';

/**
 * 상태·중요도 표시 (§10.4).
 *
 * 예전에는 전부 10.5px 빈 테두리 도장이었다. 관보의 인장을 흉내 낸 것인데,
 * 그 크기에서는 테두리와 글자가 뭉쳐 읽히지 않았고, "채운 도장 = 확정"이라는
 * 구분도 눈에 들어오지 않았다. 흉내가 목적이 되면 읽히지 않는다.
 *
 * 지금은 **색점 + 13px 글자**다. 점은 작아도 보이고 글자는 제 크기를 갖는다.
 * 확정 전은 속이 빈 점이라 색을 못 보는 사람도 구분할 수 있다 (§NFR-013).
 *
 * 라벨 문구는 **서버가 내려준 값을 그대로 쓴다.** 프론트에서 다시 만들면
 * 웹·텔레그램·이메일의 표현이 갈라지고, "입법예고를 시행 중으로 표시"하는
 * 사고가 채널마다 따로 난다 (AT-04).
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

/** 확정된 사실만 점을 채운다. */
const FILLED: Record<Tone, boolean> = {
  effective: true,
  confirmed: true,
  halted: true,
  pending: false,
  unknown: false,
};

const TONE_TEXT: Record<Tone, string> = {
  effective: 'text-state-effective',
  confirmed: 'text-state-confirmed',
  pending: 'text-state-pending',
  halted: 'text-state-halted',
  unknown: 'text-state-unknown',
};

export function StatusSeal({ status, label }: { status: LegalStatus; label: string }) {
  const tone = STATUS_TONE[status];
  return (
    <span className={`status ${FILLED[tone] ? '' : 'status-hollow'} ${TONE_TEXT[tone]}`}>
      {label}
    </span>
  );
}

/** 확정되지 않은 정책에 반드시 따라붙는 경고 (§10.4). */
export function Caveat({ text }: { text: string }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 text-[13px] font-semibold text-state-pending">
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
 * 중요도.
 *
 * **제목과 같은 줄에 들어간다.** 신문이 [속보]를 헤드라인 안에 넣는 것과 같다 —
 * 별도 줄에 두면 제목이 아래로 밀리고, 목록을 훑는 눈이 매번 표시를 지나
 * 제목을 찾아야 한다.
 *
 * 빨강은 긴급 하나뿐이다. 페이지 전체에서 이 색이 나오는 곳이 여기밖에 없어야
 * 신호가 된다. 안내·참고는 표시하지 않는다 — 대부분이 여기 해당해서 정보가
 * 없고, 매 줄에 같은 글자가 붙으면 그만큼 제목이 좁아진다.
 */
export function RiskMark({ risk }: { risk: RiskLevel }) {
  if (risk === 'CRITICAL') {
    return <span className="tag mr-2 bg-seal align-[2px] text-white">{RISK_LABEL.CRITICAL}</span>;
  }
  if (risk === 'HIGH') {
    return (
      <span className="tag mr-2 bg-accent-soft align-[2px] text-accent">{RISK_LABEL.HIGH}</span>
    );
  }
  return null;
}

/** 출처 등급 (§3.1). A/B 만 공식이고, 그 사실이 이 서비스의 신뢰 근거다. */
export function AuthorityTag({ grade }: { grade: 'A' | 'B' | 'C' | 'D' }) {
  const official = grade === 'A' || grade === 'B';
  return (
    <span
      className={`tag border ${
        official ? 'border-accent text-accent' : 'border-rule-strong text-ink-3'
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
    <span className={`tag ${days <= 3 ? 'bg-seal text-white' : 'border border-seal text-seal'}`}>
      {days === 0 ? '오늘 마감' : `마감 D-${days}`}
    </span>
  );
}
