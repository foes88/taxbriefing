"""인수 시나리오 AT-01 ~ AT-14 (§14.2).

실제 PostgreSQL 에 대해 실행한다. 이 파일이 통과하지 않으면
"개발 완료 정의"(§14.5)를 만족하지 못한 것이다.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.errors import ConflictError, ForbiddenError, GateFailedError, ValidationFailedError
from app.core.rbac import REVIEW_ROLES, ensure_role, ensure_tenant_scope
from app.core.security import Principal
from app.core.ssrf import SsrfBlocked, UrlPolicy, check_redirect_chain, check_url
from app.domain.enums import (
    AuthorityGrade,
    Channel,
    LegalStatus,
    ReviewDecision,
    RiskLevel,
    Role,
    SourceRole,
    WorkflowStatus,
)
from app.models.tables import Campaign, Consent, RawContentVersion
from app.services import content as content_service
from app.services import ingest
from app.services.delivery.channels import OutboundMessage
from app.services.delivery.dispatch import (
    delivery_idempotency_key,
    dispatch,
    has_active_consent,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

NOW = dt.datetime(2026, 8, 6, tzinfo=dt.UTC)


# --------------------------------------------------------------------- 헬퍼


def link_evidence(db, content, version_id, fields: list[str]) -> None:
    for field in fields:
        content_service.add_evidence(
            db,
            content,
            field_name=field,
            raw_content_version_id=version_id,
            locator=f"field:{field}#p1",
        )


def approvable_content(db, make_source, make_raw_version, *, risk=RiskLevel.MEDIUM):
    """게이트를 모두 통과할 수 있는 콘텐츠를 만든다."""
    source = make_source(AuthorityGrade.A)
    version = make_raw_version(source, title="소득세법 시행령 일부개정")
    content = content_service.create_content(
        db,
        title="소득세법 시행령 개정",
        source_version_ids=[version.id],
        legal_status=LegalStatus.PROMULGATED,
        risk_level=risk,
        roles={version.id: SourceRole.PRIMARY},
        now=NOW,
    )
    link_evidence(db, content, version.id, ["legal_status", "affected_users", "effective_date"])
    content.effective_date = dt.date(2027, 1, 1)
    db.flush()
    return content, version


# --------------------------------------------------------------------- AT-01


class TestAT01IdempotentCollection:
    """동일 게시물을 3회 수집해도 raw_content 는 1개이고 실행이력만 증가한다."""

    def test_three_identical_collections_create_one_record(self, db, make_source):
        source = make_source(AuthorityGrade.B)
        url = "https://www.nts.go.kr/board/12345"
        body = "부가가치세 신고 안내입니다.\n\n신고 기한을 확인하세요."

        results = [
            ingest.ingest(
                db,
                source_id=source.id,
                canonical_url=url,
                title="부가가치세 신고 안내",
                publisher="국세청",
                raw_body=body,
                now=NOW + dt.timedelta(hours=i),
            )
            for i in range(3)
        ]

        assert results[0].outcome is ingest.IngestOutcome.NEW
        assert results[1].outcome is ingest.IngestOutcome.UNCHANGED
        assert results[2].outcome is ingest.IngestOutcome.UNCHANGED

        ids = {r.raw_content.id for r in results}
        assert len(ids) == 1

        versions = db.query(RawContentVersion).filter_by(
            raw_content_id=results[0].raw_content.id
        ).all()
        assert len(versions) == 1

    def test_last_checked_at_advances_on_recollection(self, db, make_source):
        source = make_source(AuthorityGrade.B)
        url = "https://www.nts.go.kr/board/999"
        first = ingest.ingest(
            db, source_id=source.id, canonical_url=url, title="t",
            publisher="국세청", raw_body="본문", now=NOW,
        )
        later = NOW + dt.timedelta(days=1)
        ingest.ingest(
            db, source_id=source.id, canonical_url=url, title="t",
            publisher="국세청", raw_body="본문", now=later,
        )
        db.refresh(first.raw_content)
        assert first.raw_content.last_checked_at.replace(tzinfo=dt.UTC) == later

    def test_tracking_params_do_not_create_duplicates(self, db, make_source):
        source = make_source(AuthorityGrade.B)
        a = ingest.ingest(
            db, source_id=source.id, canonical_url="https://www.nts.go.kr/b/1",
            title="t", publisher="국세청", raw_body="본문", now=NOW,
        )
        b = ingest.ingest(
            db, source_id=source.id,
            canonical_url="https://www.nts.go.kr/b/1?utm_source=newsletter",
            title="t", publisher="국세청", raw_body="본문", now=NOW,
        )
        assert a.raw_content.id == b.raw_content.id
        assert b.outcome is ingest.IngestOutcome.UNCHANGED


# --------------------------------------------------------------------- AT-02


class TestAT02Versioning:
    """원문 본문이 변경되면 새 raw_content_version 과 diff 가 생성된다."""

    def test_changed_body_creates_new_version_with_diff(self, db, make_source):
        source = make_source(AuthorityGrade.A)
        url = "https://www.law.go.kr/law/1"

        first = ingest.ingest(
            db, source_id=source.id, canonical_url=url, title="법령",
            publisher="법제처", raw_body="제1조 시행일은 2027년 1월 1일이다.", now=NOW,
        )
        second = ingest.ingest(
            db, source_id=source.id, canonical_url=url, title="법령",
            publisher="법제처", raw_body="제1조 시행일은 2027년 7월 1일이다.", now=NOW,
        )

        assert second.outcome is ingest.IngestOutcome.CHANGED
        assert second.version.version_no == 2
        assert first.raw_content.id == second.raw_content.id
        assert second.diff and "2027년 7월 1일" in second.diff

        db.refresh(second.raw_content)
        assert second.raw_content.current_version_id == second.version.id

    def test_previous_version_is_preserved(self, db, make_source):
        source = make_source(AuthorityGrade.A)
        url = "https://www.law.go.kr/law/2"
        ingest.ingest(db, source_id=source.id, canonical_url=url, title="t",
                      publisher="법제처", raw_body="원본", now=NOW)
        result = ingest.ingest(db, source_id=source.id, canonical_url=url, title="t",
                               publisher="법제처", raw_body="수정본", now=NOW)

        versions = db.query(RawContentVersion).filter_by(
            raw_content_id=result.raw_content.id
        ).order_by(RawContentVersion.version_no).all()
        assert [v.version_no for v in versions] == [1, 2]
        assert versions[0].normalized_text == "원본"

    def test_revert_does_not_create_third_version(self, db, make_source):
        """§7.4 D-03: A→B→A 되돌림은 새 버전이 아니라 포인터 이동이다."""
        source = make_source(AuthorityGrade.A)
        url = "https://www.law.go.kr/law/3"
        for body in ("A", "B"):
            ingest.ingest(db, source_id=source.id, canonical_url=url, title="t",
                          publisher="법제처", raw_body=body, now=NOW)
        back = ingest.ingest(db, source_id=source.id, canonical_url=url, title="t",
                             publisher="법제처", raw_body="A", now=NOW)

        assert back.outcome is ingest.IngestOutcome.REVERTED
        versions = db.query(RawContentVersion).filter_by(
            raw_content_id=back.raw_content.id
        ).all()
        assert len(versions) == 2
        assert back.raw_content.current_version_id == back.version.id


# --------------------------------------------------------------------- AT-03


class TestAT03NewsOnlyBlocked:
    """뉴스만 연결된 콘텐츠는 승인·발송할 수 없다."""

    @pytest.mark.parametrize("grade", [AuthorityGrade.C, AuthorityGrade.D])
    def test_news_only_content_cannot_submit_for_review(
        self, db, make_source, make_raw_version, grade
    ):
        source = make_source(grade)
        version = make_raw_version(source, title="세법 개정 전망")
        content = content_service.create_content(
            db, title="세법 개정 전망", source_version_ids=[version.id], now=NOW
        )

        assert content.workflow is WorkflowStatus.UNVERIFIED

        with pytest.raises(GateFailedError) as exc:
            content_service.submit_for_review(db, content, now=NOW)
        assert "G1" in exc.value.details["failed_gates"]

    def test_news_only_content_cannot_be_approved(
        self, db, make_source, make_raw_version, make_user
    ):
        source = make_source(AuthorityGrade.D)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="뉴스 기반 콘텐츠", source_version_ids=[version.id], now=NOW
        )
        reviewer = make_user(Role.REVIEWER)

        with pytest.raises(GateFailedError):
            content_service.record_review(
                db, content,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.APPROVE,
                review_note="확인함",
                checked_source_version_ids=[version.id],
                now=NOW,
            )

    def test_adding_official_source_unblocks_it(
        self, db, make_source, make_raw_version
    ):
        """UC-02: 뉴스로 탐지한 뒤 공식 원문을 연결하면 진행할 수 있다."""
        news = make_source(AuthorityGrade.D)
        news_version = make_raw_version(news, title="세법 개정 전망")
        content = content_service.create_content(
            db, title="세법 개정", source_version_ids=[news_version.id], now=NOW
        )

        official = make_source(AuthorityGrade.A)
        official_version = make_raw_version(official, title="관보 공포문")
        content_service.link_source(
            db,
            content,
            raw_content_version_id=official_version.id,
            role=SourceRole.PRIMARY,
            now=NOW,
        )
        # 공식 근거가 붙는 순간 원문성이 확인된다.
        assert content.workflow is WorkflowStatus.SOURCE_CONFIRMED

        link_evidence(db, content, official_version.id, ["legal_status", "affected_users"])

        report = content_service.submit_for_review(db, content, now=NOW)
        assert report.can_approve
        assert content.workflow is WorkflowStatus.REVIEW_PENDING


# --------------------------------------------------------------------- AT-04


class TestAT04StatusDisplay:
    """입법예고 콘텐츠가 '시행 중'으로 표시되지 않는다."""

    def test_preannounced_is_not_confirmed(self):
        assert not LegalStatus.PREANNOUNCED.is_confirmed
        assert not LegalStatus.BILL_PROPOSED.is_confirmed
        assert not LegalStatus.GOV_ANNOUNCED.is_confirmed
        assert LegalStatus.EFFECTIVE.is_confirmed

    def test_preannounced_content_keeps_its_status_through_approval(
        self, db, make_source, make_raw_version, make_user
    ):
        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source, title="입법예고")
        content = content_service.create_content(
            db, title="소득세법 입법예고",
            source_version_ids=[version.id],
            legal_status=LegalStatus.PREANNOUNCED,
            now=NOW,
        )
        link_evidence(db, content, version.id, ["legal_status", "affected_users"])
        content_service.submit_for_review(db, content, now=NOW)

        reviewer = make_user(Role.REVIEWER)
        content_service.record_review(
            db, content,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.APPROVE,
            review_note="입법예고 단계 확인",
            checked_source_version_ids=[version.id],
            now=NOW,
        )

        assert content.legal is LegalStatus.PREANNOUNCED
        assert not content.legal.is_confirmed
        assert content.workflow is WorkflowStatus.APPROVED

    def test_cannot_claim_effective_without_grade_a_evidence(
        self, db, make_source, make_raw_version
    ):
        """B등급 근거만으로 '시행 중'을 주장할 수 없다 (§9.4 V3)."""
        source = make_source(AuthorityGrade.B)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="시행 주장",
            source_version_ids=[version.id],
            legal_status=LegalStatus.EFFECTIVE,
            now=NOW,
        )
        link_evidence(db, content, version.id, ["legal_status", "affected_users"])

        with pytest.raises(GateFailedError) as exc:
            content_service.submit_for_review(db, content, now=NOW)
        assert "G5" in exc.value.details["failed_gates"]


# --------------------------------------------------------------------- AT-05


class TestAT05NullDates:
    """시행일 근거가 없으면 AI 출력 effective_date 는 null 이다."""

    def test_ungrounded_effective_date_is_nullified_on_submit(
        self, db, make_source, make_raw_version
    ):
        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="시행일 미확인 콘텐츠",
            source_version_ids=[version.id],
            legal_status=LegalStatus.PREANNOUNCED,
            now=NOW,
        )
        link_evidence(db, content, version.id, ["legal_status", "affected_users"])

        # 근거 없이 시행일이 들어갔다고 가정한다.
        content.effective_date = dt.date(2027, 1, 1)
        db.flush()

        content_service.submit_for_review(db, content, now=NOW)
        assert content.effective_date is None

    def test_grounded_effective_date_survives(self, db, make_source, make_raw_version):
        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="시행일 확인 콘텐츠",
            source_version_ids=[version.id],
            legal_status=LegalStatus.PROMULGATED,
            now=NOW,
        )
        link_evidence(
            db, content, version.id, ["legal_status", "affected_users", "effective_date"]
        )
        content.effective_date = dt.date(2027, 1, 1)
        db.flush()

        content_service.submit_for_review(db, content, now=NOW)
        assert content.effective_date == dt.date(2027, 1, 1)

    def test_ai_pipeline_returns_null_when_source_lacks_date(
        self, db, make_source, make_raw_version
    ):
        """AI 실행 전체 경로에서도 근거 없는 날짜는 null 이다."""
        from app.services.ai import runner

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source, body="시행일 언급이 없는 본문입니다.")
        result = runner.run_analysis(db, source_version_ids=[version.id])

        assert result.output is not None
        assert result.output.effective_date is None
        assert result.output.promulgation_date is None
        assert result.analysis.output_json is not None


# --------------------------------------------------------------------- AT-06


class TestAT06HighRiskGate:
    """HIGH 위험도 콘텐츠는 REVIEWER 승인 없이는 캠페인에 포함되지 않는다."""

    def test_high_risk_cannot_be_scheduled_before_approval(
        self, db, make_source, make_raw_version
    ):
        content, _ = approvable_content(db, make_source, make_raw_version, risk=RiskLevel.HIGH)
        report = content_service.evaluate_for_campaign(db, content)

        assert not report.can_schedule
        assert "G6" in report.failed_gate_ids()

    def test_high_risk_can_be_scheduled_after_reviewer_approval(
        self, db, make_source, make_raw_version, make_user
    ):
        content, version = approvable_content(
            db, make_source, make_raw_version, risk=RiskLevel.HIGH
        )
        content_service.submit_for_review(db, content, now=NOW)

        reviewer = make_user(Role.REVIEWER)
        content_service.record_review(
            db, content,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.APPROVE,
            review_note="시행일과 경과조치 원문 확인 완료",
            checked_source_version_ids=[version.id],
            now=NOW,
        )

        report = content_service.evaluate_for_campaign(db, content)
        assert report.can_schedule

    def test_campaign_manager_cannot_bypass_expert_approval(self):
        """§12.2: CAMPAIGN_MANAGER 는 검수 권한이 없다."""
        principal = Principal(uuid.uuid4(), Role.CAMPAIGN_MANAGER, None)
        with pytest.raises(ForbiddenError):
            ensure_role(principal, REVIEW_ROLES)

    def test_system_admin_cannot_substitute_for_reviewer(self):
        """§12.2: SYSTEM_ADMIN 도 검수 책임을 대체할 수 없다."""
        principal = Principal(uuid.uuid4(), Role.SYSTEM_ADMIN, None)
        with pytest.raises(ForbiddenError):
            ensure_role(principal, REVIEW_ROLES)

    def test_medium_risk_needs_no_expert_approval(
        self, db, make_source, make_raw_version
    ):
        content, _ = approvable_content(db, make_source, make_raw_version, risk=RiskLevel.MEDIUM)
        assert content_service.evaluate_for_campaign(db, content).can_schedule


# --------------------------------------------------------------------- AT-07


class TestAT07Reapproval:
    """승인 후 본문 수정 시 승인상태가 해제되고 재검수 큐로 이동한다."""

    def approve(self, db, make_source, make_raw_version, make_user):
        content, version = approvable_content(db, make_source, make_raw_version)
        content_service.submit_for_review(db, content, now=NOW)
        reviewer = make_user(Role.REVIEWER)
        content_service.record_review(
            db, content,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.APPROVE,
            review_note="확인 완료",
            checked_source_version_ids=[version.id],
            now=NOW,
        )
        assert content.workflow is WorkflowStatus.APPROVED
        return content, version

    def test_protected_field_edit_revokes_approval(
        self, db, make_source, make_raw_version, make_user
    ):
        content, _ = self.approve(db, make_source, make_raw_version, make_user)

        content, outcome = content_service.update_content(
            db, content, {"effective_date": dt.date(2027, 7, 1)}, now=NOW
        )

        assert outcome.approval_revoked
        assert content.workflow is WorkflowStatus.REVIEW_PENDING
        assert "effective_date" in outcome.protected_changed

    def test_body_edit_creates_version_and_revokes_approval(
        self, db, make_source, make_raw_version, make_user
    ):
        content, _ = self.approve(db, make_source, make_raw_version, make_user)
        old_version_id = content.current_version_id

        content, outcome = content_service.update_content(
            db, content, {"body": {"summary": "수정된 본문"}}, now=NOW
        )

        assert outcome.approval_revoked
        assert content.current_version_id != old_version_id
        assert content.workflow is WorkflowStatus.REVIEW_PENDING

    def test_revoked_content_is_not_schedulable(
        self, db, make_source, make_raw_version, make_user
    ):
        """승인 해제 후에는 이전 승인이 재사용되지 않는다."""
        content, _ = self.approve(db, make_source, make_raw_version, make_user)
        content.risk = RiskLevel.HIGH
        db.flush()
        content, _ = content_service.update_content(
            db, content, {"body": {"v": 2}}, now=NOW
        )
        report = content_service.evaluate_for_campaign(db, content)
        assert not report.can_schedule

    def test_optimistic_lock_rejects_stale_write(
        self, db, make_source, make_raw_version
    ):
        content, _ = approvable_content(db, make_source, make_raw_version)
        stale = content.lock_version - 1
        with pytest.raises(ConflictError):
            content_service.update_content(
                db, content, {"title": "새 제목"}, expected_version=stale, now=NOW
            )

    def test_unknown_field_is_rejected(self, db, make_source, make_raw_version):
        """A-06: 임의 필드 수정을 허용하지 않는다."""
        content, _ = approvable_content(db, make_source, make_raw_version)
        with pytest.raises(ValidationFailedError):
            content_service.update_content(
                db, content, {"source_confidence": 100}, now=NOW
            )


# --------------------------------------------------------------------- AT-08 / AT-10


class TestAT08AndAT10Exclusion:
    """AT-08 명시적 제외, AT-10 수신철회 사용자는 최종 대상에서 제외된다."""

    def make_profile(self, db, user, **kwargs):
        from app.models.tables import BusinessProfile

        profile = BusinessProfile(
            user_id=user.id,
            business_type=kwargs.get("business_type", "개인사업자"),
            industry_codes=kwargs.get("industry_codes", []),
            region_codes=kwargs.get("region_codes", ["ALL"]),
            interest_topics=kwargs.get("interest_topics", ["부가세"]),
        )
        db.add(profile)
        db.flush()
        return profile

    def grant(self, db, user, channel=Channel.EMAIL, granted=True, at=NOW):
        consent = Consent(
            user_id=user.id,
            consent_type="MARKETING",
            channel=channel.value,
            granted=granted,
            document_version="v1",
            granted_at=at,
            revoked_at=None if granted else at,
        )
        db.add(consent)
        db.flush()
        return consent

    def test_excluded_user_is_removed_regardless_of_score(self, db, make_user):
        from app.domain.personalization import ContentTargeting
        from app.services.delivery.dispatch import select_recipients

        user = make_user(Role.SUBSCRIBER)
        self.make_profile(db, user, industry_codes=["F001"])
        self.grant(db, user)

        targeting = ContentTargeting(
            business_types=frozenset({"개인사업자"}),
            topics=frozenset({"부가세"}),
            industry_codes=frozenset({"F001"}),
            region_codes=frozenset({"ALL"}),
            excluded_business_types=frozenset({"개인사업자"}),
            nearest_deadline=NOW.date() + dt.timedelta(days=2),
        )

        decisions = select_recipients(
            db,
            candidate_user_ids=[user.id],
            targeting=targeting,
            channel=Channel.EMAIL,
            today=NOW.date(),
        )
        assert not decisions[0].included
        assert decisions[0].result.excluded_reason.value == "EXPLICITLY_EXCLUDED"

    def test_matching_user_is_included(self, db, make_user):
        from app.domain.personalization import ContentTargeting
        from app.services.delivery.dispatch import select_recipients

        user = make_user(Role.SUBSCRIBER)
        self.make_profile(db, user)
        self.grant(db, user)

        decisions = select_recipients(
            db,
            candidate_user_ids=[user.id],
            targeting=ContentTargeting(
                business_types=frozenset({"개인사업자"}),
                topics=frozenset({"부가세"}),
                region_codes=frozenset({"ALL"}),
            ),
            channel=Channel.EMAIL,
            today=NOW.date(),
        )
        assert decisions[0].included
        assert decisions[0].result.user_facing_reasons()

    def test_revoked_consent_excludes_user(self, db, make_user):
        """AT-10: 예약 후 철회한 사용자는 발송 시점에 제외된다."""
        from app.domain.personalization import ContentTargeting
        from app.services.delivery.dispatch import select_recipients

        user = make_user(Role.SUBSCRIBER)
        self.make_profile(db, user)
        self.grant(db, user, granted=True, at=NOW)
        # 예약 후 철회 — append-only 이므로 새 행이 최신 상태가 된다.
        self.grant(db, user, granted=False, at=NOW + dt.timedelta(hours=1))

        assert not has_active_consent(db, user_id=user.id, channel=Channel.EMAIL)

        decisions = select_recipients(
            db,
            candidate_user_ids=[user.id],
            targeting=ContentTargeting(
                business_types=frozenset({"개인사업자"}),
                topics=frozenset({"부가세"}),
                region_codes=frozenset({"ALL"}),
            ),
            channel=Channel.EMAIL,
            today=NOW.date(),
        )
        assert not decisions[0].included
        assert decisions[0].result.excluded_reason.value == "CONSENT_REVOKED"

    def test_no_consent_record_means_no_consent(self, db, make_user):
        user = make_user(Role.SUBSCRIBER)
        assert not has_active_consent(db, user_id=user.id, channel=Channel.EMAIL)

    def test_consent_is_per_channel(self, db, make_user):
        user = make_user(Role.SUBSCRIBER)
        self.grant(db, user, channel=Channel.EMAIL, granted=True)
        assert has_active_consent(db, user_id=user.id, channel=Channel.EMAIL)
        assert not has_active_consent(db, user_id=user.id, channel=Channel.SMS)


# --------------------------------------------------------------------- AT-09


class TestAT09IdempotentDelivery:
    """동일 idempotency key 로 발송 요청해도 사용자당 1건만 전송된다."""

    def campaign(self, db) -> Campaign:
        campaign = Campaign(
            campaign_type="DAILY",
            name="일일 브리핑",
            audience_filter={},
            channels=[Channel.EMAIL.value],
        )
        db.add(campaign)
        db.flush()
        return campaign

    def message(self) -> OutboundMessage:
        return OutboundMessage(
            subject="오늘의 세무 브리핑",
            body="본문",
            unsubscribe_url="https://example.test/unsubscribe/abc",
        )

    def test_repeated_dispatch_creates_one_delivery(self, db, make_user):
        from app.models.tables import Delivery

        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)

        first = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )
        second = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )
        third = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )

        assert first.created
        assert not second.created and not third.created
        assert first.delivery.id == second.delivery.id == third.delivery.id

        count = db.query(Delivery).filter_by(campaign_id=campaign.id, user_id=user.id).count()
        assert count == 1

    def test_key_follows_documented_rule(self, db, make_user):
        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)
        expected = f"{campaign.id}:{user.id}:EMAIL"
        assert delivery_idempotency_key(campaign.id, user.id, Channel.EMAIL) == expected

        outcome = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )
        assert outcome.delivery.idempotency_key == expected

    def test_different_channel_is_a_separate_delivery(self, db, make_user):
        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)

        email = dispatch(db, campaign_id=campaign.id, user_id=user.id,
                         channel=Channel.EMAIL, message=self.message(), now=NOW)
        telegram = dispatch(db, campaign_id=campaign.id, user_id=user.id,
                            channel=Channel.TELEGRAM, message=self.message(), now=NOW)
        assert email.created and telegram.created
        assert email.delivery.id != telegram.delivery.id

    def test_email_without_unsubscribe_link_is_refused(self, db, make_user):
        """§11.4: 이메일에는 수신거부 링크가 필수다."""
        from app.services.delivery.channels import ChannelPolicyError

        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)
        with pytest.raises(ChannelPolicyError):
            dispatch(
                db, campaign_id=campaign.id, user_id=user.id, channel=Channel.EMAIL,
                message=OutboundMessage(subject="제목", body="본문"), now=NOW,
            )

    def test_snapshot_is_frozen_at_send_time(self, db, make_user):
        """§11.4: 콘텐츠가 나중에 바뀌어도 '무엇을 보냈는지'는 변하지 않는다."""
        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)
        outcome = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )
        assert outcome.delivery.message_snapshot["body"] == "본문"
        assert outcome.delivery.message_snapshot["unsubscribe_url"]

    def test_dispatch_does_not_send_by_default(self, db, make_user):
        """발송은 되돌릴 수 없다. 기본값은 레코드만 만들고 전송하지 않는다."""
        from app.domain.enums import DeliveryStatus

        campaign = self.campaign(db)
        user = make_user(Role.SUBSCRIBER)
        outcome = dispatch(
            db, campaign_id=campaign.id, user_id=user.id,
            channel=Channel.EMAIL, message=self.message(), now=NOW,
        )
        assert not outcome.sent
        assert outcome.delivery.status is DeliveryStatus.PENDING


# --------------------------------------------------------------------- AT-12


class TestAT12AuditTrail:
    """관리자는 누가 어떤 근거를 확인하고 승인했는지 조회할 수 있다."""

    def test_review_records_checked_source_versions(
        self, db, make_source, make_raw_version, make_user
    ):
        content, version = approvable_content(db, make_source, make_raw_version)
        content_service.submit_for_review(db, content, now=NOW)
        reviewer = make_user(Role.REVIEWER)

        review, _ = content_service.record_review(
            db, content,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.APPROVE_WITH_EDIT,
            review_note="시행일과 경과조치 원문 확인 완료",
            checked_source_version_ids=[version.id],
            now=NOW,
        )

        assert review.reviewer_id == reviewer.id
        assert review.checked_source_version_ids == [version.id]
        assert review.content_version_id == content.current_version_id
        assert review.review_note

    def test_audit_log_is_queryable_by_object(self, db, make_source, make_raw_version, make_user):
        from app.core import audit

        content, version = approvable_content(db, make_source, make_raw_version)
        reviewer = make_user(Role.REVIEWER)
        audit.record(
            db,
            action=audit.Action.CONTENT_REVIEWED,
            object_type="tax_content",
            object_id=content.id,
            actor_user_id=reviewer.id,
            after={"checked_source_version_ids": [str(version.id)]},
            reason="원문 확인 완료",
        )

        entries = audit.history(db, object_type="tax_content", object_id=content.id)
        assert entries
        assert entries[0].actor_user_id == reviewer.id
        assert str(version.id) in entries[0].after_data["checked_source_version_ids"]
        assert entries[0].trace_id

    def test_audit_masks_sensitive_values(self, db, make_user):
        from app.core import audit

        user = make_user(Role.SUBSCRIBER)
        entry = audit.record(
            db,
            action=audit.Action.PROFILE_UPDATED,
            object_type="user",
            object_id=user.id,
            after={"email": "someone@example.test", "password_hash": "$2b$12$abc", "role": "SUBSCRIBER"},
        )
        assert entry.after_data["email"] == "***"
        assert entry.after_data["password_hash"] == "***"
        assert entry.after_data["role"] == "SUBSCRIBER"

    def test_cannot_claim_unlinked_source_as_checked(
        self, db, make_source, make_raw_version, make_user
    ):
        """연결되지 않은 원문을 '확인함'으로 기록하면 추적성이 거짓이 된다."""
        content, _ = approvable_content(db, make_source, make_raw_version)
        content_service.submit_for_review(db, content, now=NOW)
        other_source = make_source(AuthorityGrade.A)
        stranger = make_raw_version(other_source)
        reviewer = make_user(Role.REVIEWER)

        with pytest.raises(ValidationFailedError):
            content_service.record_review(
                db, content,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.APPROVE,
                review_note="확인",
                checked_source_version_ids=[stranger.id],
                now=NOW,
            )

    def test_empty_checked_sources_is_rejected(
        self, db, make_source, make_raw_version, make_user
    ):
        content, _ = approvable_content(db, make_source, make_raw_version)
        content_service.submit_for_review(db, content, now=NOW)
        reviewer = make_user(Role.REVIEWER)

        with pytest.raises(ValidationFailedError):
            content_service.record_review(
                db, content,
                reviewer_id=reviewer.id,
                decision=ReviewDecision.APPROVE,
                review_note="확인",
                checked_source_version_ids=[],
                now=NOW,
            )


# --------------------------------------------------------------------- AT-13


class TestAT13TenantIsolation:
    """테넌트 관리자는 다른 테넌트의 자원을 볼 수 없다."""

    def test_cross_tenant_access_is_forbidden(self):
        mine, theirs = uuid.uuid4(), uuid.uuid4()
        principal = Principal(uuid.uuid4(), Role.TENANT_ADMIN, mine)
        with pytest.raises(ForbiddenError):
            ensure_tenant_scope(principal, theirs)

    def test_own_tenant_is_allowed(self):
        mine = uuid.uuid4()
        principal = Principal(uuid.uuid4(), Role.TENANT_ADMIN, mine)
        ensure_tenant_scope(principal, mine)

    def test_shared_content_is_readable_by_all(self):
        """§7.4 D-04: tenant_id 가 NULL 인 콘텐츠는 전체 공용이다."""
        principal = Principal(uuid.uuid4(), Role.TENANT_ADMIN, uuid.uuid4())
        ensure_tenant_scope(principal, None)

    def test_tenantless_admin_cannot_read_tenant_resource(self):
        principal = Principal(uuid.uuid4(), Role.TENANT_ADMIN, None)
        with pytest.raises(ForbiddenError):
            ensure_tenant_scope(principal, uuid.uuid4())


# --------------------------------------------------------------------- AT-14


class TestAT14Ssrf:
    """수집 대상 URL 이 사설 IP 로 리다이렉트되면 차단된다."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/admin",
            "http://10.0.0.5/secret",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://169.254.169.254/latest/meta-data/",  # 클라우드 메타데이터
            "http://[::1]/",
        ],
    )
    def test_private_addresses_are_blocked(self, url):
        with pytest.raises(SsrfBlocked):
            check_url(url)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://x/"])
    def test_non_http_schemes_are_blocked(self, url):
        with pytest.raises(SsrfBlocked, match="스킴"):
            check_url(url)

    def test_ipv4_mapped_ipv6_bypass_is_blocked(self):
        with pytest.raises(SsrfBlocked):
            check_url("http://[::ffff:10.0.0.1]/")

    def test_redirect_to_private_ip_is_blocked(self):
        """AT-14 핵심: 허용 도메인이 사설 IP 로 리다이렉트하는 경우."""
        chain = [
            "https://www.nts.go.kr/board/1",
            "http://169.254.169.254/latest/meta-data/",
        ]
        policy = UrlPolicy(allowed_hosts=frozenset({"nts.go.kr"}))
        with pytest.raises(SsrfBlocked):
            check_redirect_chain(chain, policy)

    def test_host_allowlist_is_enforced_on_first_hop(self):
        policy = UrlPolicy(allowed_hosts=frozenset({"nts.go.kr"}))
        with pytest.raises(SsrfBlocked, match="허용된 출처 도메인"):
            check_url("https://evil.example.com/x", policy)

    def test_subdomain_of_allowed_host_passes_allowlist(self):
        policy = UrlPolicy(
            allowed_hosts=frozenset({"nts.go.kr"}), allow_private_ips=True
        )
        check_url("https://www.nts.go.kr/board/1", policy)

    def test_redirect_count_is_capped(self):
        chain = [f"https://a{i}.example.com/" for i in range(6)]
        policy = UrlPolicy(max_redirects=3, allow_private_ips=True)
        with pytest.raises(SsrfBlocked, match="리다이렉트"):
            check_redirect_chain(chain, policy)
