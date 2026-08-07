"""ORM 모델 (§7).

docs/contracts/schema.sql 을 기준으로 하되, §7.4 의 구현 결정 D-01~D-08 을 반영했다.
초안과 달라진 부분에는 D-번호를 주석으로 남긴다.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain import enums
from app.models.base import (
    AuthorityGradeType,
    Base,
    DeliveryStatusType,
    LegalStatusType,
    ReviewDecisionType,
    RiskLevelType,
    WorkflowStatusType,
    created_at_col,
    updated_at_col,
    uuid_pk,
)

_JSONB_OBJ = JSONB
_UUID = PgUUID(as_uuid=True)


# ---------------------------------------------------------------- 테넌트·계정


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    settings: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, default=enums.Role.SUBSCRIBER.value)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    password_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()

    @property
    def role_enum(self) -> enums.Role:
        return enums.Role(self.role)


# ---------------------------------------------------------------- 출처·원문


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    organization_code: Mapped[str | None] = mapped_column(Text)
    canonical_domain: Mapped[str] = mapped_column(Text, nullable=False)
    authority: Mapped[enums.AuthorityGrade] = mapped_column(AuthorityGradeType, nullable=False)
    collector_type: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(Text)
    rate_limit_per_min: Mapped[int | None] = mapped_column(Integer)
    terms_url: Mapped[str | None] = mapped_column(Text)
    copyright_policy: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    adapter_name: Mapped[str | None] = mapped_column(Text)
    adapter_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    failure_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 부록 A.2 의 나머지 필드는 운영 빈도가 확인될 때까지 settings 에 담는다.
    settings: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("sources.id"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    trace_id: Mapped[str | None] = mapped_column(Text)


class RawContent(Base):
    __tablename__ = "raw_contents"
    __table_args__ = (
        UniqueConstraint("source_id", "canonical_url", name="uq_raw_contents_source_url"),
        Index("idx_raw_contents_published", "published_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("sources.id"), nullable=False
    )
    source_item_id: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    first_collected_at: Mapped[dt.datetime] = created_at_col()
    last_checked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("raw_content_versions.id", use_alter=True)
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSONB_OBJ, nullable=False, default=dict
    )

    versions: Mapped[list[RawContentVersion]] = relationship(
        back_populates="raw_content",
        foreign_keys="RawContentVersion.raw_content_id",
        cascade="all, delete-orphan",
        order_by="RawContentVersion.version_no",
    )


class RawContentVersion(Base):
    __tablename__ = "raw_content_versions"
    __table_args__ = (
        UniqueConstraint("raw_content_id", "version_no", name="uq_rcv_content_version"),
        # D-03: 내용이 A→B→A 로 되돌아가면 삽입이 실패한다. 되돌림은 새 버전이 아니라
        # last_checked_at 갱신으로 처리하므로 제약을 유지한다.
        UniqueConstraint("raw_content_id", "content_hash", name="uq_rcv_content_hash"),
        Index("idx_raw_versions_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    raw_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("raw_contents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    http_etag: Mapped[str | None] = mapped_column(Text)
    http_last_modified: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[dt.datetime] = created_at_col()
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSONB_OBJ, nullable=False, default=dict
    )

    raw_content: Mapped[RawContent] = relationship(
        back_populates="versions", foreign_keys=[raw_content_id]
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("raw_content_version_id", "content_hash", name="uq_attachments_hash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    raw_content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("raw_content_versions.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    malware_scan_status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSONB_OBJ, nullable=False, default=dict
    )


# ---------------------------------------------------------------- 정책 클러스터


class PolicyCluster(Base):
    __tablename__ = "policy_clusters"

    id: Mapped[uuid.UUID] = uuid_pk()
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    topic_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class PolicyClusterItem(Base):
    __tablename__ = "policy_cluster_items"

    policy_cluster_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("policy_clusters.id", ondelete="CASCADE"), primary_key=True
    )
    raw_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("raw_contents.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False, default="RELATED")
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))


# ---------------------------------------------------------------- 콘텐츠


class TaxContent(Base):
    __tablename__ = "tax_contents"
    __table_args__ = (
        CheckConstraint(
            "source_confidence BETWEEN 0 AND 100", name="source_confidence_range"
        ),
        Index("idx_tax_contents_status", "workflow", "legal", "risk"),
        Index("idx_tax_contents_dates", "effective_date", "application_end"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # D-04: NULL = 전체 공용, 값 있음 = 해당 테넌트 전용.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    policy_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("policy_clusters.id")
    )
    workflow: Mapped[enums.WorkflowStatus] = mapped_column(
        WorkflowStatusType, nullable=False, default=enums.WorkflowStatus.DETECTED
    )
    legal: Mapped[enums.LegalStatus] = mapped_column(
        LegalStatusType, nullable=False, default=enums.LegalStatus.UNKNOWN
    )
    risk: Mapped[enums.RiskLevel] = mapped_column(
        RiskLevelType, nullable=False, default=enums.RiskLevel.MEDIUM
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    one_line_summary: Mapped[str | None] = mapped_column(Text)
    announcement_date: Mapped[dt.date | None] = mapped_column(Date)
    promulgation_date: Mapped[dt.date | None] = mapped_column(Date)
    effective_date: Mapped[dt.date | None] = mapped_column(Date)
    application_start: Mapped[dt.date | None] = mapped_column(Date)
    application_end: Mapped[dt.date | None] = mapped_column(Date)
    source_confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # D-08: 점수 내역 조회 (FR-VER-005).
    confidence_breakdown: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("content_versions.id", use_alter=True)
    )
    #: 업종 분류 (app.domain.industry). 상담 참고용 색인이지 적용 판정이 아니다.
    industries: Mapped[list[str]] = mapped_column(
        "industries", JSONB, nullable=False, default=list
    )
    #: 검색용 합본 텍스트. 본문이 content_versions 에 있어 생성 컬럼으로 못 만든다.
    #: 게시·수정 시점에 코드가 채운다.
    search_text: Mapped[str | None] = mapped_column(Text)
    # 낙관적 잠금 (§8.1 If-Match).
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()

    sources: Mapped[list[ContentSource]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    evidence: Mapped[list[ContentEvidence]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("tax_content_id", "version_no", name="uq_content_versions_no"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False)
    rendered_html: Mapped[str | None] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = created_at_col()


class ContentSource(Base):
    """가공 콘텐츠 ↔ 원문 버전 근거 관계 (§7.3)."""

    __tablename__ = "content_sources"
    __table_args__ = (
        CheckConstraint(
            "role IN ('PRIMARY','SECONDARY','REFERENCE')", name="content_sources_role"
        ),
    )

    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id", ondelete="CASCADE"), primary_key=True
    )
    raw_content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("raw_content_versions.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ContentEvidence(Base):
    """필드별 근거 위치 (§7.3). 이 표가 비면 G3/G4 가 통과하지 못한다."""

    __tablename__ = "content_evidence"
    __table_args__ = (
        CheckConstraint(
            "support_type IN ('DIRECT','INFERRED','CONFLICT')",
            name="content_evidence_support_type",
        ),
        Index("idx_content_evidence_content", "tax_content_id", "field_name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id", ondelete="CASCADE"), nullable=False
    )
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("content_versions.id")
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("raw_content_versions.id"), nullable=False
    )
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    support_type: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class AiAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = uuid_pk()
    tax_content_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("tax_contents.id")
    )
    policy_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("policy_clusters.id")
    )
    prompt_template_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # V1: 스키마 검증에 실패해도 원본은 그대로 저장한다.
    output_json: Mapped[dict[str, Any] | None] = mapped_column(_JSONB_OBJ)
    validation_result: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    token_usage: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False, default=dict)
    cost_amount: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = created_at_col()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id", ondelete="CASCADE"), nullable=False
    )
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("content_versions.id"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("users.id"), nullable=False
    )
    decision: Mapped[enums.ReviewDecision] = mapped_column(ReviewDecisionType, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    # D-02: A-01 결정에 따라 '원문 버전' ID 를 저장한다. FK 는 애플리케이션에서 검증.
    checked_source_version_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(_UUID), nullable=False, default=list
    )
    created_at: Mapped[dt.datetime] = created_at_col()


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[uuid.UUID] = uuid_pk()
    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id"), nullable=False
    )
    original_content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("content_versions.id"), nullable=False
    )
    corrected_content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("content_versions.id"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    reason_detail: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[enums.RiskLevel] = mapped_column(RiskLevelType, nullable=False)
    impact_filter: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()


# ---------------------------------------------------------------- 태그·프로필


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tag_type", "code", name="uq_tags_type_code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tag_type: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tags.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")


class ContentTag(Base):
    __tablename__ = "content_tags"

    tax_content_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tax_contents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("tags.id"), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="MANUAL")
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    # 제외 대상 태그 여부. 개인화 하드 제외에 쓴다 (§11.2, AT-08).
    is_exclusion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    business_type: Mapped[str] = mapped_column(Text, nullable=False)
    tax_type: Mapped[str | None] = mapped_column(Text)
    industry_codes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    region_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    employee_band: Mapped[str | None] = mapped_column(Text)
    revenue_band: Mapped[str | None] = mapped_column(Text)
    interest_topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Consent(Base):
    """수신·개인정보 동의 이력 (§12.4).

    D-05: append-only. '현재 유효 동의'는 (user_id, consent_type, channel) 별
    최신 행으로 판정한다.
    """

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str | None] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    document_version: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- 캠페인·발송


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    campaign_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    audience_filter: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = created_at_col()


class CampaignContent(Base):
    __tablename__ = "campaign_contents"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("content_versions.id"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("users.id"), primary_key=True
    )
    match_score: Mapped[int | None] = mapped_column(Integer)
    match_reasons: Mapped[dict[str, Any]] = mapped_column(
        _JSONB_OBJ, nullable=False, default=dict
    )
    excluded_reason: Mapped[str | None] = mapped_column(Text)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (Index("idx_deliveries_campaign_status", "campaign_id", "status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("campaigns.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("users.id"), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    # D-01: 전역 UNIQUE + 키 생성 규칙 "{campaign_id}:{user_id}:{channel}" (§11.5, AT-09).
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[enums.DeliveryStatus] = mapped_column(
        DeliveryStatusType, nullable=False, default=enums.DeliveryStatus.PENDING
    )
    # 발송 시점 고정 스냅샷. 콘텐츠가 나중에 바뀌어도 불변 (§11.4).
    message_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSONB_OBJ, nullable=False)
    attempted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)


class EngagementEvent(Base):
    __tablename__ = "engagement_events"
    __table_args__ = (Index("idx_engagement_content_time", "tax_content_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("deliveries.id"))
    tax_content_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("tax_contents.id")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[dt.datetime] = created_at_col()
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSONB_OBJ, nullable=False, default=dict
    )


class ConsultationRequest(Base):
    __tablename__ = "consultation_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("users.id"), nullable=False)
    tax_content_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("tax_contents.id")
    )
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="NEW")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


# ---------------------------------------------------------------- 감사·멱등성


class AuditLog(Base):
    """append-only 감사 이벤트 (§NFR-009, AT-12). UPDATE/DELETE 하지 않는다."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_object", "object_type", "object_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[dt.datetime] = created_at_col()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("tenants.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(Text, nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(_JSONB_OBJ)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(_JSONB_OBJ)
    reason: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)


class IdempotencyRecord(Base):
    """D-06: 멱등성 저장소 (§NFR-005).

    같은 Idempotency-Key 로 온 요청이 정말 같은 요청인지 확인하기 위해
    요청 본문 해시를 함께 저장한다. 키는 같은데 본문이 다르면 409 로 거절한다.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(_JSONB_OBJ)
    created_at: Mapped[dt.datetime] = created_at_col()
