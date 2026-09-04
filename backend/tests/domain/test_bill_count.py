"""알림에 적는 법안 건수. 네트워크 없이 실행된다.

"매일 알림에서 법안 바뀌는거를 너무 길게 잡아서 신규 법안인지 헷갈려"

세는 기준과 적는 말이 둘 다 문제였다.
"""

from __future__ import annotations

import datetime as dt

from app.services.render.telegram import render_digest

TODAY = dt.date(2026, 9, 3)


class TestWording:
    def test_one_day_window_says_yesterday(self):
        out = render_digest([], today=TODAY, bills=3, bill_days=1)
        assert "어제 새로 발의된 세법 개정안이 3건" in out

    def test_longer_window_says_how_many_days(self):
        """--hours 를 늘려 돌리면 「어제」 가 거짓이 된다.

        문구가 세는 창과 어긋나면 그 자체가 거짓말이다.
        """
        out = render_digest([], today=TODAY, bills=8, bill_days=3)
        assert "최근 3일 사이 새로 발의된 세법 개정안이 8건" in out
        assert "어제" not in out

    def test_says_it_is_not_law_yet(self):
        """카드로 안 보내는 이유가 이것이다. 건수만 알린다."""
        assert "아직 법이 아닙니다" in render_digest([], today=TODAY, bills=1)

    def test_no_bills_no_line(self):
        """0건이면 줄 자체를 안 쓴다. 「0건」 은 알림이 아니다."""
        out = render_digest([], today=TODAY, bills=0)
        assert "발의" not in out

    def test_the_old_ambiguous_wording_is_gone(self):
        """예전 문구는 두 가지로 읽혔다.

            국회에 발의된 세법 개정안이 4건 있습니다

        계류 중인 것이 통틀어 넷이라는 말로도, 어제 새로 나온 것이
        넷이라는 말로도 읽힌다.
        """
        out = render_digest([], today=TODAY, bills=4, bill_days=1)
        assert "국회에 발의된 세법 개정안이 4건 있습니다" not in out
