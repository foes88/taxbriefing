"""행정규칙 중 납세자에게 걸리는 것만 고른다. 네트워크 없이 실행된다.

시험에 쓰는 제목은 전부 **실제로 받은 90건**에서 가져왔다. 지어낸 제목으로
시험하면 지어낸 규칙만 통과한다.
"""

from __future__ import annotations

import pytest

from app.domain.admin_rule import is_internal_rule

#: 사장님에게 그대로 적용되는 것들. 형식이 고시·예규여도 담아야 한다.
KEEP = [
    "국세청 건물 기준시가 계산방법 고시 (고시)",
    "조세특례제한법 시행령 제111조제2항의 규정에 의한 재정경제부장관이 정하여 고시하는 법인 (고시)",
    "교육세법 시행령 제4조제2항제13호의 규정에 의한 재정경제부장관이 정하여 고시하는 대출 (고시)",
    (
        "조세특례제한법 시행령상 재정경제부 장관이 정하는 부가가치세가 면제되는 "
        "정부업무를 대행하는 단체인 국제경기대회 지원법에 따라 설립된 조직위원회 (고시)"
    ),
    "재정경제부 소관 법령에 따른 행정처분 및 과태료의 가중처분에 관한 세부지침 (예규)",
    "국가를 당사자로 하는 계약에 관한 법률 등의 재정경제부장관이 정하는 고시금액 (고시)",
]

#: 공무원과 부처 내부를 구속하는 것들. 사장님이 알 이유가 없다.
DROP = [
    "국세청당직근무규정 (훈령)",
    "국세청 인사관리규정 (훈령)",
    "국세청 방첩업무 운영규정 (훈령)",
    "국세청 기록관 운영규정 (훈령)",
    "국세청 사무분장규정 (훈령)",
    "국세청위임전결규정 (훈령)",
    "국세상담센터 기본운영규정 (훈령)",
    "국세청 「국세 체납관리단」 운영 규정 (훈령)",
    "국세청 주거용 재산 관리 규정 (훈령)",
    "재정경제부 동호회 운영 규정 (훈령)",
    "재정경제부 성희롱·성폭력·스토킹 예방 지침 (훈령)",
    "재정경제부 공무원의 가상자산 보유 제한에 관한 지침 (훈령)",
    "재정경제부 국제기구 초급전문가·중견전문가·인턴 파견 및 관리 규정 (예규)",
    "재정경제부 갈등관리 운영지침 (훈령)",
    "재정경제부 공무국외출장규정 (훈령)",
    "재정경제부 일상감사 지침 (훈령)",
    "재정경제부 부정청탁 및 금품등 수수의 신고사무 처리지침 (훈령)",
    "재정경제부 청렴옴부즈만 설치 및 운영에 관한 규정 (훈령)",
    "재정경제부 경고ㆍ주의 등 처분 지침 (훈령)",
    "산업통상부와 그 소속기관의 회계관계 공무원지정 및 재정보증 등에 관한 규정 (훈령)",
    "재정경제부 주요정보통신기반시설 지정 고시 (고시)",
    "(재정경제부) 국가연구개발성과 범부처 이어달리기 프로젝트 공통운영 지침 (고시)",
]


@pytest.mark.parametrize("title", KEEP)
def test_taxpayer_facing_rules_are_kept(title: str):
    assert not is_internal_rule(title), "사업자에게 적용되는 고시를 빼면 안 된다"


@pytest.mark.parametrize("title", DROP)
def test_internal_rules_are_dropped(title: str):
    assert is_internal_rule(title)


class TestWhyKeywordsAreNotEnough:
    """세목 낱말로는 못 가른다.

    「국세청 인사관리규정」에는 "국세" 가 들어 있다. 세목을 찾는 방식으로는
    통과한다. 기준은 세목이 아니라 **누구를 구속하는가** 다.
    """

    def test_tax_word_in_an_internal_rule_does_not_save_it(self):
        assert is_internal_rule("국세청 인사관리규정 (훈령)")

    def test_no_tax_word_in_a_binding_notice_does_not_kill_it(self):
        """「…정하여 고시하는 대출」에는 세목이 없지만 세법이 위임한 고시다."""
        assert not is_internal_rule(
            "교육세법 시행령 제4조제2항제13호의 규정에 의한 "
            "재정경제부장관이 정하여 고시하는 대출 (고시)"
        )


class TestSpacingAndDots:
    """띄어쓰기와 가운뎃점이 제각각이다.

    「운영 규정」과 「운영규정」이 같이 온다. 제목만 정규화하고 표는 그대로
    뒀더니 「경고ㆍ주의」 가 새 나갔다 — 양쪽에 같은 처리를 해야 한다.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "재정경제부 기록관 운영규정",
            "재정경제부 기록관 운영 규정",
            "재정경제부기록관운영규정",
        ],
    )
    def test_same_verdict_regardless_of_spacing(self, title: str):
        assert is_internal_rule(title)

    @pytest.mark.parametrize("dot", ["ㆍ", "·", " "])
    def test_middle_dot_variants_all_match(self, dot: str):
        assert is_internal_rule(f"재정경제부 경고{dot}주의 등 처분 지침")


class TestWhenUnsure:
    """모르면 담는 쪽으로 기운다.

    쓸데없는 것 하나를 더 지고 가는 비용보다 진짜 고시 하나를 조용히
    놓치는 비용이 크다. 놓친 것은 아무도 모른다.
    """

    def test_unknown_shape_is_kept(self):
        assert not is_internal_rule("정부조직 개편 반영을 위한 30개 예규의 일부개정")

    def test_empty_title_is_kept(self):
        assert not is_internal_rule("")
