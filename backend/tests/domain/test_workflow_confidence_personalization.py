"""워크플로 전이·신뢰도·개인화 단위 테스트. DB 없이 실행된다."""

from __future__ import annotations

import datetime as dt
import itertools
from uuid import uuid4

import pytest

from app.domain.confidence import MAX_TOTAL, score
from app.domain.enums import (
    AuthorityGrade,
    LegalStatus,
    ReviewDecision,
    SourceRole,
    WorkflowStatus,
)
from app.domain.gates import GateContext, SourceLink
from app.domain.personalization import (
    ContentTargeting,
    ExclusionReason,
    UserTargeting,
    match,
    rank,
)
from app.domain.workflow import (
    PROTECTED_FIELDS,
    apply_edit,
    can_transition,
    status_after_review,
)

NOW = dt.datetime(2026, 8, 6, tzinfo=dt.UTC)
TODAY = NOW.date()


def link(authority: AuthorityGrade, source_id=None) -> SourceLink:
    return SourceLink(uuid4(), authority, SourceRole.PRIMARY, source_id or uuid4())


class TestWorkflowTransitions:
    def test_forward_path_is_allowed(self):
        path = [
            WorkflowStatus.DETECTED,
            WorkflowStatus.UNVERIFIED,
            WorkflowStatus.SOURCE_CONFIRMED,
            WorkflowStatus.ANALYZED,
            WorkflowStatus.REVIEW_PENDING,
            WorkflowStatus.APPROVED,
            WorkflowStatus.SCHEDULED,
            WorkflowStatus.PUBLISHED,
            WorkflowStatus.MONITORING,
        ]
        for current, target in itertools.pairwise(path):
            assert can_transition(current, target), f"{current} -> {target}"

    def test_cannot_skip_review(self):
        assert not can_transition(WorkflowStatus.ANALYZED, WorkflowStatus.APPROVED)
        assert not can_transition(WorkflowStatus.SOURCE_CONFIRMED, WorkflowStatus.PUBLISHED)

    def test_archived_is_terminal(self):
        assert not can_transition(WorkflowStatus.ARCHIVED, WorkflowStatus.DETECTED)

    def test_approval_returns_to_review(self):
        assert can_transition(WorkflowStatus.APPROVED, WorkflowStatus.REVIEW_PENDING)


class TestApprovalRevocation:
    """AT-07: 승인 후 본문 수정 시 승인상태가 해제되고 재검수 큐로 이동한다."""

    def test_protected_field_change_revokes_approval(self):
        outcome = apply_edit(
            current_status=WorkflowStatus.APPROVED,
            before={"effective_date": dt.date(2027, 1, 1)},
            patch={"effective_date": dt.date(2027, 7, 1)},
        )
        assert outcome.approval_revoked
        assert outcome.next_status is WorkflowStatus.REVIEW_PENDING
        assert outcome.protected_changed == ("effective_date",)

    def test_published_content_also_returns_to_review(self):
        outcome = apply_edit(
            current_status=WorkflowStatus.PUBLISHED,
            before={"risk_level": "MEDIUM"},
            patch={"risk_level": "HIGH"},
        )
        assert outcome.approval_revoked

    def test_same_value_does_not_revoke(self):
        """같은 값 재전송으로 승인이 풀리면 운영자가 저장을 두려워하게 된다."""
        outcome = apply_edit(
            current_status=WorkflowStatus.APPROVED,
            before={"title": "동일 제목"},
            patch={"title": "동일 제목"},
        )
        assert not outcome.approval_revoked
        assert outcome.changed_fields == ()

    def test_draft_content_is_unaffected(self):
        outcome = apply_edit(
            current_status=WorkflowStatus.ANALYZED,
            before={"title": "이전"},
            patch={"title": "이후"},
        )
        assert not outcome.approval_revoked
        assert outcome.next_status is WorkflowStatus.ANALYZED

    def test_date_string_equals_date_object(self):
        outcome = apply_edit(
            current_status=WorkflowStatus.APPROVED,
            before={"effective_date": dt.date(2027, 1, 1)},
            patch={"effective_date": "2027-01-01"},
        )
        assert not outcome.approval_revoked

    def test_all_fact_bearing_fields_are_protected(self):
        for field in ("legal_status", "risk_level", "effective_date", "title", "body"):
            assert field in PROTECTED_FIELDS

    def test_reject_returns_to_analyzed(self):
        assert (
            status_after_review(WorkflowStatus.REVIEW_PENDING, ReviewDecision.REJECT)
            is WorkflowStatus.ANALYZED
        )

    @pytest.mark.parametrize(
        "decision", [ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_EDIT]
    )
    def test_approval_moves_to_approved(self, decision):
        assert (
            status_after_review(WorkflowStatus.REVIEW_PENDING, decision)
            is WorkflowStatus.APPROVED
        )


