"""법령 이름이 세법인가. 네트워크 없이 실행된다.

제목은 전부 2026-08-14 에 실제로 받은 입법예고 276건에서 가져왔다.
"""

from __future__ import annotations

import pytest

from app.domain.tax_law import is_tax_law

#: 재정경제부가 같은 날 올린 2026년 세법개정안. 의견 마감 8월 20일.
TAX = [
    "소득세법 일부개정법률안 입법예고",
    "법인세법 일부개정법률안 입법예고",
    "부가가치세법 일부개정법률안 입법예고",
    "상속세 및 증여세법 일부개정법률안 입법예고",
    "종합부동산세법 일부개정법률안 입법예고",
    "국세기본법 일부개정법률안 입법예고",
    "국세징수법 일부개정법률안 입법예고",
    "조세특례제한법 일부개정법률안 입법예고",
    "국제조세조정에 관한 법률 일부개정법률안 입법예고",
    "농어촌특별세법 일부개정법률안 입법예고",
    "소득세법 시행령 일부개정령안 입법예고",
    (
        "중국산 탄소강 및 그 밖의 합금강 열간압연 후판에 대한 "
        "덤핑방지관세 부과에 관한 규칙 일부개정령안 입법예고"
    ),
]

#: 같은 목록에 섞여 온 것들. 재정경제부가 낸 것도 세법이 아니면 뺀다.
NOT_TAX = [
    "국가를 당사자로 하는 계약에 관한 법률 시행령 일부개정령안 입법예고",
    "국유재산특례제한법 일부개정법률안 입법예고",
    "경제안보를 위한 공급망 안정화 지원 기본법 시행령 일부개정령안 입법예고",
    "지방자치분권 및 지역균형발전에 관한 특별법 시행령 일부개정령안 입법예고",
    "지방공무원 수당 등에 관한 규정 일부개정령안 입법예고",
    "자연재해대책법 시행령 일부개정령안 입법예고",
    "각종 기념일 등에 관한 규정 일부개정령안 입법예고",
    "초ㆍ중등교육법 시행령 일부개정령안 입법예고",
]


@pytest.mark.parametrize("name", TAX)
def test_tax_laws_are_kept(name: str):
    assert is_tax_law(name)


@pytest.mark.parametrize("name", NOT_TAX)
def test_others_are_dropped(name: str):
    assert not is_tax_law(name)


class TestOrganisationRules:
    """세목이 들어 있어도 조직도면 아니다.

    「관세청과 그 소속기관 직제 시행규칙」은 "관세" 가 있지만 관세청의
    조직 규정이다. 사장님이 낼 세금과 아무 상관이 없다.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "관세청과 그 소속기관 직제 시행규칙 일부개정령안 입법예고",
            "국세청과 그 소속기관 직제 일부개정령안",
        ],
    )
    def test_organisation_charts_are_dropped(self, name: str):
        assert not is_tax_law(name)


class TestSpacing:
    @pytest.mark.parametrize(
        "name",
        ["상속세 및 증여세법", "상속세및증여세법", "상속세ㆍ증여세법"],
    )
    def test_spacing_does_not_change_the_verdict(self, name: str):
        assert is_tax_law(name)


class TestLocalTax:
    """지방세도 담는다. 사장님에게는 국세와 같은 고지서다."""

    @pytest.mark.parametrize(
        "name",
        [
            "지방세법 일부개정법률안",
            "지방세특례제한법 시행령 일부개정령안",
            "취득세 관련 지방세기본법 시행규칙",
        ],
    )
    def test_local_tax_is_kept(self, name: str):
        assert is_tax_law(name)


class TestWhyNotFilterByMinistry:
    """부처로 거르려던 계획이 왜 틀렸는지 남긴다.

    국세청·기획재정부 코드로 서버에서 거르려 했는데 둘 다 0건이었다.
    정부조직이 바뀌어 지금 세법을 내는 곳은 재정경제부다. 그리고 부처로
    걸러도 그 안에 세법이 아닌 것이 절반이다.
    """

    def test_same_ministry_mixes_tax_and_non_tax(self):
        assert is_tax_law("소득세법 일부개정법률안 입법예고")
        assert not is_tax_law("국유재산특례제한법 일부개정법률안 입법예고")
