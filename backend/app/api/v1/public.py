"""공개 열람 API — 로그인 없이 읽는다 (ADR-001).

텔레그램·이메일에서 링크를 타고 들어온 사업자가 회원가입 없이 바로 읽을 수 있어야 한다.

**공개되는 것은 PUBLISHED/CORRECTED/MONITORING 상태의 콘텐츠뿐이다.**
검수 전 초안이 공개 경로로 새어나가면 §1.3 "사람이 최종 승인" 원칙이 무너지므로,
필터는 옵션이 아니라 쿼리에 항상 강제로 들어간다.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.domain.enums import LegalStatus, RiskLevel, WorkflowStatus
from app.models.tables import (
    ContentEvidence,
    ContentSource,
    ContentVersion,
    RawContent,
    RawContentVersion,
    Source,
    TaxContent,
)
from app.services.render.telegram import STATUS_CAVEAT, STATUS_LABEL

router = APIRouter(prefix="/public", tags=["Public"])

#: 공개 가능한 워크플로 상태. 이 목록 밖의 콘텐츠는 어떤 경로로도 노출되지 않는다.
PUBLIC_STATES = (
    WorkflowStatus.PUBLISHED,
    WorkflowStatus.MONITORING,
    WorkflowStatus.CORRECTED,
)


class PublicSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher: str
    title: str
    url: str
    authority: str
    role: str
    published_at: dt.datetime | None = None


class PublicContentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    one_line_summary: str | None = None
    legal_status: LegalStatus
    status_label: str
    status_caveat: str | None = None
    is_confirmed: bool
    risk_level: RiskLevel
    effective_date: dt.date | None = None
    application_end: dt.date | None = None
    corrected: bool = False
    updated_at: dt.datetime


class PublicContentDetail(PublicContentSummary):
    """§10.3 콘텐츠 상세 표준 블록."""

    announcement_date: dt.date | None = None
    promulgation_date: dt.date | None = None
    application_start: dt.date | None = None
    body: dict = Field(default_factory=dict)
    sources: list[PublicSourceOut] = Field(default_factory=list)
    evidence_fields: list[str] = Field(default_factory=list)
    reviewed: bool = True
    """공개 콘텐츠는 전부 전문가 검수를 거친다 (게이트 G6, §1.3)."""


class PublicFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PublicContentSummary]
    total: int
    next_cursor: str | None = None


def _summary(content: TaxContent) -> PublicContentSummary:
    return PublicContentSummary(
        id=content.id,
        title=content.title,
        one_line_summary=content.one_line_summary,
        legal_status=content.legal,
        status_label=STATUS_LABEL[content.legal],
        status_caveat=STATUS_CAVEAT.get(content.legal),
        is_confirmed=content.legal.is_confirmed,
        risk_level=content.risk,
        effective_date=content.effective_date,
        application_end=content.application_end,
        corrected=content.workflow is WorkflowStatus.CORRECTED,
        updated_at=content.updated_at,
    )


def _public_query(tenant_id: UUID | None = None):
    """공개 콘텐츠만 고르는 기본 쿼리.

    tenant_id 가 NULL 인 콘텐츠는 전체 공용이다 (§7.4 D-04).
    """
    stmt = select(TaxContent).where(TaxContent.workflow.in_(PUBLIC_STATES))
    if tenant_id is None:
        return stmt.where(TaxContent.tenant_id.is_(None))
    return stmt.where(
        or_(TaxContent.tenant_id.is_(None), TaxContent.tenant_id == tenant_id)
    )


@router.get("/feed", response_model=PublicFeed)
def public_feed(
    db: DbSession,
    q: Annotated[str | None, Query(description="제목·요약 키워드")] = None,
    legal_status: Annotated[list[LegalStatus] | None, Query()] = None,
    risk_level: Annotated[list[RiskLevel] | None, Query()] = None,
    effective_from: Annotated[dt.date | None, Query()] = None,
    effective_to: Annotated[dt.date | None, Query()] = None,
    deadline_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    tenant_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    today: Annotated[dt.date | None, Query(include_in_schema=False)] = None,
) -> PublicFeed:
    """오늘의 브리핑 목록 (U-02). 인증 없이 호출할 수 있다."""
    today = today or dt.datetime.now(dt.UTC).date()
    stmt = _public_query(tenant_id)

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(TaxContent.title.ilike(pattern), TaxContent.one_line_summary.ilike(pattern))
        )
    if legal_status:
        stmt = stmt.where(TaxContent.legal.in_(legal_status))
    if risk_level:
        stmt = stmt.where(TaxContent.risk.in_(risk_level))
    if effective_from:
        stmt = stmt.where(TaxContent.effective_date >= effective_from)
    if effective_to:
        stmt = stmt.where(TaxContent.effective_date <= effective_to)
    if deadline_within_days is not None:
        horizon = today + dt.timedelta(days=deadline_within_days)
        stmt = stmt.where(
            TaxContent.application_end.is_not(None),
            TaxContent.application_end >= today,
            TaxContent.application_end <= horizon,
        )

    total = len(db.execute(stmt).scalars().all())

    # 중요도 → 마감 임박 → 최신 순 (FR-USR-001).
    ordered = stmt.order_by(
        TaxContent.risk.desc(),
        TaxContent.application_end.asc().nullslast(),
        TaxContent.updated_at.desc(),
    ).limit(limit).offset(offset)

    items = [_summary(c) for c in db.execute(ordered).scalars()]
    next_cursor = str(offset + limit) if offset + limit < total else None
    return PublicFeed(items=items, total=total, next_cursor=next_cursor)


@router.get("/contents/{content_id}", response_model=PublicContentDetail)
def public_content(content_id: UUID, db: DbSession) -> PublicContentDetail:
    """콘텐츠 상세 (U-03). 공식 출처를 접지 않고 그대로 노출한다 (§10.4)."""
    content = db.execute(
        select(TaxContent).where(
            TaxContent.id == content_id,
            TaxContent.workflow.in_(PUBLIC_STATES),
        )
    ).scalar_one_or_none()

    if content is None:
        # 존재하지만 미공개인 경우와 없는 경우를 구분하지 않는다.
        raise NotFoundError("콘텐츠를 찾을 수 없습니다.", {"content_id": str(content_id)})

    detail = PublicContentDetail(
        **_summary(content).model_dump(),
        announcement_date=content.announcement_date,
        promulgation_date=content.promulgation_date,
        application_start=content.application_start,
        body=_body_of(db, content),
        sources=_sources_of(db, content),
        evidence_fields=_evidence_fields_of(db, content),
    )
    return detail


def _body_of(db: Session, content: TaxContent) -> dict:
    if content.current_version_id is None:
        return {}
    version = db.get(ContentVersion, content.current_version_id)
    return version.body if version else {}


def _sources_of(db: Session, content: TaxContent) -> list[PublicSourceOut]:
    rows = db.execute(
        select(ContentSource, RawContent, Source)
        .join(RawContentVersion, ContentSource.raw_content_version_id == RawContentVersion.id)
        .join(RawContent, RawContentVersion.raw_content_id == RawContent.id)
        .join(Source, RawContent.source_id == Source.id)
        .where(ContentSource.tax_content_id == content.id)
    ).all()

    return [
        PublicSourceOut(
            publisher=raw.publisher,
            title=raw.title,
            url=raw.canonical_url,
            authority=src.authority.value,
            role=cs.role,
            published_at=raw.published_at,
        )
        for cs, raw, src in rows
    ]


def _evidence_fields_of(db: Session, content: TaxContent) -> list[str]:
    rows = db.execute(
        select(ContentEvidence.field_name).where(
            ContentEvidence.tax_content_id == content.id
        )
    ).scalars()
    return sorted(set(rows))
