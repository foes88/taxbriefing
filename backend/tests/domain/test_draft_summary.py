"""임시 요약 문구. AI 요약 전까지 화면에 나가는 문장이다.

**틀린 문장을 내보내지 않는 것**이 이 테스트의 목적이다.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import ClassVar

from app.bulk_draft import _summary


def raw(title: str) -> SimpleNamespace:
    return SimpleNamespace(title=title)


class TestLawSummary:
    def test_says_when_it_takes_effect(self):
        text = _summary(
            raw("소득세법 (일부개정)"),
            {"revision_type": "일부개정"},
            dt.date(2027, 1, 1),
        )
        assert "2027년 1월 1일부터 시행됩니다" in text

    def test_missing_date_is_not_invented(self):
        """시행일이 없으면 지어내지 않는다 (§10.4)."""
        text = _summary(raw("소득세법 (일부개정)"), {}, None)
        assert "원문 확인이 필요합니다" in text


class TestTribunalSummary:
    """심판례에 법령 문구를 쓰면 거짓말이 된다.

    처음에 하나로 뭉쳐 놨더니 이런 문장이 나갔다.

        「…심판청구가 적법한지 여부 — 기각」이(가) 개정되어
        시행일은 원문 확인이 필요합니다.

    심판례는 개정된 것이 아니고 시행일도 없다.
    """

    META: ClassVar[dict[str, str]] = {
        "content_kind": "TRIBUNAL_DECISION",
        "result": "기각",
        "tax_type": "부가",
        "disposition_agency": "OO세무서장",
    }

    def test_never_says_amended(self):
        text = _summary(raw("가공세금계산서 사건 — 기각"), self.META, None)
        assert "개정" not in text
        assert "시행" not in text

    def test_leads_with_the_outcome(self):
        """인용인지 기각인지가 실무에서 제일 먼저 보는 정보다."""
        text = _summary(raw("사건명"), self.META, None)
        assert "청구 기각" in text
        assert "부가" in text

    def test_unknown_outcome_is_omitted_not_guessed(self):
        meta = {**self.META, "result": ""}
        text = _summary(raw("사건명"), meta, None)
        assert "청구" not in text
        assert "조세심판원 결정" in text

    def test_effective_date_is_ignored_for_tribunals(self):
        """심판례에 시행일이 실려 오더라도 문구에 넣지 않는다."""
        text = _summary(raw("사건명"), self.META, dt.date(2027, 1, 1))
        assert "2027" not in text
