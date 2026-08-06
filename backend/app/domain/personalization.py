"""규칙 기반 개인화 매칭 (§11.1, §11.2).

순수 함수. 매칭 이유를 항상 함께 반환한다 (FR-PER-002 '매칭 이유 표시',
§NFR-010 설명가능성). 사용자에게 "내게 해당되는 이유"를 보여주려면
점수가 아니라 이유가 필요하다.

**하드 제외가 점수보다 먼저다.** 명시적 제외 대상과 수신철회는
가중치 합이 아무리 커도 대상에 포함되지 않는다 (AT-08, AT-10).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

# §11.2 가중치 초기값. 운영 데이터로 조정한다.
W_DIRECT_TARGET = 40
W_TOPIC = 20
W_INDUSTRY = 15
W_REGION = 15
W_DEADLINE_SOON = 20
W_USER_INTEREST = 5
W_NOT_INTERESTED = -20

DEADLINE_SOON_DAYS = 7
REGION_NATIONWIDE = "ALL"


class ExclusionReason(StrEnum):
    """대상에서 제거된 이유. campaign_recipients.excluded_reason 에 저장한다."""

    EXPLICITLY_EXCLUDED = "EXPLICITLY_EXCLUDED"
    """콘텐츠가 명시한 제외 대상에 해당 (§11.2 -100, AT-08)."""

    CONSENT_REVOKED = "CONSENT_REVOKED"
    """해당 채널 수신동의가 없거나 철회됨 (§12.4, AT-10)."""

    GATE_BLOCKED = "GATE_BLOCKED"
    """G4 적용성 실패로 개인화 발송이 금지된 콘텐츠 (§3.7)."""

    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    """관련성 점수가 임계값 미만."""


@dataclass(frozen=True)
class ContentTargeting:
    """콘텐츠 쪽 매칭 축. 운영자가 정규화한 content_tags 에서 만든다.

    AI 가 낸 자유 문자열(affected_users)은 여기 직접 들어오지 않는다 (§9.4 S-04).
    """

    business_types: frozenset[str] = frozenset()
    tax_types: frozenset[str] = frozenset()
    topics: frozenset[str] = frozenset()
    industry_codes: frozenset[str] = frozenset()
    region_codes: frozenset[str] = frozenset()
    employee_bands: frozenset[str] = frozenset()
    revenue_bands: frozenset[str] = frozenset()
    excluded_business_types: frozenset[str] = frozenset()
    excluded_industry_codes: frozenset[str] = frozenset()
    excluded_region_codes: frozenset[str] = frozenset()
    nearest_deadline: dt.date | None = None


@dataclass(frozen=True)
class UserTargeting:
    """사용자 쪽 매칭 축 (business_profiles + 행동 이력)."""

    business_type: str
    tax_type: str | None = None
    industry_codes: frozenset[str] = frozenset()
    region_codes: frozenset[str] = frozenset()
    employee_band: str | None = None
    revenue_band: str | None = None
    interest_topics: frozenset[str] = frozenset()
    saved_topics: frozenset[str] = frozenset()
    not_interested_topics: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MatchReason:
    code: str
    label: str
    points: int


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int
    reasons: tuple[MatchReason, ...] = field(default_factory=tuple)
    excluded_reason: ExclusionReason | None = None
    excluded_detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        """campaign_recipients.match_reasons 저장 형태."""
        return {
            "matched": self.matched,
            "score": self.score,
            "excluded_reason": self.excluded_reason.value if self.excluded_reason else None,
            "excluded_detail": self.excluded_detail,
            "reasons": [
                {"code": r.code, "label": r.label, "points": r.points} for r in self.reasons
            ],
        }

    def user_facing_reasons(self) -> tuple[str, ...]:
        """U-02 '내게 해당되는 이유'에 표시할 문구."""
        return tuple(r.label for r in self.reasons if r.points > 0)


def _check_hard_exclusion(
    content: ContentTargeting, user: UserTargeting
) -> tuple[ExclusionReason, str] | None:
    """명시적 제외 대상 판정. 점수 계산 이전에 수행한다 (AT-08)."""
    if user.business_type in content.excluded_business_types:
        return ExclusionReason.EXPLICITLY_EXCLUDED, f"제외 대상 사업자유형: {user.business_type}"

    industry_hit = user.industry_codes & content.excluded_industry_codes
    if industry_hit:
        return (
            ExclusionReason.EXPLICITLY_EXCLUDED,
            f"제외 대상 업종: {', '.join(sorted(industry_hit))}",
        )

    region_hit = user.region_codes & content.excluded_region_codes
    if region_hit:
        return (
            ExclusionReason.EXPLICITLY_EXCLUDED,
            f"제외 대상 지역: {', '.join(sorted(region_hit))}",
        )

    return None


def match(
    content: ContentTargeting,
    user: UserTargeting,
    *,
    today: dt.date,
    has_channel_consent: bool = True,
    content_allows_personalization: bool = True,
    threshold: int = 20,
) -> MatchResult:
    """콘텐츠-사용자 관련성을 판정한다.

    판정 순서가 중요하다.
      1. 수신동의 (§12.4 — 발송 실행 시점에 재확인)
      2. 게이트 G4 (§3.7 — 적용대상 근거 없는 콘텐츠는 개인화 금지)
      3. 명시적 제외 (§11.2 -100 → 하드 제외)
      4. 점수 계산
    앞 세 단계는 점수와 무관하게 대상에서 제거한다.
    """
    if not has_channel_consent:
        return MatchResult(
            False, 0, excluded_reason=ExclusionReason.CONSENT_REVOKED,
            excluded_detail="해당 채널 수신동의가 없거나 철회되었습니다.",
        )

    if not content_allows_personalization:
        return MatchResult(
            False, 0, excluded_reason=ExclusionReason.GATE_BLOCKED,
            excluded_detail="G4 적용성 게이트 실패로 개인화 발송이 금지된 콘텐츠입니다.",
        )

    hard = _check_hard_exclusion(content, user)
    if hard is not None:
        reason, detail = hard
        return MatchResult(False, 0, excluded_reason=reason, excluded_detail=detail)

    reasons: list[MatchReason] = []

    if content.business_types and user.business_type in content.business_types:
        reasons.append(
            MatchReason("DIRECT_TARGET", f"{user.business_type}에 직접 해당", W_DIRECT_TARGET)
        )
    if content.tax_types and user.tax_type and user.tax_type in content.tax_types:
        reasons.append(MatchReason("TAX_TYPE", f"{user.tax_type} 대상", W_DIRECT_TARGET))

    topic_hit = content.topics & (user.interest_topics | user.saved_topics)
    if topic_hit:
        reasons.append(
            MatchReason("TOPIC", f"관심 주제 일치: {', '.join(sorted(topic_hit))}", W_TOPIC)
        )

    industry_hit = content.industry_codes & user.industry_codes
    if industry_hit:
        reasons.append(
            MatchReason("INDUSTRY", f"업종 일치: {', '.join(sorted(industry_hit))}", W_INDUSTRY)
        )

    if REGION_NATIONWIDE in content.region_codes:
        reasons.append(MatchReason("REGION", "전국 대상", W_REGION))
    else:
        region_hit = content.region_codes & user.region_codes
        if region_hit:
            reasons.append(
                MatchReason("REGION", f"지역 일치: {', '.join(sorted(region_hit))}", W_REGION)
            )

    if content.employee_bands and user.employee_band in content.employee_bands:
        reasons.append(MatchReason("EMPLOYEE_BAND", f"직원수 구간 일치: {user.employee_band}", 0))
    if content.revenue_bands and user.revenue_band in content.revenue_bands:
        reasons.append(MatchReason("REVENUE_BAND", f"매출 구간 일치: {user.revenue_band}", 0))

    if content.nearest_deadline is not None:
        days_left = (content.nearest_deadline - today).days
        if 0 <= days_left <= DEADLINE_SOON_DAYS:
            reasons.append(
                MatchReason("DEADLINE_SOON", f"마감 D-{days_left}", W_DEADLINE_SOON)
            )

    if content.topics & user.saved_topics:
        reasons.append(MatchReason("USER_INTEREST", "저장한 주제", W_USER_INTEREST))

    not_interested_hit = content.topics & user.not_interested_topics
    if not_interested_hit:
        reasons.append(
            MatchReason(
                "NOT_INTERESTED",
                f"관심없음 표시: {', '.join(sorted(not_interested_hit))}",
                W_NOT_INTERESTED,
            )
        )

    total = sum(r.points for r in reasons)
    matched = total >= threshold

    return MatchResult(
        matched=matched,
        score=total,
        reasons=tuple(reasons),
        excluded_reason=None if matched else ExclusionReason.BELOW_THRESHOLD,
        excluded_detail=None if matched else f"관련성 점수 {total} < 임계값 {threshold}",
    )


def rank(results: list[tuple[object, MatchResult]]) -> list[tuple[object, MatchResult]]:
    """매칭된 항목을 점수 내림차순으로 정렬한다 (FR-PER-003)."""
    return sorted(
        (item for item in results if item[1].matched),
        key=lambda item: item[1].score,
        reverse=True,
    )
