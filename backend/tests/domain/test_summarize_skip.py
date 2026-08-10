"""이미 요약된 건을 다시 집지 않는가. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

from app.summarize import _already_summarized


class TestAlreadySummarized:
    def test_ai_result_with_changes_is_done(self):
        assert _already_summarized({"_ai": True, "changes": ["뭔가 바뀜"]}) is True

    def test_ai_result_without_changes_is_also_done(self):
        """빈 changes 는 실패가 아니라 정상적인 결과다.

        프롬프트가 "실질 변경이 하나도 없으면 changes 를 빈 배열로 두라"고 시킨다.
        자구 정리만 있는 개정이 여기 해당한다. 이걸 미완으로 보면 그 건이
        영원히 다시 집히고 무료 한도만 태운다 — 실제로 그랬다.
        """
        assert _already_summarized({"_ai": True, "changes": []}) is True

    def test_untouched_body_is_not_done(self):
        assert _already_summarized({"changes": ["초안 문구"]}) is False

    def test_empty_body_is_not_done(self):
        assert _already_summarized({}) is False

    def test_ai_false_is_not_done(self):
        assert _already_summarized({"_ai": False, "changes": ["x"]}) is False
