"""검증 게이트 G1~G6 단위 테스트 (§3.7). DB 없이 실행된다."""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import pytest

from app.domain.enums import AuthorityGrade, LegalStatus, RiskLevel, SourceRole
from app.domain.gates import (
    Consequence,
    EvidenceRef,
    GateContext,
    SourceLink,
    evaluate,
    gate_g1_authenticity,
    gate_g2_status,
    gate_g3_dates,
    gate_g4_applicability,
    gate_g5_cross_check,
    gate_g6_expert_approval,
)


def link(authority: AuthorityGrade, *, source_id=None, version_id=None) -> SourceLink:
    return SourceLink(
        source_version_id=version_id or uuid4(),
        authority=authority,
        role=SourceRole.PRIMARY,
        source_id=source_id or uuid4(),
    )


def ev(field: str, version_id) -> EvidenceRef:
    return EvidenceRef(field_name=field, source_version_id=version_id, locator="p1")


class TestG1Authenticity:
    def test_passes_with_grade_a(self):
        ctx = GateContext(sources=(link(AuthorityGrade.A),))
        assert gate_g1_authenticity(ctx).passed

    def test_passes_with_grade_b(self):
        ctx = GateContext(sources=(link(AuthorityGrade.B),))
        assert gate_g1_authenticity(ctx).passed

    @pytest.mark.parametrize("grade", [AuthorityGrade.C, AuthorityGrade.D])
    def test_blocks_approval_for_news_only(self, grade):
        """AT-03: 뉴스·해설만 연결된 콘텐츠는 승인할 수 없다."""
        result = gate_g1_authenticity(GateContext(sources=(link(grade),)))
        assert not result.passed
        assert result.consequence is Consequence.BLOCK_APPROVAL

    def test_blocks_when_no_sources(self):
        result = gate_g1_authenticity(GateContext())
        assert not result.passed
        assert result.consequence is Consequence.BLOCK_APPROVAL

    def test_mixed_grades_pass_if_one_official(self):
        ctx = GateContext(
            sources=(link(AuthorityGrade.D), link(AuthorityGrade.C), link(AuthorityGrade.B))
        )
        assert gate_g1_authenticity(ctx).passed


class TestG2Status:
    def test_unknown_status_warns_only(self):
        result = gate_g2_status(GateContext(legal_status=LegalStatus.UNKNOWN))
        assert not result.passed
        assert result.consequence is Consequence.WARN

    def test_status_without_evidence_warns(self):
        result = gate_g2_status(GateContext(legal_status=LegalStatus.PREANNOUNCED))
        assert not result.passed
        assert result.consequence is Consequence.WARN

    def test_status_with_evidence_passes(self):
        vid = uuid4()
        ctx = GateContext(
            legal_status=LegalStatus.PREANNOUNCED, evidence=(ev("legal_status", vid),)
        )
        assert gate_g2_status(ctx).passed


class TestG3Dates:
    def test_ungrounded_date_is_nullified(self):
        """AT-05 의 DB 측 대응: 근거 없는 날짜는 지워진다."""
        ctx = GateContext(dates={"effective_date": dt.date(2027, 1, 1)})
        result = gate_g3_dates(ctx)
        assert not result.passed
        assert result.consequence is Consequence.NULLIFY_DATES
        assert result.details["fields"] == ("effective_date",)

    def test_grounded_date_passes(self):
        vid = uuid4()
        ctx = GateContext(
            dates={"effective_date": dt.date(2027, 1, 1)},
            evidence=(ev("effective_date", vid),),
        )
        assert gate_g3_dates(ctx).passed

    def test_null_dates_always_pass(self):
        ctx = GateContext(dates={"effective_date": None, "promulgation_date": None})
        assert gate_g3_dates(ctx).passed

    def test_reports_every_ungrounded_date(self):
        ctx = GateContext(
            dates={
                "effective_date": dt.date(2027, 1, 1),
                "promulgation_date": dt.date(2026, 12, 1),
                "application_end": dt.date(2027, 3, 1),
            }
        )
        fields = gate_g3_dates(ctx).details["fields"]
        assert set(fields) == {"effective_date", "promulgation_date", "application_end"}


class TestG4Applicability:
    def test_empty_affected_users_blocks_personalization(self):
        result = gate_g4_applicability(GateContext())
        assert not result.passed
        assert result.consequence is Consequence.BLOCK_PERSONALIZED_DELIVERY

    def test_affected_users_without_evidence_blocks(self):
        ctx = GateContext(affected_users=("개인사업자",))
        assert not gate_g4_applicability(ctx).passed

    def test_grounded_affected_users_pass(self):
        vid = uuid4()
        ctx = GateContext(
            affected_users=("개인사업자",), evidence=(ev("affected_users", vid),)
        )
        assert gate_g4_applicability(ctx).passed

    def test_excluded_users_need_evidence_too(self):
        vid = uuid4()
        ctx = GateContext(
            affected_users=("개인사업자",),
            excluded_users=("법인",),
            evidence=(ev("affected_users", vid),),
        )
        result = gate_g4_applicability(ctx)
        assert not result.passed
        assert "excluded_users:no_evidence" in result.details["missing"]


