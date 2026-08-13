"""신구법 대조표. 네트워크 없이 실행된다."""

from __future__ import annotations

import httpx
import pytest

from app.services.collectors.old_and_new import (
    OldAndNewClient,
    OldAndNewError,
    is_placeholder,
    split_segments,
)


class TestSplitSegments:
    """`<P>` 로 감싼 곳이 법제처가 표시한 변경 부분이다."""

    def test_marks_changed_span(self):
        segments = split_segments("다만, <P>별표 1 제1호</P>는 제외한다.")
        assert segments == [
            {"text": "다만, ", "changed": False},
            {"text": "별표 1 제1호", "changed": True},
            {"text": "는 제외한다.", "changed": False},
        ]

    def test_no_tag_is_one_plain_segment(self):
        assert split_segments("제4조(이동통신역무)") == [
            {"text": "제4조(이동통신역무)", "changed": False}
        ]

    def test_keeps_every_character(self):
        """조각을 이어 붙이면 태그만 뺀 원문이 그대로 나와야 한다."""
        raw = "앞<P>가운데</P>뒤<P>끝</P>"
        assert "".join(s["text"] for s in split_segments(raw)) == "앞가운데뒤끝"

    def test_multiline_span(self):
        segments = split_segments("가<P>여러\n줄</P>나")
        assert segments[1] == {"text": "여러\n줄", "changed": True}

    def test_empty(self):
        assert split_segments("") == []


class TestIsPlaceholder:
    def test_unchanged_marker(self):
        assert is_placeholder("2. ∼ 4. (현행과 같음)")  # noqa: RUF001
        assert is_placeholder("2. ∼ 4. (생  략)")  # noqa: RUF001

    def test_real_article_is_not_placeholder(self):
        assert not is_placeholder("제6조(지방공사의 범위) 영 제8조제2항제7호에서")


def _client(handler) -> OldAndNewClient:
    transport = httpx.MockTransport(handler)
    client = OldAndNewClient(httpx.Client(transport=transport))
    object.__setattr__(client, "oc", "test")
    return client


def _detail(olds, news) -> dict:
    return {
        "OldAndNewService": {
            "구조문목록": {"조문": olds},
            "신조문목록": {"조문": news},
        }
    }


class TestDiff:
    def test_keeps_only_marked_rows(self):
        payload = _detail(
            [
                {"no": "1", "content": "제4조(제목) 그대로인 조문"},
                {"no": "2", "content": "다만, <P>30일</P> 이내"},
            ],
            [
                {"no": "1", "content": "제4조(제목) 그대로인 조문"},
                {"no": "2", "content": "다만, <P>60일</P> 이내"},
            ],
        )
        rows, dropped = _client(lambda r: httpx.Response(200, json=payload)).diff("1")
        assert dropped == 0
        assert [row.no for row in rows] == ["2"]
        assert rows[0].old[1] == {"text": "30일", "changed": True}
        assert rows[0].new[1] == {"text": "60일", "changed": True}

    def test_placeholder_pair_is_dropped(self):
        """양쪽 다 '(현행과 같음)' 이면 보여줄 것이 없다."""
        payload = _detail(
            [{"no": "1", "content": "2. ∼ 4. <P>(생  략)</P>"}],  # noqa: RUF001
            [{"no": "1", "content": "2. ∼ 4. <P>(현행과 같음)</P>"}],  # noqa: RUF001
        )
        rows, _ = _client(lambda r: httpx.Response(200, json=payload)).diff("1")
        assert rows == []

    def test_mismatched_counts_raise(self):
        """짝이 안 맞으면 버린다. 억지로 붙이면 엉뚱한 조문을 나란히 놓는다."""
        payload = _detail(
            [{"no": "1", "content": "<P>가</P>"}, {"no": "2", "content": "<P>나</P>"}],
            [{"no": "1", "content": "<P>다</P>"}],
        )
        with pytest.raises(OldAndNewError, match="조문 수가 다릅니다"):
            _client(lambda r: httpx.Response(200, json=payload)).diff("1")

    def test_mismatched_numbers_raise(self):
        payload = _detail(
            [{"no": "1", "content": "<P>가</P>"}],
            [{"no": "7", "content": "<P>다</P>"}],
        )
        with pytest.raises(OldAndNewError, match="번호가 어긋납니다"):
            _client(lambda r: httpx.Response(200, json=payload)).diff("1")

    def test_truncation_is_reported(self):
        """말없이 자르면 '이게 전부' 로 읽힌다. 몇 개를 잘랐는지 같이 준다."""
        many = [{"no": str(i), "content": f"<P>{i}</P>"} for i in range(60)]
        payload = _detail(many, many)
        rows, dropped = _client(lambda r: httpx.Response(200, json=payload)).diff("1")
        assert len(rows) == 40
        assert dropped == 20

    def test_html_response_raises(self):
        """OC 가 틀리면 법제처가 HTML 오류 페이지를 준다."""
        with pytest.raises(OldAndNewError, match="JSON 이 아닙니다"):
            _client(lambda r: httpx.Response(200, text="<html>error</html>")).diff("1")


class TestSearch:
    def test_single_result_comes_as_object(self):
        """1건일 때 배열 대신 객체가 온다."""
        payload = {
            "OldAndNewLawSearch": {
                "oldAndNew": {
                    "신구법일련번호": "286379",
                    "신구법ID": "007507",
                    "신구법명": "소득세법 시행규칙",
                    "공포번호": "00033",
                    "시행일자": "20260701",
                    "제개정구분명": "일부개정",
                }
            }
        }
        items = _client(lambda r: httpx.Response(200, json=payload)).search("소득세법")
        assert len(items) == 1
        assert items[0].law_id == "007507"
        assert items[0].promulgation_no == "00033"

    def test_empty_result(self):
        payload = {"OldAndNewLawSearch": {"resultMsg": "success"}}
        assert _client(lambda r: httpx.Response(200, json=payload)).search("없는법") == []
