"""입법예고 파싱. 네트워크 없이 실행된다.

승인을 기다리는 동안 만들어 둔 것이라, **문서에 적힌 응답 모양**으로
시험한다. 실제 응답이 오면 여기 붙여 넣고 다시 돌리면 된다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.collectors.preannounce import (
    AGENCIES,
    PreannounceError,
    build_body,
    parse_list,
)

# 문서(정보공개 활용가이드)의 출력 필드 그대로.
SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<ogLmPpSearch>
  <ogLmPp>
    <ogLmPpSeq>87228</ogLmPpSeq>
    <lsNm>부가가치세법 시행령 일부개정령안 입법예고</lsNm>
    <lsClsNm>대통령령</lsClsNm>
    <asndOfiNm>기획재정부</asndOfiNm>
    <pntcNo>2026-341</pntcNo>
    <pntcDt>2026.08.11.</pntcDt>
    <stYd>2026.08.11.</stYd>
    <edYd>2026.09.20.</edYd>
    <FileName>부가가치세법 시행령 일부개정령안.hwp</FileName>
    <FileDownLink>https://www.lawmaking.go.kr/file/12345</FileDownLink>
    <readCnt>412</readCnt>
    <announceType>입법예고</announceType>
  </ogLmPp>
</ogLmPpSearch>"""

REJECTED = "<result>\n  <retMsg>401</retMsg>\n</result>"


class TestParseList:
    def test_reads_the_documented_fields(self):
        item = parse_list(SAMPLE)[0]
        assert item.serial == "87228"
        assert item.title == "부가가치세법 시행령 일부개정령안 입법예고"
        assert item.agency == "기획재정부"
        assert item.law_type == "대통령령"
        assert item.notice_no == "2026-341"

    def test_dates_with_trailing_dots(self):
        """이 API 는 `2026.08.11.` 처럼 끝에도 마침표를 붙인다.

        법제처 심판례가 점 구분이라 의결일이 20건 전부 빈 적이 있다.
        같은 자리에서 두 번 넘어지지 않는다.
        """
        item = parse_list(SAMPLE)[0]
        assert item.noticed_at == dt.date(2026, 8, 11)
        assert item.opens_at == dt.date(2026, 8, 11)
        assert item.closes_at == dt.date(2026, 9, 20)

    def test_public_url_is_built_from_the_serial(self):
        """목록은 일련번호만 준다. 사람이 여는 화면 주소는 우리가 만든다."""
        assert parse_list(SAMPLE)[0].canonical_url.endswith("/gcom/ogLmPp/87228")

    def test_rejection_raises_instead_of_returning_empty(self):
        """**빈 목록으로 돌려주면 안 된다.**

        승인 전에는 retMsg 401 이 온다. 그때 빈 목록을 주면 화면이
        "오늘은 예고가 없나 보다" 로 읽는다. 그건 사실이 아니다.
        """
        with pytest.raises(PreannounceError, match="401"):
            parse_list(REJECTED)

    def test_rejection_message_says_what_to_check(self):
        with pytest.raises(PreannounceError, match="정보공개 신청"):
            parse_list(REJECTED)

    def test_broken_xml_raises(self):
        with pytest.raises(PreannounceError, match="파싱"):
            parse_list("<ogLmPpSearch><ogLmPp>")

    def test_rows_without_a_title_are_skipped(self):
        xml = "<r><ogLmPp><ogLmPpSeq>1</ogLmPpSeq></ogLmPp></r>"
        assert parse_list(xml) == []


class TestBody:
    def test_says_it_is_not_settled_yet(self):
        """이 화면에서 가장 위험한 오해는 "이미 바뀌었구나" 다."""
        body = build_body(parse_list(SAMPLE)[0])
        assert "확정된 개정이 아닙니다" in body
        assert "무산될 수 있습니다" in body

    def test_shows_the_comment_window(self):
        """의견을 낼 수 있는 기간이 이 항목의 값이다."""
        assert "2026-08-11 ~ 2026-09-20" in build_body(parse_list(SAMPLE)[0])


class TestAgencies:
    def test_covers_national_and_local_tax(self):
        """지방세는 행정안전부 소관이다. 사장님에게는 국세와 같은 고지서다."""
        codes = {code for code, _ in AGENCIES}
        assert {"1210000", "1051000", "1741000"} <= codes
