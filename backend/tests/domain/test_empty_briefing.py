"""보낼 것이 없는 날. 네트워크 없이 실행된다.

조용한 것과 고장 난 것은 받는 쪽에서 똑같아 보인다. 실제로 배치가
사흘 멈춘 것을 아무도 모르다가 "오늘은 텔레그램 안 왔는데" 로 알았다.
"""

from __future__ import annotations

import datetime as dt

from app.services.render.telegram import render_digest, render_owner_digest


class TestNothingToSend:
    def test_digest_still_says_something(self):
        out = render_digest([], today=dt.date(2026, 8, 20))
        assert "오늘은 새로 확인된 공식 발표가 없습니다" in out

    def test_digest_carries_the_date(self):
        """날짜가 있어야 어제 것이 다시 온 건지 오늘 것인지 안다."""
        assert "2026.08.20" in render_digest([], today=dt.date(2026, 8, 20))

    def test_owner_digest_stays_silent(self):
        """전달할 것이 없는데 전달용 메시지를 만들 이유가 없다."""
        assert render_owner_digest([], today=dt.date(2026, 8, 20)) == ""
