"""본문 없는 종류의 날짜를 콘텐츠로 옮긴다. 네트워크 없이 실행된다.

해석은 회신일, 판례는 선고일, 심판례는 의결일. 셋 다 날짜가 하나뿐이고
공포일도 시행일도 없다. 안 옮기면 화면이 주황색 「확인 필요」 를 띄우는데,
**확인할 것이 없는 게 아니라 우리가 안 옮긴 것이다.**
"""

from __future__ import annotations

from app.bulk_draft import KINDS_WITH_DECIDED_DATE
from app.domain.enums import ContentKind


class TestKindsWithDecidedDate:
    def test_tribunal_is_included(self):
        """**빠져 있었다.**

        전에 이 문제를 고칠 때 이미 쌓인 데이터는 손으로 메웠는데 경로를
        안 고쳤다. 그래서 그 뒤로 새로 들어온 심판례마다 의결일이 비었다.
        메타에는 50건 다 있었는데 콘텐츠에는 3건이 없었고, 그 3건이 전부
        가장 최근에 들어온 것이었다.

        데이터만 메우고 코드를 안 고치면 같은 구멍으로 계속 샌다.
        """
        assert ContentKind.TRIBUNAL.value in KINDS_WITH_DECIDED_DATE

    def test_interpretation_and_precedent_too(self):
        assert ContentKind.INTERPRETATION.value in KINDS_WITH_DECIDED_DATE
        assert ContentKind.PRECEDENT.value in KINDS_WITH_DECIDED_DATE

    def test_policy_is_not(self):
        """법령은 공포일과 시행일이 따로 있다. 하나로 뭉치면 안 된다."""
        assert ContentKind.POLICY.value not in KINDS_WITH_DECIDED_DATE

    def test_bill_is_not(self):
        """법안의 날짜는 발의일이고, 그건 따로 옮긴다."""
        assert ContentKind.BILL.value not in KINDS_WITH_DECIDED_DATE
