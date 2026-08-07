"""검색 텍스트 합본. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

from app.services.ai.classify import build_search_text

BODY = {
    "changes": [
        {"text": "학원 사업장의 4대보험 가입 기준이 변경됩니다", "evidence_ids": ["x"]},
        {"text": "신고 서식이 개편됩니다"},
    ],
    "required_actions": ["강사 계약서를 다시 확인하세요"],
    "affected_users": ["학원 운영자"],
    "deadlines": [{"label": "2026년 9월 30일까지 신고", "date": "2026-09-30"}],
    "topics": ["4대보험"],
}


class TestBuildSearchText:
    def test_includes_body_not_just_title(self):
        """제목만 검색하면 '학원 4대보험' 같은 실무 질문이 안 걸린다."""
        text = build_search_text("국민건강보험법 시행령", "가입 기준 변경", BODY)

        assert "4대보험" in text
        assert "강사 계약서" in text
        assert "학원 운영자" in text

    def test_reads_grounded_items(self):
        """근거가 붙은 항목은 dict 안의 text 에 들어 있다."""
        text = build_search_text("제목", None, BODY)

        assert "신고 서식이 개편됩니다" in text
        assert "evidence_ids" not in text

    def test_includes_deadline_labels(self):
        text = build_search_text("제목", None, BODY)

        assert "2026년 9월 30일까지 신고" in text

    def test_deduplicates_repeats(self):
        body = {"changes": ["같은 문장"], "required_actions": ["같은 문장"]}
        text = build_search_text("제목", "같은 문장", body)

        assert text.count("같은 문장") == 1

    def test_survives_empty_body(self):
        assert build_search_text("제목만 있음", None, {}) == "제목만 있음"

    def test_ignores_malformed_values(self):
        """AI 출력이 항상 예상한 모양은 아니다. 검색 텍스트 때문에 죽으면 안 된다."""
        text = build_search_text("제목", None, {"changes": "배열이 아님", "deadlines": [None]})

        assert text == "제목"
