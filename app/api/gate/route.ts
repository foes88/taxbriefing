import { NextResponse } from 'next/server';

import { GATE_COOKIE, GATE_MAX_AGE, gateToken } from '@/lib/gate';

/**
 * 비밀번호 확인 후 접근 쿠키를 발급한다.
 *
 * 무차별 대입을 늦추기 위해 실패 시 짧게 지연한다. 공유 비밀번호 하나뿐이라
 * 계정 잠금 같은 수단이 없기 때문이다.
 */
export async function POST(request: Request) {
  const expected = process.env.SITE_PASSWORD;
  if (!expected) {
    return NextResponse.json(
      { message: 'SITE_PASSWORD 환경변수가 설정되지 않았습니다.' },
      { status: 503 },
    );
  }

  let password = '';
  try {
    const body = (await request.json()) as { password?: unknown };
    password = typeof body.password === 'string' ? body.password : '';
  } catch {
    password = '';
  }

  if (password !== expected) {
    await new Promise((resolve) => setTimeout(resolve, 600));
    return NextResponse.json({ message: '비밀번호가 올바르지 않습니다.' }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: GATE_COOKIE,
    value: await gateToken(expected),
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: GATE_MAX_AGE,
  });
  return response;
}
