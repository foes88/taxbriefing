"""API 요청·응답 스키마 (§8, docs/contracts/openapi.yaml 기준).

§8.4 의 구현 결정 A-01~A-07 을 반영했다.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AuthorityGrade,
    CollectorType,
    LegalStatus,
    ReviewDecision,
    RiskLevel,
    Role,
    SourceRole,
    WorkflowStatus,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- 인증


class LoginRequest(Strict):
    email: str
    password: str


class TokenResponse(Strict):
    access_token: str
    token_type: str = "bearer"
    role: Role
    tenant_id: UUID | None = None


# ---------------------------------------------------------------- 출처


class SourceCreate(Strict):
    display_name: str
    canonical_domain: str
    authority: AuthorityGrade
    collector_type: CollectorType
    organization_code: str | None = None
    schedule_cron: str | None = None
    rate_limit_per_min: int | None = None
    terms_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class SourceOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    display_name: str
    canonical_domain: str
    authority: AuthorityGrade
    collector_type: str
    organization_code: str | None = None
    schedule_cron: str | None = None
    status: str
    last_success_at: dt.datetime | None = None
    failure_streak: int


# ---------------------------------------------------------------- 원문


class ManualRawContentCreate(Strict):
    """수동 원문 등록 (FR-SRC-006)."""

    source_id: UUID
    title: str
    canonical_url: str
    publisher: str
    normalized_text: str
    published_at: dt.datetime | None = None
    source_item_id: str | None = None


class RawContentVersionOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    version_no: int
    content_hash: str
    parser_version: str
    collected_at: dt.datetime


class RawContentOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    source_id: UUID
    canonical_url: str
    title: str
    publisher: str
    published_at: dt.datetime | None = None
    first_collected_at: dt.datetime
    last_checked_at: dt.datetime
    current_version_id: UUID | None = None
    status: str


class ManualRawContentResponse(Strict):
    outcome: str
    raw_content: RawContentOut
    version: RawContentVersionOut
    diff: str | None = None


# ---------------------------------------------------------------- AI 분석


class AnalysisRequestBody(Strict):
    source_version_ids: list[UUID] = Field(min_length=1)
    policy_cluster_id: UUID | None = None
    tax_content_id: UUID | None = None
    prompt_version: str | None = None


class AnalysisOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    status: str
    model_provider: str
    model_name: str
    prompt_version: str
    schema_version: str
    input_hash: str
    latency_ms: int | None = None
    output_json: dict[str, Any] | None = None
    validation_result: dict[str, Any]
    created_at: dt.datetime


class AnalysisAccepted(Strict):
    analysis_id: UUID
    status: str
    reused: bool
    blocked: bool


# ---------------------------------------------------------------- 콘텐츠


class SourceLinkIn(Strict):
    source_version_id: UUID
    role: SourceRole = SourceRole.SECONDARY


class ContentCreate(Strict):
    """A-04: legal_status 기본값은 UNKNOWN. 확정은 검수 단계에서 한다."""

    title: str = Field(max_length=120)
    source_version_ids: list[UUID] = Field(min_length=1)
    policy_cluster_id: UUID | None = None
    legal_status: LegalStatus = LegalStatus.UNKNOWN
    risk_level: RiskLevel = RiskLevel.MEDIUM
    body: dict[str, Any] = Field(default_factory=dict)
    source_roles: list[SourceLinkIn] = Field(default_factory=list)


class ContentPatch(Strict):
    """A-06: 수정 가능한 필드를 명시적으로 제한한다."""

    title: str | None = Field(default=None, max_length=120)
    one_line_summary: str | None = Field(default=None, max_length=250)
    legal_status: LegalStatus | None = None
    risk_level: RiskLevel | None = None
    announcement_date: dt.date | None = None
    promulgation_date: dt.date | None = None
    effective_date: dt.date | None = None
    application_start: dt.date | None = None
    application_end: dt.date | None = None
    body: dict[str, Any] | None = None


class EvidenceIn(Strict):
    field_name: str
    raw_content_version_id: UUID
    locator: str
    support_type: str = "DIRECT"
    note: str | None = None


class ContentOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    title: str
    one_line_summary: str | None = None
    workflow_status: WorkflowStatus
    legal_status: LegalStatus
    risk_level: RiskLevel
    announcement_date: dt.date | None = None
    promulgation_date: dt.date | None = None
    effective_date: dt.date | None = None
    application_start: dt.date | None = None
    application_end: dt.date | None = None
    source_confidence: int
    confidence_breakdown: dict[str, Any] = Field(default_factory=dict)
    version: int
    current_version_id: UUID | None = None
    tenant_id: UUID | None = None

    @classmethod
    def of(cls, content: Any) -> ContentOut:
        return cls(
            id=content.id,
            title=content.title,
            one_line_summary=content.one_line_summary,
            workflow_status=content.workflow,
            legal_status=content.legal,
            risk_level=content.risk,
            announcement_date=content.announcement_date,
            promulgation_date=content.promulgation_date,
            effective_date=content.effective_date,
            application_start=content.application_start,
            application_end=content.application_end,
            source_confidence=content.source_confidence,
            confidence_breakdown=content.confidence_breakdown or {},
            version=content.lock_version,
            current_version_id=content.current_version_id,
            tenant_id=content.tenant_id,
        )


class ContentPatchResponse(Strict):
    content: ContentOut
    approval_revoked: bool
    protected_fields_changed: list[str]
    message: str | None = None


class GateReportOut(Strict):
    can_approve: bool
    can_schedule: bool
    can_personalize: bool
    requires_review: bool
    results: list[dict[str, Any]]


class SubmitReviewResponse(Strict):
    content: ContentOut
    gate_report: GateReportOut


# ---------------------------------------------------------------- 검수


class ReviewRequest(Strict):
    """A-01: checked_source_version_ids 로 통일 (원문이 아니라 원문 *버전*)."""

    decision: ReviewDecision
    review_note: str = Field(min_length=1)
    checked_source_version_ids: list[UUID] = Field(min_length=1)
    legal_status: LegalStatus | None = None
    risk_level: RiskLevel | None = None


class ReviewOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tax_content_id: UUID
    content_version_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    review_note: str | None = None
    checked_source_version_ids: list[UUID]
    created_at: dt.datetime


class ReviewResponse(Strict):
    review: ReviewOut
    content: ContentOut
    gate_report: GateReportOut


# ---------------------------------------------------------------- 사용자


class BusinessProfileIn(Strict):
    business_type: str
    tax_type: str | None = None
    industry_codes: list[str] = Field(default_factory=list)
    region_codes: list[str] = Field(default_factory=list)
    employee_band: str | None = None
    revenue_band: str | None = None
    interest_topics: list[str] = Field(default_factory=list)


class BusinessProfileOut(BusinessProfileIn):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    user_id: UUID


# ---------------------------------------------------------------- 감사


class AuditLogOut(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    occurred_at: dt.datetime
    actor_user_id: UUID | None = None
    action: str
    object_type: str
    object_id: str
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    reason: str | None = None
    trace_id: str | None = None
