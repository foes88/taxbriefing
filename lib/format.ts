/** 표시 시간대는 Asia/Seoul (§8.1). 저장은 UTC. */

const SEOUL = 'Asia/Seoul';

function toDate(value: string): Date | null {
  const date = new Date(value.length === 10 ? `${value}T00:00:00+09:00` : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "2026년 9월 1일" — 상세 화면처럼 오해가 없어야 하는 곳에 쓴다. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '확인 필요';
  const date = toDate(value);
  if (!date) return '확인 필요';
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: SEOUL,
  }).format(date);
}

/** "26.09.01" — 목록처럼 밀도가 필요한 곳에 쓴다. */
export function formatDateShort(value: string | null | undefined): string {
  if (!value) return '확인 필요';
  const date = toDate(value);
  if (!date) return '확인 필요';
  return new Intl.DateTimeFormat('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    timeZone: SEOUL,
  })
    .format(date)
    .replace(/\.$/, '');
}

/**
 * 일자 거터용 2행 표기 — "26.09" / "01".
 * 좁은 열에서도 연·월과 일이 각각 읽히게 한다.
 */
export function formatDateCompact(value: string | null | undefined): string {
  if (!value) return '미정';
  const date = toDate(value);
  if (!date) return '미정';
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: SEOUL,
  }).format(date);
  const [y, m, d] = parts.split('-');
  return `${y.slice(2)}.${m}.${d}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  const date = toDate(value);
  if (!date) return '-';
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: SEOUL,
  }).format(date);
}

/** 서울 기준 오늘 (YYYY-MM-DD). */
export function seoulToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SEOUL }).format(new Date());
}

/** 오늘 기준 남은 일수. 과거면 음수, 값이 없으면 null. */
export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  const target = toDate(value.slice(0, 10));
  if (!target) return null;
  const today = new Date(`${seoulToday()}T00:00:00+09:00`);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

export function todayLabel(): string {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
    timeZone: SEOUL,
  }).format(new Date());
}

/**
 * 목록을 시간대별로 묶는 라벨.
 * 신문처럼 "언제 것인가"가 보이면 훑는 속도가 빨라진다.
 */
export function recencyGroup(updatedAt: string): '오늘' | '이번 주' | '지난 소식' {
  const days = daysUntil(updatedAt);
  if (days === null) return '지난 소식';
  const ago = -days;
  if (ago <= 0) return '오늘';
  if (ago <= 7) return '이번 주';
  return '지난 소식';
}
