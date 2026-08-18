"""입법예고는 AI 를 돌리지 않는다. 네트워크 없이 실행된다.

**종류가 아니라 상태로 걸러야 한다.** 입법예고의 content_kind 는 POLICY 라
심판례·해석례를 빼던 목록을 그냥 통과했고, 배치가 15건을 전부 덮어썼다.
"""

from __future__ import annotations

import datetime as dt

from app.api.v1.public import _comment_deadline
from app.bulk_draft import _is_preannounce, _preannounce_body, _preannounce_summary
from app.domain.enums import LegalStatus
from app.summarize import KINDS_WITHOUT_AI

META = {
    "legal_status": "PREANNOUNCED",
    "content_kind": "POLICY",
    "agency": "재정경제부",
    "law_type": "법률",
    "opens_at": "2026-08-04",
    "closes_at": "2026-08-20",
}


class _Raw:
    title = "부가가치세법 일부개정법률안"


class TestKindIsNotEnough:
    def test_preannounce_is_a_policy_by_kind(self):
        """그래서 종류 목록으로는 못 거른다. 이걸 놓쳐서 덮어썼다."""
        assert META["content_kind"] not in KINDS_WITHOUT_AI

    def test_status_tells_them_apart(self):
        assert _is_preannounce(META)
        assert not _is_preannounce({"legal_status": "PROMULGATED"})

    def test_status_value_matches_the_enum(self):
        """문자열을 손으로 적어 두면 enum 이 바뀔 때 조용히 안 걸린다."""
        assert META["legal_status"] == LegalStatus.PREANNOUNCED.value


class TestSummary:
    def test_leads_with_the_deadline(self):
        """제목을 넣었더니 카드가 문장을 통째로 버렸다.

        요약이 제목을 품고 있으면 제목만 보여주는 규칙(headlineOf)에
        걸린 것이다. 그 안에 마감 날짜가 있었다.
        """
        summary = _preannounce_summary(_Raw, META)
        assert summary == "의견 제출은 2026년 8월 20일까지입니다."
        assert _Raw.title not in summary

    def test_does_not_repeat_the_caveat(self):
        """상태 배지와 경고 문구가 이미 두 번 말한다. 세 번째는 소음이다."""
        assert "확정" not in _preannounce_summary(_Raw, META)

    def test_no_deadline_means_no_invented_date(self):
        summary = _preannounce_summary(_Raw, {**META, "closes_at": None})
        assert "까지" not in summary
        assert "확정된 개정이 아닙니다" in summary


class TestBody:
    def test_carries_the_deadline_as_a_value(self):
        """문장 안에만 두면 화면이 며칠 남았는지 셀 수 없다."""
        assert _preannounce_body(META)["comment_deadline"] == "2026-08-20"

    def test_makes_no_required_actions(self):
        """확정되지 않은 개정에 할 일을 만들지 않는다."""
        assert _preannounce_body(META)["required_actions"] == []

    def test_says_it_may_never_happen(self):
        assert "무산될 수 있습니다" in _preannounce_body(META)["needs_expert"][0]


class TestApiField:
    def test_reads_the_deadline(self):
        assert _comment_deadline(_preannounce_body(META)) == dt.date(2026, 8, 20)

    def test_missing_or_broken_gives_none(self):
        """모르는 값은 비워 둔다. 만들면 거짓이 된다."""
        assert _comment_deadline(None) is None
        assert _comment_deadline({}) is None
        assert _comment_deadline({"comment_deadline": "2026-13-99"}) is None
        assert _comment_deadline({"comment_deadline": 20260820}) is None
