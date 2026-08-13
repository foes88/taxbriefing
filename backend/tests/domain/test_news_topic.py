"""뉴스가 세무 이야기인가. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

import pytest

from app.domain.news_topic import LIKE_PATTERNS, TAX_TERMS, is_tax_news


class TestKeeps:
    """실무자가 봐야 하는 것은 남는다."""

    @pytest.mark.parametrize(
        "title",
        [
            "국세청, 주식 양도세 신고…대주주 판정·30% 세율·저가양도 적발사례 공개",
            "'3.3%가 2.2%로' 프리랜서가 가장 반길 세제개편",
            "재경부 \"출산세액공제 폐지 아니다…예산지원 전환으로 형평성 높인다\"",
            # 처음 만든 목록에서 떨어졌던 것들. 둘 다 실무자가 봐야 한다.
            '"최대 260만 원까지"…근로장려금 이달 말 지급 속 내년 신청 대상 기준',
            "[판세] 인적분할로 취득한 분할신설법인 주식 양도시 취득가액 기준시가 산정법",
            # 4대보험은 사장님에게 세금과 같은 고지서다.
            "내년 건강보험료율 동결…직장가입자 부담 얼마나",
        ],
    )
    def test_kept(self, title):
        assert is_tax_news(title)


class TestDrops:
    """기업 홍보와 지역 행사는 뺀다.

    세무 전문지 RSS 라도 이런 것이 섞여 들어온다. 112건 중 39건이었다.
    셋 중 하나가 이런 제목이면 며칠 만에 그 탭을 안 열게 된다.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "하나금융그룹, 민관협력 중장년 일자리 창출 'JOB매칭 페스타 in 대전'성료!!!",
            "넷마블문화재단, '2026 게임소통학교' 성료...게임문화 이해 및 직업체험",
            "NH농협은행, 창립기념일 맞아 'NH농심천심예·적금' 출시",
            "신한은행, '슈퍼쏠져 나라사랑카드 라운지'에 삼성전자 패밀리몰 서비스 제공",
        ],
    )
    def test_dropped(self, title):
        assert not is_tax_news(title)

    def test_empty_title(self):
        assert not is_tax_news("")


class TestPatterns:
    def test_sql_patterns_match_the_terms(self):
        """SQL 로 거르는 것과 파이썬으로 판단하는 것이 어긋나면 안 된다.

        어긋나면 목록 건수와 실제 보이는 수가 달라진다.
        """
        assert len(LIKE_PATTERNS) == len(TAX_TERMS)
        assert all(p.startswith("%") and p.endswith("%") for p in LIKE_PATTERNS)
        assert all(term in pattern for term, pattern in zip(TAX_TERMS, LIKE_PATTERNS, strict=True))