class TestG5CrossCheck:
    def test_effective_without_grade_a_blocks_approval(self):
        """§9.4 V3: 시행 주장은 A등급 근거가 있어야 한다."""
        vid = uuid4()
        ctx = GateContext(
            sources=(link(AuthorityGrade.B, version_id=vid),),
            evidence=(ev("legal_status", vid),),
            legal_status=LegalStatus.EFFECTIVE,
        )
        result = gate_g5_cross_check(ctx)
        assert not result.passed
        assert result.consequence is Consequence.BLOCK_APPROVAL

    def test_effective_with_grade_a_evidence_passes(self):
        vid = uuid4()
        ctx = GateContext(
            sources=(link(AuthorityGrade.A, version_id=vid),),
            evidence=(ev("legal_status", vid),),
            legal_status=LegalStatus.EFFECTIVE,
        )
        assert gate_g5_cross_check(ctx).passed

    def test_grade_a_source_but_evidence_from_grade_b_blocks(self):
        """A등급 원문이 붙어 있어도, 상태를 뒷받침하는 근거가 B등급이면 통과하지 못한다."""
        a_vid, b_vid = uuid4(), uuid4()
        ctx = GateContext(
            sources=(
                link(AuthorityGrade.A, version_id=a_vid),
                link(AuthorityGrade.B, version_id=b_vid),
            ),
            evidence=(ev("legal_status", b_vid),),
            legal_status=LegalStatus.PROMULGATED,
        )
        assert not gate_g5_cross_check(ctx).passed

    def test_high_risk_single_b_source_requires_review(self):
        ctx = GateContext(
            sources=(link(AuthorityGrade.B),),
            legal_status=LegalStatus.PREANNOUNCED,
            risk_level=RiskLevel.HIGH,
        )
        result = gate_g5_cross_check(ctx)
        assert not result.passed
        assert result.consequence is Consequence.REQUIRE_REVIEW

    def test_two_independent_official_sources_pass(self):
        ctx = GateContext(
            sources=(link(AuthorityGrade.B), link(AuthorityGrade.B)),
            legal_status=LegalStatus.PREANNOUNCED,
            risk_level=RiskLevel.HIGH,
        )
        assert gate_g5_cross_check(ctx).passed

    def test_same_source_twice_is_not_independent(self):
        """같은 기관의 게시물 2건은 '독립 근거 2개'가 아니다."""
        same = uuid4()
        ctx = GateContext(
            sources=(
                link(AuthorityGrade.B, source_id=same),
                link(AuthorityGrade.B, source_id=same),
            ),
            legal_status=LegalStatus.PREANNOUNCED,
            risk_level=RiskLevel.HIGH,
        )
        assert not gate_g5_cross_check(ctx).passed


class TestG6ExpertApproval:
    @pytest.mark.parametrize("risk", [RiskLevel.LOW, RiskLevel.MEDIUM])
    def test_low_risk_needs_no_approval(self, risk):
        assert gate_g6_expert_approval(GateContext(risk_level=risk)).passed

    @pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.CRITICAL])
    def test_high_risk_blocks_schedule_without_approval(self, risk):
        """AT-06: HIGH 위험도는 REVIEWER 승인 없이 캠페인에 포함될 수 없다."""
        result = gate_g6_expert_approval(GateContext(risk_level=risk))
        assert not result.passed
        assert result.consequence is Consequence.BLOCK_SCHEDULE

    def test_high_risk_with_approval_passes(self):
        ctx = GateContext(risk_level=RiskLevel.HIGH, approved_by_reviewer=True)
        assert gate_g6_expert_approval(ctx).passed


class TestGateReport:
    def test_collects_all_failures_not_just_first(self):
        """운영자가 한 번에 전부 고칠 수 있어야 한다."""
        report = evaluate(GateContext(sources=(link(AuthorityGrade.D),)))
        failed = set(report.failed_gate_ids())
        assert {"G1", "G2", "G4"}.issubset(failed)

    def test_news_only_content_cannot_be_approved(self):
        report = evaluate(GateContext(sources=(link(AuthorityGrade.D),)))
        assert not report.can_approve
        assert not report.can_schedule

    def test_fully_grounded_content_passes_everything(self):
        vid = uuid4()
        ctx = GateContext(
            sources=(link(AuthorityGrade.A, version_id=vid),),
            evidence=(
                ev("legal_status", vid),
                ev("effective_date", vid),
                ev("affected_users", vid),
            ),
            legal_status=LegalStatus.EFFECTIVE,
            risk_level=RiskLevel.MEDIUM,
            dates={"effective_date": dt.date(2027, 1, 1)},
            affected_users=("affected_users",),
        )
        report = evaluate(ctx)
        assert report.failures == ()
        assert report.can_approve and report.can_schedule and report.can_personalize

    def test_as_dict_is_serializable(self):
        import json

        report = evaluate(GateContext(sources=(link(AuthorityGrade.D),)))
        assert json.dumps(report.as_dict(), default=str)
