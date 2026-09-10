"""중요도는 **지금 손봐야 하는 정도**다. 네트워크 없이 실행된다.

법안은 통과할지 모르고, 해석례·판례·심판례는 **남의 사건에 대한 판단**이다.
넷 다 사장님이 오늘 할 일이 없다. 제목에 "가산세" 가 있다고 [중요] 를 달면
「지금 안 하면 큰일 난다」 는 말을 거짓으로 하는 것이다.
"""

from __future__ import annotations

import pytest

from app.bulk_draft import KINDS_ALWAYS_LOW, _decide_risk
from app.domain.enums import ContentKind, RiskLevel

#: 원래대로면 [중요] 가 붙는 제목. 종류가 이겨야 한다.
ALARMING = "가산세 부과 및 과태료 처분의 당부"


class TestKindsAlwaysLow:
    @pytest.mark.parametrize(
        "kind",
        [
            ContentKind.BILL.value,
            ContentKind.INTERPRETATION.value,
            ContentKind.PRECEDENT.value,
            ContentKind.TRIBUNAL.value,
        ],
    )
    def test_alarming_title_stays_low(self, kind: str):
        assert _decide_risk(ALARMING, kind=kind) is RiskLevel.LOW

    def test_tribunal_is_included(self):
        """**빠져 있었다.**

        해석례·판례는 목록에 있는데 심판례만 없었다. 그래서 제목 낱말만
        보고 33건 중 30건에 [중요] 가 붙었다. 형제 셋 중 하나만 빠지는
        누락은 의결일 때도 똑같이 났다 — 낱개로 늘어놓으면 못 본다.
        """
        assert ContentKind.TRIBUNAL.value in KINDS_ALWAYS_LOW

    def test_policy_is_not(self):
        """확정된 법령은 실제로 지금 손볼 일이 생긴다. 제목을 봐야 한다."""
        assert ContentKind.POLICY.value not in KINDS_ALWAYS_LOW


class TestPreannounced:
    def test_preannounced_policy_is_low(self):
        """입법예고는 아직 법이 아니다. 종류는 법령이어도 낮다."""
        assert (
            _decide_risk(ALARMING, kind=ContentKind.POLICY.value, preannounced=True)
            is RiskLevel.LOW
        )
