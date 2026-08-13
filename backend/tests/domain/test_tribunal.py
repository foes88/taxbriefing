"""조세심판원 심판례 파싱. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

from typing import ClassVar

from app.services.collectors.tribunal import build_body, read_outcome


class TestReadOutcome:
    """인용인가 기각인가.

    목록의 `재결구분명` 은 이 값이 아니다 — "조세" 처럼 분야가 들어온다.
    그걸 결론인 줄 알고 제목에 붙였더니 "…부가가치세 처분 (조세)" 가 됐다.
    """

    def test_rejected(self):
        assert read_outcome({"주문": "심판청구를 기각한다."}) == "기각"

    def test_accepted(self):
        assert read_outcome({"주문": "처분청의 처분을 취소한다."}) == "인용"

    def test_partially_accepted(self):
        assert read_outcome({"주문": "과세표준 및 세액을 경정한다."}) == "일부인용"

    def test_dismissed(self):
        assert read_outcome({"주문": "심판청구를 각하한다."}) == "각하"

    def test_reinvestigation(self):
        assert read_outcome({"주문": "재조사하여 그 결과에 따라 경정한다."}) == "일부인용"

    def test_spacing_is_ignored(self):
        assert read_outcome({"주문": "심판청구를  기각 한다"}) == "기각"

    def test_unknown_stays_empty(self):
        """읽지 못하면 빈 값이다. **추측하지 않는다.**

        기각을 인용으로 잘못 표시하면 사업자가 정반대로 판단한다.
        """
        assert read_outcome({"주문": "무슨 말인지 알 수 없는 문장"}) == ""
        assert read_outcome({}) == ""


class TestBuildBody:
    DETAIL: ClassVar[dict[str, str]] = {
        "사건명": "가공세금계산서 수수로 보아 부가가치세를 부과한 처분의 당부",
        "세목": "부가",
        "처분청": "OO세무서장",
        "재결청": "조세심판원",
        "청구취지": "처분을 취소해 주십시오.",
        "재결요지": "순환거래로 확정됨",
        "이유": "1. 처분개요 …",
        "주문": "심판청구를 기각한다.",
        "관련법령": "부가가치세법 제60조",
        "참조결정": "",
    }

    def test_reads_in_the_order_a_person_reads(self):
        """사건 개요 → 무엇을 다퉜나 → 어떻게 판단했나 → 결론."""
        body = build_body(self.DETAIL)
        order = [body.index(label) for label in ("[사건명]", "[청구인 주장]", "[판단 이유]", "[주문]")]

        assert order == sorted(order)

    def test_labels_are_plain_korean(self):
        """행정 용어를 그대로 두면 사업자가 못 읽는다."""
        body = build_body(self.DETAIL)

        assert "[청구인 주장]" in body
        assert "[판단 요지]" in body
        assert "[청구취지]" not in body

    def test_empty_fields_are_dropped(self):
        """빈 제목만 늘어놓으면 "여기 뭔가 있어야 하는데" 하고 멈춘다."""
        body = build_body(self.DETAIL)

        assert "[참조 결정]" not in body

    def test_empty_detail_gives_empty_body(self):
        assert build_body({}) == ""