class TestConfidenceScore:
    def test_score_is_bounded(self):
        ctx = GateContext(
            sources=(link(AuthorityGrade.A), link(AuthorityGrade.A)),
            legal_status=LegalStatus.EFFECTIVE,
            approved_by_reviewer=True,
        )
        result = score(ctx, now=NOW, last_checked_at=NOW)
        assert 0 <= result.total <= MAX_TOTAL

    def test_empty_context_scores_zero(self):
        result = score(GateContext(), now=NOW)
        assert result.total == 0

    def test_grade_a_beats_grade_d(self):
        a = score(GateContext(sources=(link(AuthorityGrade.A),)), now=NOW)
        d = score(GateContext(sources=(link(AuthorityGrade.D),)), now=NOW)
        assert a.total > d.total

    def test_breakdown_explains_every_component(self):
        result = score(GateContext(sources=(link(AuthorityGrade.A),)), now=NOW)
        keys = {c.key for c in result.components}
        assert keys == {
            "authority",
            "status_clarity",
            "cross_check",
            "recency",
            "expert_review",
        }
        assert all(c.explanation for c in result.components)

    def test_stale_check_loses_recency_points(self):
        ctx = GateContext(sources=(link(AuthorityGrade.A),))
        fresh = score(ctx, now=NOW, last_checked_at=NOW)
        stale = score(ctx, now=NOW, last_checked_at=NOW - dt.timedelta(days=90))
        assert fresh.total > stale.total

    def test_manual_adjustment_requires_reason(self):
        with pytest.raises(ValueError, match="사유"):
            score(GateContext(), now=NOW, manual_adjustment=10)

    def test_manual_adjustment_with_reason_applies(self):
        result = score(
            GateContext(sources=(link(AuthorityGrade.A),)),
            now=NOW,
            manual_adjustment=-10,
            manual_adjustment_reason="원문 재확인 필요",
        )
        assert result.manual_adjustment == -10
        assert result.as_dict()["manual_adjustment_reason"] == "원문 재확인 필요"


class TestPersonalization:
    def content(self, **kwargs) -> ContentTargeting:
        base = {
            "business_types": frozenset({"개인사업자"}),
            "topics": frozenset({"부가세"}),
            "region_codes": frozenset({"ALL"}),
        }
        base.update(kwargs)
        return ContentTargeting(**base)

    def user(self, **kwargs) -> UserTargeting:
        base = {
            "business_type": "개인사업자",
            "interest_topics": frozenset({"부가세"}),
        }
        base.update(kwargs)
        return UserTargeting(**base)

    def test_direct_match_is_included(self):
        result = match(self.content(), self.user(), today=TODAY)
        assert result.matched
        assert result.score >= 40

    def test_reasons_are_human_readable(self):
        result = match(self.content(), self.user(), today=TODAY)
        assert result.user_facing_reasons()
        assert any("개인사업자" in r for r in result.user_facing_reasons())

    def test_explicit_exclusion_beats_every_positive_signal(self):
        """AT-08: 명시적 제외 대상은 점수와 무관하게 제거된다."""
        content = self.content(
            excluded_business_types=frozenset({"개인사업자"}),
            industry_codes=frozenset({"F001"}),
            nearest_deadline=TODAY + dt.timedelta(days=1),
        )
        user = self.user(industry_codes=frozenset({"F001"}))
        result = match(content, user, today=TODAY)
        assert not result.matched
        assert result.excluded_reason is ExclusionReason.EXPLICITLY_EXCLUDED
        assert result.score == 0

    def test_excluded_industry_removes_user(self):
        content = self.content(excluded_industry_codes=frozenset({"F001"}))
        user = self.user(industry_codes=frozenset({"F001"}))
        assert not match(content, user, today=TODAY).matched

    def test_revoked_consent_removes_user(self):
        """AT-10: 수신철회 사용자는 최종 대상에서 제외된다."""
        result = match(
            self.content(), self.user(), today=TODAY, has_channel_consent=False
        )
        assert not result.matched
        assert result.excluded_reason is ExclusionReason.CONSENT_REVOKED

    def test_gate_g4_failure_blocks_personalization(self):
        result = match(
            self.content(),
            self.user(),
            today=TODAY,
            content_allows_personalization=False,
        )
        assert not result.matched
        assert result.excluded_reason is ExclusionReason.GATE_BLOCKED

    def test_deadline_within_7_days_adds_points(self):
        soon = self.content(nearest_deadline=TODAY + dt.timedelta(days=3))
        far = self.content(nearest_deadline=TODAY + dt.timedelta(days=60))
        assert match(soon, self.user(), today=TODAY).score > match(
            far, self.user(), today=TODAY
        ).score

    def test_past_deadline_adds_nothing(self):
        past = self.content(nearest_deadline=TODAY - dt.timedelta(days=1))
        none = self.content()
        assert match(past, self.user(), today=TODAY).score == match(
            none, self.user(), today=TODAY
        ).score

    def test_not_interested_reduces_score(self):
        plain = match(self.content(), self.user(), today=TODAY)
        bored = match(
            self.content(),
            self.user(not_interested_topics=frozenset({"부가세"})),
            today=TODAY,
        )
        assert bored.score < plain.score

    def test_unrelated_user_falls_below_threshold(self):
        content = ContentTargeting(
            business_types=frozenset({"법인"}),
            topics=frozenset({"법인세"}),
            region_codes=frozenset({"11"}),
        )
        user = UserTargeting(business_type="프리랜서", region_codes=frozenset({"26"}))
        result = match(content, user, today=TODAY)
        assert not result.matched
        assert result.excluded_reason is ExclusionReason.BELOW_THRESHOLD

    def test_rank_sorts_by_score_and_drops_unmatched(self):
        high = match(
            self.content(nearest_deadline=TODAY + dt.timedelta(days=1)),
            self.user(),
            today=TODAY,
        )
        low = match(self.content(), self.user(), today=TODAY)
        excluded = match(
            self.content(excluded_business_types=frozenset({"개인사업자"})),
            self.user(),
            today=TODAY,
        )
        ordered = rank([("low", low), ("excluded", excluded), ("high", high)])
        assert [key for key, _ in ordered] == ["high", "low"]
