"""신뢰도 점수 산정 (§3.8).

**이 점수는 사실의 확률이 아니다.** 내부 처리 우선순위와 발송 제한을 위한
워크플로 점수이며, 점수만으로 자동 확정하지 않는다. 게이트 G1~G6 이 확정을 담당한다.

산정 내역을 함께 반환한다 (§NFR-010 설명가능성, FR-VER-005 '점수 내역 조회').
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.domain.enums import AuthorityGrade, LegalStatus
from app.domain.gates import GateContext

# §3.8 배점표. 값은 명세서의 '예시'이며 운영 데이터로 조정한다.
_AUTHORITY_POINTS: dict[AuthorityGrade, int] = {
    AuthorityGrade.A: 40,
    AuthorityGrade.B: 30,
    AuthorityGrade.C: 15,
    AuthorityGrade.D: 5,
}

# "공포·시행 25, 예고 15, 논의 5" — 명세서가 값을 준 세 구간만 사용하고
# 나머지 상태는 가장 가까운 구간에 배정한다. 새 값을 발명하지 않는다.
_STATUS_POINTS: dict[LegalStatus, int] = {
    LegalStatus.PROMULGATED: 25,
    LegalStatus.EFFECTIVE: 25,
    LegalStatus.SUSPENDED: 25,
    LegalStatus.ABOLISHED: 25,
    LegalStatus.ASSEMBLY_PASSED: 15,
    LegalStatus.PREANNOUNCED: 15,
    LegalStatus.GOV_ANNOUNCED: 15,
    LegalStatus.BILL_PROPOSED: 15,
    LegalStatus.DISCUSSION: 5,
    LegalStatus.UNKNOWN: 0,
}

MAX_AUTHORITY = 40
MAX_STATUS = 25
MAX_CROSS_CHECK = 20
MAX_RECENCY = 10
MAX_REVIEW = 5
MAX_TOTAL = MAX_AUTHORITY + MAX_STATUS + MAX_CROSS_CHECK + MAX_RECENCY + MAX_REVIEW  # 100


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    label: str
    points: int
    max_points: int
    explanation: str


@dataclass(frozen=True)
class ConfidenceScore:
    total: int
    components: tuple[ScoreComponent, ...] = field(default_factory=tuple)
    manual_adjustment: int = 0
    manual_adjustment_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        """tax_contents.confidence_breakdown 에 저장할 형태 (§7.4 D-08)."""
        return {
            "total": self.total,
            "max_total": MAX_TOTAL,
            "manual_adjustment": self.manual_adjustment,
            "manual_adjustment_reason": self.manual_adjustment_reason,
            "components": [
                {
                    "key": c.key,
                    "label": c.label,
                    "points": c.points,
                    "max_points": c.max_points,
                    "explanation": c.explanation,
                }
                for c in self.components
            ],
        }


def _authority_component(ctx: GateContext) -> ScoreComponent:
    if not ctx.sources:
        return ScoreComponent(
            "authority", "출처 권위", 0, MAX_AUTHORITY, "연결된 원문이 없습니다."
        )
    best = max(ctx.sources, key=lambda s: _AUTHORITY_POINTS[s.authority])
    points = _AUTHORITY_POINTS[best.authority]
    return ScoreComponent(
        "authority",
        "출처 권위",
        points,
        MAX_AUTHORITY,
        f"최고 등급 근거 {best.authority.value}등급 ({points}점)",
    )


def _status_component(ctx: GateContext) -> ScoreComponent:
    points = _STATUS_POINTS[ctx.legal_status]
    return ScoreComponent(
        "status_clarity",
        "정책상태 명확성",
        points,
        MAX_STATUS,
        f"법적 상태 {ctx.legal_status.value} ({points}점)",
    )


def _cross_check_component(ctx: GateContext) -> ScoreComponent:
    independent = ctx.independent_official_count()
    if independent >= 2:
        points, note = MAX_CROSS_CHECK, f"독립 공식 근거 {independent}개"
    elif independent == 1:
        # 명세서는 '2개 이상 20'만 규정한다. 1개는 절반으로 두어
        # 0 과 20 사이의 절벽을 없애되, 만점은 주지 않는다.
        points, note = MAX_CROSS_CHECK // 2, "독립 공식 근거 1개 (교차검증 미완)"
    else:
        points, note = 0, "공식 근거 없음"
    return ScoreComponent("cross_check", "교차검증", points, MAX_CROSS_CHECK, note)


def _recency_component(
    last_checked_at: dt.datetime | None, now: dt.datetime, content_changed: bool
) -> ScoreComponent:
    if last_checked_at is None:
        return ScoreComponent("recency", "최신성·버전", 0, MAX_RECENCY, "재확인 이력이 없습니다.")
    if content_changed:
        return ScoreComponent(
            "recency", "최신성·버전", 0, MAX_RECENCY, "최근 재확인에서 원문 변경이 감지되었습니다."
        )
    age_days = (now - last_checked_at).total_seconds() / 86400
    if age_days <= 7:
        return ScoreComponent(
            "recency", "최신성·버전", MAX_RECENCY, MAX_RECENCY, "7일 이내 재확인, 변경 없음"
        )
    if age_days <= 30:
        return ScoreComponent(
            "recency", "최신성·버전", MAX_RECENCY // 2, MAX_RECENCY, "30일 이내 재확인, 변경 없음"
        )
    return ScoreComponent(
        "recency", "최신성·버전", 0, MAX_RECENCY, f"마지막 재확인 후 {int(age_days)}일 경과"
    )


def _review_component(ctx: GateContext) -> ScoreComponent:
    points = MAX_REVIEW if ctx.approved_by_reviewer else 0
    note = "전문가 승인 완료" if ctx.approved_by_reviewer else "전문가 승인 전"
    return ScoreComponent("expert_review", "전문가 검수", points, MAX_REVIEW, note)


def score(
    ctx: GateContext,
    *,
    now: dt.datetime,
    last_checked_at: dt.datetime | None = None,
    content_changed: bool = False,
    manual_adjustment: int = 0,
    manual_adjustment_reason: str | None = None,
) -> ConfidenceScore:
    """0~100 워크플로 점수를 산정한다.

    `now` 를 주입받는 이유는 이 함수를 순수하게 유지해 테스트에서 시간을 고정하기 위해서다.
    수동 조정은 사유 없이 적용되지 않는다 (FR-VER-005).
    """
    if manual_adjustment and not manual_adjustment_reason:
        raise ValueError("수동 조정에는 사유가 필요합니다 (FR-VER-005).")

    components = (
        _authority_component(ctx),
        _status_component(ctx),
        _cross_check_component(ctx),
        _recency_component(last_checked_at, now, content_changed),
        _review_component(ctx),
    )
    raw = sum(c.points for c in components) + manual_adjustment
    total = max(0, min(MAX_TOTAL, raw))

    return ConfidenceScore(
        total=total,
        components=components,
        manual_adjustment=manual_adjustment,
        manual_adjustment_reason=manual_adjustment_reason,
    )
