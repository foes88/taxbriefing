import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

import { GATE_COOKIE, gateToken, safeEqual } from '@/lib/gate';

/**
 * 사이트 전체 접근 잠금.
 *
 * SITE_PASSWORD 가 설정되지 않으면 **막는 쪽으로** 실패한다.
 * 설정을 깜빡했을 때 사이트가 열려 버리는 것이, 잠깐 안 열리는 것보다 나쁘다.
 * 단 로컬 개발(NODE_ENV !== production)에서는 통과시켜 개발을 막지 않는다.
 */
const OPEN_PATHS = ['/gate', '/api/gate'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (OPEN_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  const password = process.env.SITE_PASSWORD;

  if (!password) {
    // 로컬에서는 잠그지 않는다.
    if (process.env.NODE_ENV !== 'production') return NextResponse.next();
    return redirectToGate(request, 'unset');
  }

  const cookie = request.cookies.get(GATE_COOKIE)?.value;
  if (cookie && safeEqual(cookie, await gateToken(password))) {
    return NextResponse.next();
  }

  return redirectToGate(request);
}

function redirectToGate(request: NextRequest, reason?: string) {
  const url = request.nextUrl.clone();
  url.pathname = '/gate';
  url.search = '';
  // 로그인 후 원래 보려던 곳으로 돌려보낸다.
  const from = request.nextUrl.pathname + request.nextUrl.search;
  if (from && from !== '/') url.searchParams.set('from', from);
  if (reason) url.searchParams.set('reason', reason);
  return NextResponse.redirect(url);
}

export const config = {
  // 정적 자산과 Next 내부 경로는 검사하지 않는다.
  matcher: ['/((?!_next/static|_next/image|favicon.ico|robots.txt|.*\\.(?:png|jpg|svg|ico|webp)$).*)'],
};
