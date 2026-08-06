/**
 * 사이트 접근 잠금 (공유 비밀번호).
 *
 * 회원 시스템이 아니다. "아는 사람만 들어온다"가 목적이므로
 * 계정·가입·비밀번호찾기·탈퇴가 없다. 관리자 로그인(JWT)은 이것과 별개로 그대로 유지된다.
 *
 * 쿠키에 비밀번호를 넣지 않는다. 비밀번호로 서명한 토큰을 넣고,
 * 미들웨어가 같은 방식으로 다시 계산해 비교한다. 쿠키를 훔쳐봐도 비밀번호는 나오지 않고,
 * 비밀번호를 바꾸면 기존 쿠키가 모두 무효가 된다.
 *
 * Edge 런타임에서 돌아야 하므로 Node crypto 대신 Web Crypto 를 쓴다.
 */

export const GATE_COOKIE = 'tb_gate';
export const GATE_MAX_AGE = 60 * 60 * 24 * 30; // 30일

const PAYLOAD = 'taxbriefing-gate-v1';

/** 비밀번호에서 쿠키에 담을 토큰을 만든다. */
export async function gateToken(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(PAYLOAD));
  return Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/** 타이밍 공격을 피하려면 길이와 무관하게 전체를 비교해야 한다. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
