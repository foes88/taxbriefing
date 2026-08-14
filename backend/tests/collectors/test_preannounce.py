"""입법예고 파싱. 네트워크 없이 실행된다.

승인 전에 문서만 보고 만든 시험이었는데, 키가 나온 뒤 실제 응답과
맞지 않는 곳이 다섯 군데 있었다. **여기 있는 XML 은 실제 응답을 붙인
것이다.** 문서로 만든 시험은 문서가 맞는지만 확인해 준다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.collectors.preannounce import (
    PreannounceError,
    build_body,
    parse_list,
    total_count,
)

#: 2026-08-14 에 실제로 받은 응답에서 두 건을 잘라 냈다.
#: 항목 태그는 `ApiList04Vo`, 날짜는 `2026. 8. 7.`, 제목 앞에 `[진행]`.
SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <retMsg>200</retMsg>
  <totalCnt>276</totalCnt>
  <pageIndex>1</pageIndex>
  <pageSize>100</pageSize>
  <list>
    <ApiList04Vo>
      <ogLmPpSeq>88015</ogLmPpSeq>
      <lsNm><![CDATA[[진행]부가가치세법 일부개정법률안 입법예고]]></lsNm>
      <lsClsNm>법률</lsClsNm>
      <asndOfiNm>재정경제부</asndOfiNm>
      <pntcNo>2026-512</pntcNo>
      <pntcDt>2026. 8. 4.</pntcDt>
      <stYd>2026. 8. 4.</stYd>
      <edYd>2026. 8. 20.</edYd>
      <FileName>(법령안) 부가가치세법 일부개정법률(안).hwpx</FileName>
      <FileDownLink>http://www.lawmaking.go.kr/file/download/10989560/X4A0OC75</FileDownLink>
      <readCnt>346</readCnt>
      <mappingLbicId>0</mappingLbicId>
      <announceType>TYPE5</announceType>
    </ApiList04Vo>
    <ApiList04Vo>
      <ogLmPpSeq>88110</ogLmPpSeq>
      <lsNm><![CDATA[[진행]관세청과 그 소속기관 직제 시행규칙 일부개정령안 입법예고]]></lsNm>
      <lsClsNm>부령</lsClsNm>
      <asndOfiNm>관세청</asndOfiNm>
      <pntcNo>2026-301</pntcNo>
      <pntcDt>2026. 8. 7.</pntcDt>
      <stYd>2026. 8. 7.</stYd>
      <edYd>2026. 8. 14.</edYd>
      <FileName>직제.hwpx</FileName>
      <FileDownLink>http://www.lawmaking.go.kr/file/download/1/Y</FileDownLink>
      <readCnt>12</readCnt>
      <announceType>TYPE5</announceType>
    </ApiList04Vo>
  </list>
</result>"""

REJECTED = "<result>\n  <retMsg>401</retMsg>\n</result>"


class TestParseList:
    def test_reads_the_documented_fields(self):
        item = parse_list(SAMPLE)[0]
        assert item.serial == "88015"
        assert item.agency == "재정경제부"
        assert item.law_type == "법률"
        assert item.notice_no == "2026-512"

    def test_status_prefix_is_stripped_from_the_title(self):
        """제목 앞에 `[진행]` 이 붙어서 온다.

        그대로 두면 화면과 텔레그램에 `[진행]부가가치세법…` 으로 나간다.
        진행 여부는 diff 파라미터로 이미 정해서 부르므로 제목에 둘 이유가 없다.
        """
        assert parse_list(SAMPLE)[0].title == "부가가치세법 일부개정법률안"

    def test_trailing_notice_word_is_stripped(self):
        """제목 끝의 「입법예고」 도 뗀다.

        목록이 전부 입법예고라 붙어 있으나 마나고, 남겨 두면 요약이
        「부가가치세법 일부개정법률안 입법예고」이(가) 입법예고됐습니다
        로 읽힌다. 종류는 상태(PREANNOUNCED)가 이미 말한다.
        """
        assert "입법예고" not in parse_list(SAMPLE)[0].title

    def test_dates_with_spaces_and_single_digits(self):
        """`2026. 8. 4.` — 점 사이에 공백이 있고 월·일이 한 자리다.

        점과 공백을 지우고 8자리로 읽으려 했더니 `202684` 가 되어 전부
        None 이었다. 법제처 심판례에서 의결일 20건이 통째로 빈 적이 있는데
        그때와 똑같이 날짜 구분자를 잘못 봤다. 세 번째는 없어야 한다.
        """
        item = parse_list(SAMPLE)[0]
        assert item.noticed_at == dt.date(2026, 8, 4)
        assert item.opens_at == dt.date(2026, 8, 4)
        assert item.closes_at == dt.date(2026, 8, 20)

    def test_public_url_is_built_from_the_serial(self):
        """목록은 일련번호만 준다. 사람이 여는 화면 주소는 우리가 만든다."""
        assert parse_list(SAMPLE)[0].canonical_url.endswith("/gcom/ogLmPp/88015")

    def test_success_code_is_not_treated_as_an_error(self):
        """성공도 retMsg 200 으로 온다.

        retMsg 가 있으면 무조건 실패로 봤더니 정상 응답까지 예외가 됐다.
        """
        assert len(parse_list(SAMPLE)) == 2

    def test_total_count_is_read_from_the_server(self):
        """건수는 서버에 묻는다. 받은 쪽수로 세지 않는다."""
        assert total_count(SAMPLE) == 276

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
            parse_list("<result><list>")

    def test_rows_without_a_title_are_skipped(self):
        assert parse_list("<r><ApiList04Vo><ogLmPpSeq>1</ogLmPpSeq></ApiList04Vo></r>") == []


class TestBody:
    def test_says_it_is_not_settled_yet(self):
        """이 화면에서 가장 위험한 오해는 "이미 바뀌었구나" 다."""
        body = build_body(parse_list(SAMPLE)[0])
        assert "확정된 개정이 아닙니다" in body
        assert "무산될 수 있습니다" in body

    def test_shows_the_comment_window(self):
        """의견을 낼 수 있는 기간이 이 항목의 값이다."""
        assert "2026-08-04 ~ 2026-08-20" in build_body(parse_list(SAMPLE)[0])
