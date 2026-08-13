/**
 * 출처 등급 표시.
 *
 * A·B 는 공식 원문(법령·관보·기관 발표), C·D 는 보도다.
 * 이 구분이 이 서비스의 약속이라 화면 어디서든 같은 모양으로 보여야 한다.
 */
const GRADE: Record<'A' | 'B' | 'C' | 'D', { label: string; tone: string }> = {
  A: { label: '공식 원문', tone: 'pill-good' },
  B: { label: '기관 발표', tone: 'pill-good' },
  C: { label: '언론 보도', tone: 'pill-warn' },
  D: { label: '참고', tone: 'pill-calm' },
};

export function AuthorityTag({ grade }: { grade: 'A' | 'B' | 'C' | 'D' }) {
  const spec = GRADE[grade] ?? GRADE.D;
  return <span className={`pill ${spec.tone}`}>{spec.label}</span>;
}
