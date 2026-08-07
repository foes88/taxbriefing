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
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.core.errors import NotFoundError, ValidationFailedError
from app.domain import industry
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
    #: 월 묶음이 공포월 기준이므로 목록에서도 함께 보여준다.
    #: 없으면 "5월 목록인데 왜 7월?" 이라는 혼란이 생긴다.
    promulgation_date: dt.date | None = None
    application_end: dt.date | None = None
    corrected: bool = False
    updated_at: dt.datetime
    #: 업종 코드와 화면용 이름. 상담 참고용 색인이지 적용 판정이 아니다.
    industries: list[str] = Field(default_factory=list)
    industry_labels: list[str] = Field(default_factory=list)


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


class NewsItemOut(BaseModel):
    """언론 보도 한 건. **공식 원문이 아니다.**

    검수를 거친 콘텐츠(`PublicContentSummary`)와 이름도 필드도 일부러 다르게 뒀다.
    화면에서 둘을 섞어 쓸 수 없어야 한다.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    url: str
    publisher: str
    """언론사가 아니라 수집 출처명이다 (예: "네이버 뉴스 검색")."""
    summary: str | None = None
    published_at: dt.datetime | None = None
    authority: str
    matched_query: str | None = None


class NewsFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NewsItemOut]
    total: int
    #: 화면 상단 경고 문구. 서버가 내려보내야 프론트가 지우기 어렵다.
    caveat: str = (
        "아래는 언론 보도입니다. 공식 원문으로 확인되지 않았으며 "
        "확정된 제도 변경이 아닐 수 있습니다."
    )


class MonthBucket(BaseModel):
    """월별 아카이브 항목. 공포월 기준이다 — 사업자가 "몇 월 개정"으로 기억하기 때문이다."""

    model_config = ConfigDict(extra="forbid")

    month: str
    """YYYY-MM"""
    label: str
    """"2026년 7월" """
    count: int
    important: int
    """HIGH·CRITICAL 건수. 그 달을 열어볼지 판단하는 신호다."""


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
        promulgation_date=content.promulgation_date,
        application_end=content.application_end,
        corrected=content.workflow is WorkflowStatus.CORRECTED,
        updated_at=content.updated_at,
        industries=list(content.industries or []),
        industry_labels=[industry.label(code) for code in (content.industries or [])],
    )


def _business_relevant(stmt):
    """사업자와 무관하다고 **판단된** 건을 뺀다.

    수집 대상에 국세청·재정경제부 행정규칙이 들어 있는데, 그중 상당수가
    "고문변호사 운영규정", "기간제 근로자 인사관리규정", "국제기구 인턴 파견
    규정" 같은 기관 내부 문서다. 사장님이 볼 화면에 이런 게 섞이면 진짜
    개정이 묻힌다.

    조건이 두 개인 이유: `industries = []` 하나만 보면 **아직 분류하지 않은**
    건까지 숨는다. `search_text` 는 분류가 성공했을 때만 채워지므로,
    둘을 같이 봐야 "판단해보니 무관"만 걸러진다. 분류 실패나 미분류는
    그대로 보인다 — 판단을 못 한 것을 없는 것처럼 다루지 않는다.
    """
    return stmt.where(
        ~(TaxContent.search_text.is_not(None) & (TaxContent.industries == []))
    )


def _public_query(tenant_id: UUID | None = None):
    """공개 콘텐츠만 고르는 기본 쿼리.

    tenant_id 가 NULL 인 콘텐츠는 전체 공용이다 (§7.4 D-04).
    """
    stmt = _business_relevant(select(TaxContent).where(TaxContent.workflow.in_(PUBLIC_STATES)))
    if tenant_id is None:
        return stmt.where(TaxContent.tenant_id.is_(None))
    return stmt.where(
        or_(TaxContent.tenant_id.is_(None), TaxContent.tenant_id == tenant_id)
    )


def _month_range(month: str) -> tuple[dt.date, dt.date]:
    """`2026-07` → (2026-07-01, 2026-08-01)."""
    try:
        year, mon = (int(part) for part in month.split("-", 1))
        start = dt.date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise ValidationFailedError(
            "month 는 YYYY-MM 형식이어야 합니다.", {"month": month}
        ) from exc
    end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
    return start, end


@router.get("/months", response_model=list[MonthBucket])
def public_months(
    db: DbSession,
    tenant_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=36)] = 18,
) -> list[MonthBucket]:
    """월별 아카이브 (공포월 기준). 인증 없이 호출할 수 있다."""
    bucket = func.to_char(TaxContent.promulgation_date, "YYYY-MM")
    stmt = _business_relevant(
        select(
            bucket.label("month"),
            func.count().label("count"),
            func.count()
            .filter(TaxContent.risk.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
            .label("important"),
        ).where(
            TaxContent.workflow.in_(PUBLIC_STATES),
            TaxContent.promulgation_date.is_not(None),
        )
    ).group_by(bucket).order_by(bucket.desc()).limit(limit)
    stmt = stmt.where(
        TaxContent.tenant_id.is_(None)
        if tenant_id is None
        else or_(TaxContent.tenant_id.is_(None), TaxContent.tenant_id == tenant_id)
    )

    out: list[MonthBucket] = []
    for month, count, important in db.execute(stmt).all():
        year, mon = month.split("-")
        out.append(
            MonthBucket(
                month=month,
                label=f"{year}년 {int(mon)}월",
                count=count,
                important=important,
            )
        )
    return out


class IndustryBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    count: int


@router.get("/industries", response_model=list[IndustryBucket])
def public_industries(db: DbSession) -> list[IndustryBucket]:
    """업종 목록과 건수.

    분류표 전체가 아니라 **실제로 게시된 건이 있는 업종만** 준다.
    0건짜리 버튼을 눌러 빈 화면을 보는 일이 없어야 한다.
    """
    # 배열을 행으로 편다. lateral 조인이라 명시적으로 붙여야 한다 —
    # 안 붙이면 SQLAlchemy 가 교차곱을 만들고 건수가 부풀려진다.
    unnested = func.jsonb_array_elements_text(TaxContent.industries).table_valued("value")
    stmt = (
        select(unnested.c.value, func.count().label("count"))
        .select_from(TaxContent)
        .join(unnested, true())
        .where(
            TaxContent.workflow.in_(PUBLIC_STATES),
            TaxContent.tenant_id.is_(None),
        )
        .group_by(unnested.c.value)
    )

    order = {item.value: index for index, item in enumerate(industry.Industry)}
    rows = [
        IndustryBucket(code=value, label=industry.label(value), count=count)
        for value, count in db.execute(stmt).all()
    ]
    # 건수가 아니라 분류표 순서로 낸다. 필터 버튼의 자리가 매일 바뀌면
    # "아까 여기 있었는데" 하고 눈으로 찾게 된다.
    rows.sort(key=lambda bucket: order.get(bucket.code, 999))
    return rows


@router.get("/feed", response_model=PublicFeed)
def public_feed(
    db: DbSession,
    q: Annotated[str | None, Query(description="제목·요약 키워드")] = None,
    legal_status: Annotated[list[LegalStatus] | None, Query()] = None,
    risk_level: Annotated[list[RiskLevel] | None, Query()] = None,
    industries: Annotated[list[str] | None, Query(description="업종 코드")] = None,
    month: Annotated[str | None, Query(description="공포월 YYYY-MM")] = None,
    promulgated_from: Annotated[dt.date | None, Query(description="공포일 시작")] = None,
    promulgated_to: Annotated[dt.date | None, Query(description="공포일 종료")] = None,
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

    if month:
        start, end = _month_range(month)
        stmt = stmt.where(
            TaxContent.promulgation_date >= start,
            TaxContent.promulgation_date < end,
        )

    # 기간 검색은 공포일 기준이다. 사업자는 "언제 나온 개정인가"로 찾는다.
    if promulgated_from:
        stmt = stmt.where(TaxContent.promulgation_date >= promulgated_from)
    if promulgated_to:
        stmt = stmt.where(TaxContent.promulgation_date <= promulgated_to)

    if q:
        # 제목·요약만 검색하면 "학원 4대보험" 같은 실무 질문이 안 걸린다.
        # 정작 답은 개정 내용과 사업자 할 일에 들어 있고, 그건 search_text 에 있다.
        # 아직 search_text 가 안 채워진 콘텐츠도 있으므로 제목·요약도 함께 본다.
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                TaxContent.title.ilike(pattern),
                TaxContent.one_line_summary.ilike(pattern),
                TaxContent.search_text.ilike(pattern),
            )
        )
    if industries:
        # 어느 하나라도 겹치면 나온다. "요식업과 학원 둘 다 해당" 을 요구하면
        # 상담 중에 찾으려던 건이 사라진다.
        stmt = stmt.where(
            or_(*[TaxContent.industries.contains([code]) for code in industries])
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


#: 뉴스 탭에 나오는 출처 등급. A·B 는 공식 원문이므로 검수 경로로만 나간다.
#: 등급으로 가르는 이유는 그게 실제 구분이기 때문이다 — "공식이냐 보도냐".
NEWS_GRADES = ("C", "D")


@router.get("/news", response_model=NewsFeed)
def public_news(
    db: DbSession,
    q: Annotated[str | None, Query(description="제목 키워드")] = None,
    days: Annotated[int, Query(ge=1, le=365, description="최근 N일")] = 30,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NewsFeed:
    """언론 보도 목록.

    검수를 거치지 않은 항목이므로 **제목·링크·짧은 요약만** 내려보낸다.
    본문은 애초에 저장하지 않았다 (§NFR-015).
    """
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)

    stmt = (
        select(RawContent, RawContentVersion, Source)
        .join(Source, RawContent.source_id == Source.id)
        .outerjoin(RawContentVersion, RawContent.current_version_id == RawContentVersion.id)
        .where(
            Source.authority.in_(NEWS_GRADES),
            RawContent.status == "ACTIVE",
            # 날짜를 모르는 항목은 뉴스 탭에 올리지 않는다. 최신순 정렬이 무의미해지고,
            # 사업자가 오래된 기사를 오늘 소식으로 오해한다.
            RawContent.published_at.is_not(None),
            RawContent.published_at >= since,
        )
    )
    if q:
        stmt = stmt.where(RawContent.title.ilike(f"%{q}%"))

    total = len(db.execute(stmt).all())
    rows = db.execute(
        stmt.order_by(RawContent.published_at.desc()).limit(limit).offset(offset)
    ).all()

    return NewsFeed(
        items=[
            NewsItemOut(
                id=raw.id,
                title=raw.title,
                url=raw.canonical_url,
                publisher=raw.publisher,
                summary=(version.doc_metadata or {}).get("summary") if version else None,
                published_at=raw.published_at,
                authority=source.authority.value,
                matched_query=(version.doc_metadata or {}).get("matched_query")
                if version
                else None,
            )
            for raw, version, source in rows
        ],
        total=total,
    )


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
        # promulgation_date 는 요약에 이미 들어 있다.
        **_summary(content).model_dump(),
        announcement_date=content.announcement_date,
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
