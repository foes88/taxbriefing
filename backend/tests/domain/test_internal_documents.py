"""기관 내부 문서 판정. 네트워크·AI 없이 실행된다."""

from __future__ import annotations

import pytest

from app.domain.industry import is_internal_document

INTERNAL = [
    "재정경제부 고문변호사 운영규정 (훈령)",
    "국세청 체납관리단 기간제 근로자 인사관리규정 (훈령)",
    "재정경제부 국제기구 초급전문가·중견전문가·인턴 파견 및 관리 규정 (예규)",
    "재정경제부 갈등관리 운영지침 (훈령)",
    "산업통상부와 그 소속기관의 회계관계 공무원지정 및 재정보증 등에 관한 규정",
    "공무원 국외출장 지침 (훈령)",
]

BUSINESS = [
    "부가가치세법 시행령 (일부개정)",
    "국민건강보험법 시행규칙 (일부개정)",
    "조세특례제한법 (일부개정)",
    "국세청 사무처리규정 (훈령)",
    "소득세법 (일부개정)",
    "고용보험 및 산업재해보상보험의 보험료징수 등에 관한 법률 시행령",
]


@pytest.mark.parametrize("title", INTERNAL)
def test_internal_titles_are_hidden(title: str):
    assert is_internal_document(title) is True


@pytest.mark.parametrize("title", BUSINESS)
def test_business_titles_are_kept(title: str):
    """사장님과 관련된 것을 실수로 숨기면, 숨겨졌다는 사실조차 아무도 모른다."""
    assert is_internal_document(title) is False
