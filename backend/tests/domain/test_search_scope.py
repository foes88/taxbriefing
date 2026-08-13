"""검색 대상 범위. 네트워크·DB 없이 실행된다.

**절반만 찾아 주는 검색은 안 쓰느니만 못하다** — 없는 줄 알고 넘어가기 때문이다.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.ai.classify import build_search_text


class TestAiBackedContent:
    """법령은 AI 출력에서 검색 텍스트를 만든다."""

    BODY: ClassVar[dict[str, Any]] = {
        "changes": ["학원 사업장의 4대보험 가입 기준이 변경됩니다"],
        "required_actions": ["강사 계약서를 다시 확인하세요"],
    }

    def test_uses_ai_fields(self):
        text = build_search_text("국민건강보험법 시행령", "가입 기준 변경", self.BODY)
        assert "4대보험" in text
        assert "강사 계약서" in text

    def test_raw_text_is_not_appended_when_ai_fields_exist(self):
        """AI 요약이 있으면 원문까지 넣지 않는다. 같은 말을 두 번 담게 된다."""
        text = build_search_text("제목", "요약", self.BODY, raw_text="원문 전체 내용")
        assert "원문 전체 내용" not in text


class TestContentWithoutAi:
    """심판례·법안은 일부러 AI 를 돌리지 않는다.

    원문에 이미 쟁점과 판단이 갈려 있어 모델을 쓸 자리가 아니다.
    그런데 그 탓에 검색 대상에서 통째로 빠졌었다.

        가산세     검색 1건 / 본문 7건
        세금계산서  검색 5건 / 본문 11건
    """

    def test_falls_back_to_raw_text(self):
        text = build_search_text(
            "가공세금계산서 사건 — 기각",
            "조세심판원 결정 · 부가 관련",
            {},
            raw_text="[판단 이유]\n쟁점거래는 가지급금으로 보아 매입세액을 불공제하였다",
        )
        assert "가지급금" in text
        assert "매입세액" in text

    def test_raw_text_is_not_truncated(self):
        """4,000자로 잘랐더니 여전히 놓쳤다.

        심판례는 사실관계를 길게 적은 뒤 **뒤쪽에서** 쟁점을 다룬다.
        "쟁점 단어는 앞쪽에 몰려 있다" 는 가정이 틀렸다.
        """
        buried = "가" * 8000 + "\n쟁점: 업무용승용차 손금 인정 여부"
        text = build_search_text("제목", None, {}, raw_text=buried)
        assert "업무용승용차" in text

    def test_no_raw_text_still_works(self):
        text = build_search_text("제목만 있음", None, {})
        assert text == "제목만 있음"
