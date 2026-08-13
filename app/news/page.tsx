import { redirect } from 'next/navigation';

/**
 * 옛 주소. 「찾기」로 보낸다.
 *
 * 뉴스는 이제 탭이 아니라 두 자리에 있다 — 오늘 화면의 "확인 전 소식"
 * 구획과, 찾기의 종류 칩. 확인 전이라는 표시는 그대로 따라간다.
 */
export default function NewsRedirect() {
  redirect('/search?kind=NEWS');
}
