"""검증 게이트 G1~G6 (§3.7).

이 모듈은 **순수 함수**다. DB·네트워크·시각에 의존하지 않으므로 단독으로 테스트할 수 있고,
어떤 호출 경로에서도 같은 판정을 낸다. 콘텐츠가 발송으로 가는 모든 길목에서 호출된다.

각 게이트는 통과 여부와 함께 '실패 시 처리'(Consequence)를 반환한다.
명세서 §3.7 표의 '실패 시 처리' 열이 곧 Consequence 이며, 임의로 강화·완화하지 않는다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.domain.enums import AuthorityGrade, LegalStatus, RiskLevel, SourceRole

# 날짜 필드는 근거 없이 값을 가질 수 없다 (§9.4 V2, AT-05).
DATE_FIELDS = (
    "announcement_date",
    "promulgation_date",
    "effective_date",
    "application_start",
    "application_end",
)


class Consequence(StrEnum):
    """게이트 실패가 실제로 무엇을 막는가 (§3.7 '실패 시 처리' 열)."""

    BLOCK_APPROVAL = "BLOCK_APPROVAL"
    """승인 자체를 금지. 미검증 큐에 남는다."""

    BLOCK_SCHEDULE = "BLOCK_SCHEDULE"
    """발송 스케줄 생성 금지."""

    BLOCK_PERSONALIZED_DELIVERY = "BLOCK_PERSONALIZED_DELIVERY"
    """개인화 대상 선정에서 제외. 일반 발송은 가능."""

    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    """전문가 승인을 필수로 만든다."""

    NULLIFY_DATES = "NULLIFY_DATES"
    """근거 없는 날짜 필드를 null 로 되돌리고 검수를 요구한다."""

    WARN = "WARN"
    """표시 경고만. 진행은 막지 않는다."""


@dataclass(frozen=True)
class SourceLink:
    """콘텐츠에 연결된 원문 버전 하나 (content_sources 한 행)."""

    source_version_id: UUID
    authority: AuthorityGrade
    role: SourceRole
    source_id: UUID
    """독립성 판정용. 같은 출처의 두 게시물은 '독립 근거 2개'가 아니다."""


@dataclass(frozen=True)
class EvidenceRef:
    """필드 하나를 뒷받침하는 근거 위치 (content_evidence 한 행)."""

    field_name: str
    source_version_id: UUID
    locator: str


@dataclass(frozen=True)
class GateContext:
    """게이트 판정에 필요한 콘텐츠 스냅샷 전부."""

    sources: tuple[SourceLink, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    legal_status: LegalStatus = LegalStatus.UNKNOWN
    risk_level: RiskLevel = RiskLevel.MEDIUM
    dates: dict[str, dt.date | None] = field(default_factory=dict)
    affected_users: tuple[str, ...] = ()
    excluded_users: tuple[str, ...] = ()
    has_transition_measures: bool = False
    approved_by_reviewer: bool = False
    """REVIEWER 역할이 승인했는가. 다른 역할의 승인은 여기 반영하지 않는다 (§12.2)."""

    # ---- 파생 조회 ----

    def evidence_fields(self) -> frozenset[str]:
        return frozenset(e.field_name for e in self.evidence)

    def official_sources(self) -> tuple[SourceLink, ...]:
        return tuple(s for s in self.sources if s.authority.is_official)

    def grade_a_sources(self) -> tuple[SourceLink, ...]:
        return tuple(s for s in self.sources if s.authority is AuthorityGrade.A)

    def independent_official_count(self) -> int:
        """서로 다른 출처에서 온 공식 근거의 개수 (§3.7 G5 '2개 이상 독립 근거')."""
        return len({s.source_id for s in self.official_sources()})

    def evidence_grade_for(self, field_name: str) -> frozenset[AuthorityGrade]:
        """해당 필드를 뒷받침하는 근거들의 출처 등급 집합."""
        by_version = {s.source_version_id: s.authority for s in self.sources}
        return frozenset(
            by_version[e.source_version_id]
            for e in self.evidence
            if e.field_name == field_name and e.source_version_id in by_version
        )


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    consequence: Consequence | None
    reason: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GateReport:
    results: tuple[GateResult, ...]

    @property
    def failures(self) -> tuple[GateResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    def _has(self, consequence: Consequence) -> bool:
        return any(r.consequence is consequence for r in self.failures)

    @property
    def can_approve(self) -> bool:
        """승인 가능한가. G1 실패 시 뉴스 단독 콘텐츠가 여기서 차단된다 (AT-03)."""
        return not self._has(Consequence.BLOCK_APPROVAL)

    @property
    def can_schedule(self) -> bool:
        """캠페인에 포함할 수 있는가 (AT-06)."""
        return self.can_approve and not self._has(Consequence.BLOCK_SCHEDULE)

    @property
    def can_personalize(self) -> bool:
        return not self._has(Consequence.BLOCK_PERSONALIZED_DELIVERY)

    @property
    def requires_review(self) -> bool:
        return self._has(Consequence.REQUIRE_REVIEW)

    @property
    def dates_to_nullify(self) -> tuple[str, ...]:
        out: list[str] = []
        for r in self.failures:
            if r.consequence is Consequence.NULLIFY_DATES:
                out.extend(str(f) for f in r.details.get("fields", ()))
        return tuple(out)

    def failed_gate_ids(self) -> tuple[str, ...]:
        return tuple(r.gate for r in self.failures)

    def as_dict(self) -> dict[str, object]:
        """API 응답·감사로그에 넣을 직렬화 형태."""
        return {
            "can_approve": self.can_approve,
            "can_schedule": self.can_schedule,
            "can_personalize": self.can_personalize,
            "requires_review": self.requires_review,
            "results": [
                {
                    "gate": r.gate,
                    "passed": r.passed,
                    "consequence": r.consequence.value if r.consequence else None,
                    "reason": r.reason,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


# --------------------------------------------------------------------------
# 개별 게이트
# --------------------------------------------------------------------------


def gate_g1_authenticity(ctx: GateContext) -> GateResult:
    """G1 원문성 — 공식 URL 또는 공식 첨부파일이 확인되었는가.

    실패 시: 미검증 큐 유지, 발송 금지.
    C/D 등급(전문언론·일반뉴스)만 연결된 콘텐츠는 여기서 승인이 막힌다 (AT-03).
    """
    official = ctx.official_sources()
    if official:
        return GateResult("G1", True, None, "공식 근거(A/B등급) 연결 확인")

    grades = sorted({s.authority.value for s in ctx.sources})
    return GateResult(
        "G1",
        False,
        Consequence.BLOCK_APPROVAL,
        (
            "공식 근거(A/B등급)가 연결되지 않았습니다. "
            "뉴스·해설 단독으로는 승인·발송할 수 없습니다."
        ),
        {"connected_grades": grades, "source_count": len(ctx.sources)},
    )


def gate_g2_status(ctx: GateContext) -> GateResult:
    """G2 상태성 — 정책 법적 상태와 그 기준일이 확인되었는가.

    실패 시: '상태 확인 필요' 표시. 진행을 막지는 않는다.
    """
    if ctx.legal_status is LegalStatus.UNKNOWN:
        return GateResult(
            "G2",
            False,
            Consequence.WARN,
            "정책 법적 상태가 확인되지 않았습니다. '상태 확인 필요'로 표시합니다.",
            {"legal_status": ctx.legal_status.value},
        )

    if "legal_status" not in ctx.evidence_fields():
        return GateResult(
            "G2",
            False,
            Consequence.WARN,
            f"법적 상태 '{ctx.legal_status.value}'의 근거가 연결되지 않았습니다.",
            {"legal_status": ctx.legal_status.value},
        )

    return GateResult("G2", True, None, "법적 상태와 근거 확인")


def gate_g3_dates(ctx: GateContext) -> GateResult:
    """G3 날짜성 — 발표일·시행일·마감일이 구분되고 각각 근거가 있는가.

    실패 시: 근거 없는 날짜 필드를 null 로 되돌리고 검수를 필수화한다.
    AI가 원문에 없는 날짜를 만들어내도 여기서 지워진다 (§9.4 V2, AT-05).
    """
    have_evidence = ctx.evidence_fields()
    ungrounded = [
        name
        for name in DATE_FIELDS
        if ctx.dates.get(name) is not None and name not in have_evidence
    ]
    if ungrounded:
        return GateResult(
            "G3",
            False,
            Consequence.NULLIFY_DATES,
            "원문 근거가 없는 날짜 값이 있습니다. 해당 필드를 null 로 되돌리고 검수가 필요합니다.",
            {"fields": tuple(ungrounded)},
        )
    return GateResult("G3", True, None, "날짜 필드 근거 확인")


def gate_g4_applicability(ctx: GateContext) -> GateResult:
    """G4 적용성 — 대상·제외·경과조치의 근거를 확보했는가.

    실패 시: 개인화 발송에서 제외. 누구에게 해당하는지 모르는 콘텐츠를
    '내게 해당된다'며 보내지 않기 위한 게이트다.
    """
    have_evidence = ctx.evidence_fields()
    missing: list[str] = []

    if not ctx.affected_users:
        missing.append("affected_users:empty")
    elif "affected_users" not in have_evidence:
        missing.append("affected_users:no_evidence")

    if ctx.excluded_users and "excluded_users" not in have_evidence:
        missing.append("excluded_users:no_evidence")

    if ctx.has_transition_measures and "transition_measures" not in have_evidence:
        missing.append("transition_measures:no_evidence")

    if missing:
        return GateResult(
            "G4",
            False,
            Consequence.BLOCK_PERSONALIZED_DELIVERY,
            "적용대상·제외대상·경과조치의 근거가 부족하여 개인화 발송에서 제외합니다.",
            {"missing": tuple(missing)},
        )
    return GateResult("G4", True, None, "적용대상 근거 확인")


def gate_g5_cross_check(ctx: GateContext) -> GateResult:
    """G5 교차검증 — 중요 콘텐츠는 독립 근거 2개 이상 또는 A등급 1개.

    실패 시: 전문가 승인 필수.
    단, PROMULGATED/EFFECTIVE 주장은 A등급 근거가 없으면 승인 자체를 막는다 (§9.4 V3).
    공포·시행 여부는 관보·법령 원문으로만 확정할 수 있기 때문이다.
    """
    grade_a = ctx.grade_a_sources()
    independent = ctx.independent_official_count()

    if ctx.legal_status.requires_grade_a_evidence:
        status_grades = ctx.evidence_grade_for("legal_status")
        if not grade_a or AuthorityGrade.A not in status_grades:
            return GateResult(
                "G5",
                False,
                Consequence.BLOCK_APPROVAL,
                (
                    f"'{ctx.legal_status.value}' 상태는 A등급(법령·관보·의안 원문) 근거가 "
                    "연결되고 그 근거가 상태를 직접 뒷받침해야 주장할 수 있습니다."
                ),
                {
                    "legal_status": ctx.legal_status.value,
                    "grade_a_sources": len(grade_a),
                    "legal_status_evidence_grades": sorted(g.value for g in status_grades),
                },
            )

    is_important = ctx.risk_level.requires_expert_approval
    if is_important and not grade_a and independent < 2:
        return GateResult(
            "G5",
            False,
            Consequence.REQUIRE_REVIEW,
            (
                "중요 콘텐츠는 독립 공식 근거 2개 이상 또는 A등급 1개가 필요합니다. "
                "전문가 승인이 필수입니다."
            ),
            {"independent_official_sources": independent, "grade_a_sources": len(grade_a)},
        )

    return GateResult("G5", True, None, "교차검증 조건 충족")


def gate_g6_expert_approval(ctx: GateContext) -> GateResult:
    """G6 전문가 승인 — 고위험 항목의 승인이 완료되었는가.

    실패 시: 발송 스케줄 생성 금지 (AT-06).
    CAMPAIGN_MANAGER 는 이 게이트를 우회할 수 없다 (§12.2).
    """
    if not ctx.risk_level.requires_expert_approval:
        return GateResult("G6", True, None, "고위험 항목이 아니므로 전문가 승인 요건 없음")

    if ctx.approved_by_reviewer:
        return GateResult("G6", True, None, "전문가(REVIEWER) 승인 완료")

    return GateResult(
        "G6",
        False,
        Consequence.BLOCK_SCHEDULE,
        (
            f"위험도 {ctx.risk_level.value} 콘텐츠는 전문가(REVIEWER) 승인 없이 "
            "캠페인에 포함할 수 없습니다."
        ),
        {"risk_level": ctx.risk_level.value},
    )


ALL_GATES = (
    gate_g1_authenticity,
    gate_g2_status,
    gate_g3_dates,
    gate_g4_applicability,
    gate_g5_cross_check,
    gate_g6_expert_approval,
)


def evaluate(ctx: GateContext) -> GateReport:
    """G1~G6 전체를 평가한다. 조기 반환하지 않고 모든 실패를 모아서 돌려준다.

    운영자가 한 번에 무엇을 고쳐야 하는지 알아야 하기 때문이다.
    """
    return GateReport(tuple(gate(ctx) for gate in ALL_GATES))
