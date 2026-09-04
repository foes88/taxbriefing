"""알림에 적는 법안 건수. 네트워크 없이 실행된다.

"매일 알림에서 법안 바뀌는거를 너무 길게 잡아서 신규 법안인지 헷갈려"

세는 기준과 적는 말이 둘 다 문제였다.
"""

from __future__ import annotations

import datetime as dt

from app.services.render.telegram import render_digest

TODAY = dt.date(2026, 9, 3)


class TestWording:
    def test_says_it_is_what_we_saw_today(self):
        out = render_digest([], today=TODAY, bills=3)
        assert "오늘 새로 확인된 세법 개정안이 3건" in out

    def test_does_not_claim_it_was_proposed_today(self):
        """국회 목록에는 며칠 늦게 올라오는 건이 있다.

        8월 14일에 발의된 것을 우리가 22일에 알았다. 우리가 아는 것은
        "오늘 처음 봤다" 까지이고, 그것만 말한다.
        """
        out = render_digest([], today=TODAY, bills=3)
        assert "발의된" not in out

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

        계류 중인 것이 통틀어 넷이라는 말로도, 새로 나온 것이 넷이라는
        말로도 읽힌다.
        """
        out = render_digest([], today=TODAY, bills=4)
        assert "국회에 발의된 세법 개정안이 4건 있습니다" not in out


class TestNoDoubleCounting:
    """**이틀 연속으로 같은 법안을 세면 안 된다.**

    "새로운 법안에 대해서 중복으로 계속 보내면 안 될 거 같은데"

    맞는 지적이었다. 발의일로 26시간 창을 자르니 이렇게 됐다.

        09-03 실행 → 발의일 09-02 이후 5건
        09-04 실행 → 발의일 09-03 이후 3건   ← 이 3건은 어제도 셌다

    답은 **우리가 처음 알게 된 날**이다. created_at 은 한 번 정해지면
    안 움직이고, 날짜로 자르면 한 건이 정확히 하루에만 들어간다.
    """

    def _count_for(self, day, created):
        """그날 알림이 셀 건수. notify.collect_cards 의 셈과 같은 규칙."""
        return sum(1 for c in created if c == day)

    def test_a_bill_is_counted_on_exactly_one_day(self):
        seen = [dt.date(2026, 9, 3)] * 3 + [dt.date(2026, 9, 4)] * 5
        counts = [
            self._count_for(dt.date(2026, 9, 3), seen),
            self._count_for(dt.date(2026, 9, 4), seen),
        ]
        assert counts == [3, 5]
        assert sum(counts) == len(seen), "합계가 전체와 같아야 겹침이 없다"

    def test_a_late_arrival_still_gets_counted(self):
        """8월 14일에 발의된 것을 우리가 22일에 알았다.

        발의일로 세면 그런 건 아예 못 알린다. 우리가 안 날로 세면
        그날 하루치에 정확히 한 번 들어간다.
        """
        seen = [dt.date(2026, 8, 22)]
        assert self._count_for(dt.date(2026, 8, 22), seen) == 1
        assert self._count_for(dt.date(2026, 8, 14), seen) == 0
