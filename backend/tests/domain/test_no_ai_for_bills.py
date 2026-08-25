"""본문이 없으면 AI 를 쓰지 않는다. 네트워크 없이 실행된다.

같은 실수를 세 번 했다. 심판례·해석례에서 한 번, 입법예고에서 한 번,
법안에서 또 한 번. **모델에게 제목만 주고 요지를 쓰라고 하면 지어낸다.**
"""

from __future__ import annotations

from app.bulk_draft import _bill_summary
from app.domain.enums import ContentKind
from app.summarize import KINDS_WITHOUT_AI

META = {
    "content_kind": "BILL",
    "proposer": "문진석의원 등 12인",
    "committee": "재정경제기획위원회",
    "proposed_at": "2026-08-21",
}


class TestKindsWithoutAi:
    def test_bills_are_excluded(self):
        """국회 API 는 조문을 안 준다. 의안명·발의자·처리결과가 전부다.

        86건에 돌렸더니 나온 것이 전부 빈 배열이었고, 한 줄 요약은
        「구체적인 내용이 확정되지 않아」 로 덮였다. 내용은 확정돼 있다 —
        우리가 조문을 안 가지고 있을 뿐이고, 그건 모델이 알 수 없다.
        """
        assert ContentKind.BILL.value in KINDS_WITHOUT_AI

    def test_the_other_bodiless_kinds_too(self):
        for kind in (
            ContentKind.TRIBUNAL,
            ContentKind.INTERPRETATION,
            ContentKind.PRECEDENT,
        ):
            assert kind.value in KINDS_WITHOUT_AI

    def test_laws_still_go_through_ai(self):
        """법령은 전문이 온다. 거기서는 모델이 할 일이 있다."""
        assert ContentKind.POLICY.value not in KINDS_WITHOUT_AI


class TestBillSummary:
    def test_says_who_and_when_not_what(self):
        """가진 것만 적는다. 조문이 없으니 내용은 말하지 않는다."""
        out = _bill_summary(META)
        assert "문진석의원 등 12인" in out
        assert "2026년 8월 21일 발의" in out
        assert "재정경제기획위원회" in out

    def test_never_says_it_is_settled(self):
        """「바뀝니다」 가 아니라 「발의됐습니다」 다. 아직 법이 아니다."""
        out = _bill_summary(META)
        assert "통과 여부는 정해지지 않았습니다" in out
        assert "시행" not in out

    def test_does_not_claim_the_content_is_unknown(self):
        """모델이 쓰던 문장은 사실이 아니었다.

        「구체적인 내용이 확정되지 않아」 — 확정돼 있다. 우리가 안 읽었을 뿐이다.
        """
        out = _bill_summary(META)
        assert "확정되지 않아" not in out
        assert "공개되지 않아" not in out

    def test_missing_fields_do_not_become_lies(self):
        out = _bill_summary({"content_kind": "BILL"})
        assert "국회 발의 법안" in out
        assert "None" not in out
