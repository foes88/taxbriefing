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

/**
 * 시행일을 사람이 쓰는 말로.
 *
 * "시행 26.07.01" 은 정확하지만, 사장님이 가장 먼저 묻는 것은
 * "그래서 언제부터냐"이지 날짜 문자열이 아니다. 이미 지난 것과 앞으로 올 것을
 * 같은 모양으로 적으면 매번 오늘 날짜와 머리로 비교해야 한다.
 *
 * 날짜가 없으면 **지어내지 않는다** (§10.4).
 */
export function effectiveLabel(value: string | null): {
  text: string;
  tone: 'past' | 'soon' | 'future' | 'unknown';
} {
  if (!value) return { text: '시행일 미정', tone: 'unknown' };

  const days = daysUntil(value);
  if (days === null) return { text: '시행일 미정', tone: 'unknown' };

  const date = formatDate(value);
  if (days < 0) return { text: `${date}부터 시행 중`, tone: 'past' };
  if (days === 0) return { text: `오늘(${date})부터 시행`, tone: 'soon' };
  if (days <= 30) return { text: `${days}일 뒤 시행 · ${date}`, tone: 'soon' };
  return { text: `${date} 시행 예정`, tone: 'future' };
}

/** "2026년 7월 1일 (화)" — 일자 묶음의 표제. */
export function formatDateHeading(value: string | null): string {
  if (!value) return '공포일 미상';
  const date = toDate(value);
  if (!date) return '공포일 미상';
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
    timeZone: SEOUL,
  }).format(date);
}

/**
 * 일자별로 묶는다.
 *
 * 예전에는 116개 행마다 왼쪽에 날짜 거터를 반복해 그렸다. 같은 날 공포된
 * 개정이 여러 건이면 같은 숫자가 연달아 나오고, 그 열 전체가 폭만 차지한 채
 * 아무것도 말하지 않는다. 관보는 날짜가 **표제**이고 그 아래에 항목이 딸린다.
 *
 * 날짜를 모르는 건은 맨 뒤에 따로 묶는다. 없는 날짜를 오늘로 치거나
 * 맨 앞에 두면 "최신"으로 읽힌다.
 */
export function groupByDate<T>(
  items: T[],
  dateOf: (item: T) => string | null,
): { date: string | null; heading: string; items: T[] }[] {
  const buckets = new Map<string, T[]>();
  const undated: T[] = [];

  for (const item of items) {
    const raw = dateOf(item);
    if (!raw) {
      undated.push(item);
      continue;
    }
    const key = raw.slice(0, 10);
    buckets.set(key, [...(buckets.get(key) ?? []), item]);
  }

  const groups: { date: string | null; heading: string; items: T[] }[] = Array.from(
    buckets.entries(),
  )
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, list]) => ({ date, heading: formatDateHeading(date), items: list }));

  if (undated.length > 0) {
    groups.push({ date: null, heading: '공포일 미상', items: undated });
  }
  return groups;
}
