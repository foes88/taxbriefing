"""심판례 본문 구조. 네트워크·DB 없이 실행된다.

심판례에 법령 틀을 씌우면 화면이 거짓말을 한다.

    달라지는 점     · 개정 되었습니다.
    지금 해야 할 일  · 시행일 전에 해당 조문이 적용되는지 확인하세요.

개정된 것이 없고 시행일도 없다. 이미 끝난 남의 사건이다.
"""

from __future__ import annotations

from typing import ClassVar

from app.bulk_draft import _tribunal_body
from app.services.collectors.tribunal import build_body, parse_sections


class TestParseSections:
    def test_round_trip(self):
        """`build_body` 가 붙인 구획을 그대로 되읽는다."""
        detail = {
            "사건명": "가공세금계산서 수취 여부",
            "세목": "부가가치세",
            "재결요지": "실물거래 없이 수수한 것으로 본다",
            "이유": "1.처분개요\n청구인은 …",
            "주문": "심판청구를 기각한다.",
        }
        sections = parse_sections(build_body(detail))
        assert sections["사건명"] == "가공세금계산서 수취 여부"
        assert sections["판단 요지"] == "실물거래 없이 수수한 것으로 본다"
        assert sections["주문"] == "심판청구를 기각한다."

    def test_keeps_newlines_inside_a_section(self):
        text = "[판단 이유]\n첫 줄\n둘째 줄\n\n[주문]\n기각한다."
        assert parse_sections(text)["판단 이유"] == "첫 줄\n둘째 줄"

    def test_empty_sections_are_dropped(self):
        assert parse_sections("[주문]\n\n[세목]\n부가") == {"세목": "부가"}

    def test_plain_text_yields_nothing(self):
        """구획 표시가 없는 원문은 빈 결과다. 억지로 가르지 않는다."""
        assert parse_sections("그냥 줄글입니다. [참고] 같은 게 문장 안에 있어도.") == {}


class TestTribunalBody:
    META: ClassVar[dict[str, str]] = {
        "tax_type": "부가가치세",
        "result": "기각",
        "case_no": "조심2025부1234",
        "disposition_agency": "○○세무서",
        "related_laws": "부가가치세법 제39조",
    }

    def _version(self, text: str):
        class _V:
            normalized_text = text

        return _V()

    def test_sections_follow_reading_order(self):
        """사건 → 다툰 것 → 판단 → 결론. 원문 순서가 아니라 읽는 순서다."""
        version = self._version(
            "[주문]\n기각한다.\n\n[사건명]\n사건\n\n[판단 이유]\n이유\n\n[판단 요지]\n요지"
        )
        body = _tribunal_body(version, self.META)
        assert [s["label"] for s in body["tribunal"]["sections"]] == [
            "사건명",
            "판단 요지",
            "판단 이유",
            "주문",
        ]

    def test_no_law_shaped_lies(self):
        """개정 문구와 시행일 안내가 들어가지 않는다."""
        body = _tribunal_body(self._version("[주문]\n기각한다."), self.META)
        assert not body.get("changes")
        assert not body.get("required_actions")
        assert not body.get("affected_users")

    def test_metadata_is_carried_over(self):
        body = _tribunal_body(self._version("[주문]\n기각한다."), self.META)
        t = body["tribunal"]
        assert t["tax_type"] == "부가가치세"
        assert t["outcome"] == "기각"
        assert t["related_laws"] == "부가가치세법 제39조"

    def test_missing_metadata_becomes_empty_not_guessed(self):
        """모르는 것은 빈 문자열이다. 결론을 추측하면 반대로 읽힌다."""
        body = _tribunal_body(self._version("[주문]\n기각한다."), {})
        assert body["tribunal"]["outcome"] == ""
        assert body["tribunal"]["tax_type"] == ""

    def test_unparseable_body_yields_no_sections(self):
        """구획을 못 읽으면 빈 목록. 화면은 이걸 보고 원문 링크로 돌린다."""
        body = _tribunal_body(self._version("구획 표시가 없는 원문"), self.META)
        assert body["tribunal"]["sections"] == []
