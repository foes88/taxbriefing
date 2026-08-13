"""상태 경고 문구. 네트워크·DB 없이 실행된다.

경고는 아껴 써야 신호가 된다. 남발되면 정작 진짜 경고가 안 읽힌다.
"""

from __future__ import annotations

import datetime as dt

from app.domain.enums import LegalStatus
from app.services.render.telegram import caveat_for

FUTURE = dt.date(2027, 1, 1)


class TestPromulgated:
    def test_no_caveat_when_effective_date_is_known(self):
        """화면에 이렇게 나왔었다.

            2027년 1월 1일 시행 예정
            ▲ 시행일 확인

        날짜를 보여주면서 그 날짜를 확인하라고 하는 셈이다.
        """
        assert caveat_for(LegalStatus.PROMULGATED, FUTURE) is None

    def test_caveat_when_effective_date_is_missing(self):
        """공포는 됐는데 언제부터인지 모르면 그건 알려야 한다."""
        assert caveat_for(LegalStatus.PROMULGATED, None) == "시행일 확인"


class TestUnconfirmedStatuses:
    """입법예고·발의는 **시행일을 알아도** 확정이 아니다. 경고를 유지한다."""

    def test_preannounced_keeps_caveat_even_with_date(self):
        assert caveat_for(LegalStatus.PREANNOUNCED, FUTURE) == "시행 확정 아님 · 최종안 변경 가능"

    def test_bill_proposed_keeps_caveat_even_with_date(self):
        assert caveat_for(LegalStatus.BILL_PROPOSED, FUTURE) == "시행 확정 아님"

    def test_gov_announced_keeps_caveat_even_with_date(self):
        assert caveat_for(LegalStatus.GOV_ANNOUNCED, FUTURE) == "시행 확정 아님"


class TestEffective:
    def test_effective_has_no_caveat(self):
        """이미 시행 중인 것에 경고를 붙일 이유가 없다."""
        assert caveat_for(LegalStatus.EFFECTIVE, dt.date(2026, 1, 1)) is None
        assert caveat_for(LegalStatus.EFFECTIVE, None) is None
