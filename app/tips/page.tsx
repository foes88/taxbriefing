import { redirect } from 'next/navigation';

/**
 * 옛 주소. 「찾기」로 보낸다.
 *
 * 심판례를 따로 탭으로 두었더니, 상담 중에 답이 법령에 있는지 심판례에
 * 있는지 모른 채 찾는 사람이 종류부터 골라야 했다. 이제 한 곳에서 찾고
 * 종류로 좁힌다.
 *
 * 지운 게 아니라 옮긴 것이므로 옛 링크(텔레그램·북마크)는 살려 둔다.
 */
export default function TipsRedirect() {
  redirect('/search?kind=TRIBUNAL');
}
