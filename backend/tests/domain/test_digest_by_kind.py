"""브리핑은 종류에 따라 말을 바꾼다. 네트워크·DB 없이 실행된다.

세무사무소 직원이 아침에 실제로 받는 메시지다. 여기서 틀린 말이
나가면 정정할 방법이 없다.
"""

from __future__ import annotations

import datetime as dt

from app.domain.enums import LegalStatus, RiskLevel
from app.services.render.telegram import BriefingCard, render_card, render_digest

TODAY = dt.date(2026, 8, 14)


def _bill() -> BriefingCard:
    return BriefingCard(
        title="소득세법 일부개정법률안 — 박수영의원 등 11인",
        legal_status=LegalStatus.BILL_PROPOSED,
        risk_level=RiskLevel.LOW,
        kind="BILL",
        proposed_at=dt.date(2026, 8, 10),
        key_points=("발의: 박수영의원 등 11인", "소관: 재정경제기획위원회"),
    )


def _policy() -> BriefingCard:
    return BriefingCard(
        title="국세기본법 (일부개정)",
        legal_status=LegalStatus.EFFECTIVE,
        risk_level=RiskLevel.HIGH,
        effective_date=dt.date(2026, 8, 11),
        key_points=("세무조사 연기 사유가 확대됩니다",),
        actions=("우리 상황이 해당하는지 점검하세요",),
    )


class TestBillCard:
    """법안은 아직 법이 아니다.

    예전에는 법령 틀로 나가서 이렇게 찍혔다.

        상태: 상태 확인 필요 (확정 아님)
        시행일: 확인 필요

    발의된 법안에 시행일이 있을 리 없고, 상태를 모르는 것도 아니다.
    """

    def test_no_effective_date_line(self):
        text = render_card(_bill())
        assert "시행일" not in text

    def test_shows_the_proposal_date_instead(self):
        assert "발의일: 2026년 8월 10일" in render_card(_bill())

    def test_actions_are_labelled_as_reference(self):
        """법안에 "사업자가 할 일" 을 붙이면 안 해도 될 일을 하게 만든다."""
        card = BriefingCard(
            title="법안",
            legal_status=LegalStatus.BILL_PROPOSED,
            risk_level=RiskLevel.LOW,
            kind="BILL",
            actions=("통과되면 어떻게 되는지 미리 봐 두세요",),
        )
        text = render_card(card)
        assert "참고" in text
        assert "사업자가 할 일" not in text

    def test_policy_keeps_the_effective_date(self):
        """법령까지 같이 바뀌면 안 된다."""
        text = render_card(_policy())
        assert "시행일: 2026년 8월 11일" in text
        assert "사업자가 할 일" in text


class TestDigestTail:
    """법안은 카드가 아니라 건수 한 줄로 나간다.

    법안 40건을 수집한 날 아침 브리핑 여섯 자리가 전부 법안으로 찼다.
    "누가 무엇을 발의했다" 가 여섯 줄이고, 정작 시행 중인 개정은
    한 건도 안 보였다.
    """

    def test_bill_count_is_told(self):
        text = render_digest([_policy()], today=TODAY, bills=40)
        assert "40건" in text
        assert "아직 법이 아닙니다" in text

    def test_no_line_when_there_are_no_bills(self):
        assert "발의된" not in render_digest([_policy()], today=TODAY, bills=0)

    def test_overflow_is_still_told(self):
        """자리가 없어 뺀 것은 몇 건인지 밝힌다. 조용히 자르면
        오늘 나온 게 이게 전부라고 믿는다."""
        text = render_digest([_policy()], today=TODAY, overflow=99, bills=40)
        assert "99건이 더 있습니다" in text
        assert "40건" in text

    def test_empty_day_says_so(self):
        assert "새로 확인된 공식 발표가 없습니다" in render_digest([], today=TODAY)
