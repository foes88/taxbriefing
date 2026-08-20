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
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session, noload

from app.api.deps import ReadSession
from app.core.errors import NotFoundError, ValidationFailedError
from app.domain import industry, tax_calendar
from app.domain.enums import ContentKind, LegalStatus, RiskLevel, WorkflowStatus
from app.domain.news_topic import LIKE_PATTERNS
from app.domain.share import build_deadline_text, build_share_text
from app.models.tables import (
    ContentEvidence,
    ContentSource,
    ContentVersion,
    RawContent,
    RawContentVersion,
    Source,
    TaxContent,
)
from app.services.render.telegram import STATUS_LABEL, caveat_for

router = APIRouter(prefix="/public", tags=["Public"])

#: 표시 시간대 (§8.1). 저장은 UTC, 판단은 한국 시각이다.
_SEOUL = ZoneInfo("Asia/Seoul")

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
    #: 서버가 확정한 표시 라벨. 프론트에서 다시 만들지 않는다 (§10.4).
    #: 심판례·해석례는 None — 정책 상태라는 것이 없다.
    status_label: str | None = None
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
    #: 법령인가 심판례인가 (POLICY / TRIBUNAL / INTERPRETATION / BILL / SUPPORT).
    #: 화면이 시행일·상태 배지를 붙일지 말지 이 값으로 정한다.
    content_kind: str = "POLICY"
    #: 심판례 결론 — 인용 / 일부인용 / 기각 / 각하 / 재조사. 법령은 None.
    #: 화면이 제목에서 뽑아 쓰던 값이다. 수집기 버전에 따라 "— 기각" 과
    #: "(기각)" 이 섞이면서 결론 필터가 전부 0 이 됐다.
    outcome: str | None = None
    #: 주 근거 원문 주소.
    #:
    #: 법령해석처럼 **본문이 없는 종류**는 화면이 우리 상세를 거치지 않고
    #: 여기로 바로 보낸다. 제목과 링크뿐인 화면을 한 번 더 열게 하는 것은
    #: 헛걸음이다. 다른 종류에는 붙이지 않는다 — 목록 한 번에 원문 조인을
    #: 걸 이유가 없다.
    source_url: str | None = None
    #: 달라지는 것이나 할 일이 하나라도 있는가.
    #:
    #: "먼저 볼 것"에 올릴지 판단하는 데 쓴다. 실질 변경이 없는 개정도
    #: 기록으로는 남겨야 하지만, 오늘 먼저 볼 것은 아니다.
    actionable: bool = True
    #: 의견 제출 마감 (입법예고만).
    #:
    #: 화면이 오늘 기준으로 며칠 남았는지 센다. 요약 문장에만 두면
    #: 기한이 지난 뒤에도 「8월 20일까지입니다」 가 그대로 떠 있는다.
    comment_deadline: dt.date | None = None


class PublicContentDetail(PublicContentSummary):
    """§10.3 콘텐츠 상세 표준 블록."""

    announcement_date: dt.date | None = None
    promulgation_date: dt.date | None = None
    application_start: dt.date | None = None
    body: dict = Field(default_factory=dict)
    #: 사장님에게 그대로 보낼 짧은 글.
    #:
    #: 세무사무소 직원이 이 화면을 보고 고객에게 카톡으로 옮겨 적는다.
    #: 그 옮겨 적는 일을 대신한다. **여기서 모델을 다시 돌리지 않는다** —
    #: 검수를 통과한 문장을 검수 안 거친 문장으로 바꿔서 우리 화면보다
    #: 더 멀리 보내는 셈이 된다. 고르고 자르기만 한다.
    share_text: str = ""
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


#: 정책 진행 상태를 갖는 종류.
#:
#: 심판례와 해석례는 제도가 아니라 **이미 끝난 한 건의 판단**이다.
#: 진행 단계라는 것이 없는데도 상태를 붙였더니 API 가 이렇게 내려갔다.
#:
#:     legal_status  UNKNOWN
#:     status_label  "상태 확인 필요"
#:     status_caveat "확정 아님"
#:
#: 세 줄 다 틀렸다. 확인이 필요한 게 아니라 확인할 것이 없고, 확정이
#: 아닌 게 아니라 이미 확정된 결정이다. 법안(BILL)은 다르다 —
#: 발의·통과라는 진행이 실제로 있다.
KINDS_WITH_STATUS = frozenset(
    {ContentKind.POLICY.value, ContentKind.BILL.value, ContentKind.SUPPORT.value}
)


def _actionable(body: dict | None) -> bool:
    """달라지는 것이나 할 일이 하나라도 있는가.

    AI 는 실질 변경이 없으면 changes 를 빈 배열로 둔다(프롬프트가 그렇게 시킨다).
    자구 정리나 인용 조문 번호만 바뀐 개정이 여기 해당한다.

    그런 건이 "먼저 볼 것" 1번에 올라간 적이 있다. 사장님이 화면을 열자마자
    보는 문장이 "사업자에게 실질적인 변경사항은 없습니다" 였다.
    """
    if not isinstance(body, dict):
        return True
    return bool(body.get("changes")) or bool(body.get("required_actions"))


def _comment_deadline(body: dict | None) -> dt.date | None:
    """입법예고의 의견 제출 마감. 없으면 None — 없는 날짜를 만들지 않는다."""
    raw = (body or {}).get("comment_deadline")
    if not isinstance(raw, str):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _summary(
    content: TaxContent,
    *,
    actionable: bool = True,
    source_url: str | None = None,
    body: dict | None = None,
) -> PublicContentSummary:
    has_status = content.content_kind in KINDS_WITH_STATUS
    return PublicContentSummary(
        id=content.id,
        title=content.title,
        one_line_summary=content.one_line_summary,
        legal_status=content.legal,
        status_label=STATUS_LABEL[content.legal] if has_status else None,
        status_caveat=caveat_for(content.legal, content.effective_date) if has_status else None,
        # 심판례를 "확정 아님" 으로 두면 결정문을 못 믿을 것으로 읽힌다.
        # 확정 여부를 따질 대상이 아니므로 판단하지 않는다.
        is_confirmed=content.legal.is_confirmed if has_status else False,
        risk_level=content.risk,
        effective_date=content.effective_date,
        promulgation_date=content.promulgation_date,
        application_end=content.application_end,
        corrected=content.workflow is WorkflowStatus.CORRECTED,
        updated_at=content.updated_at,
        industries=list(content.industries or []),
        industry_labels=[industry.label(code) for code in (content.industries or [])],
        content_kind=content.content_kind,
        outcome=content.outcome,
        source_url=source_url,
        actionable=actionable,
        comment_deadline=_comment_deadline(body),
    )


def _business_relevant(stmt):
    """기관 내부 문서를 뺀다.

    수집 대상에 국세청·재정경제부 행정규칙이 들어 있는데, 그중 상당수가
    "고문변호사 운영규정", "인사관리규정", "국제기구 인턴 파견 규정" 같은
    기관 내부 문서다. 사장님이 볼 화면에 섞이면 진짜 개정이 묻힌다.

    **숨김은 규칙(is_internal_document)이 붙인 INTERNAL 표시로만 판단한다.**

    전에는 "AI 가 업종을 하나도 못 붙였으면 숨긴다"였다. 그 결과 이런 것들이
    화면에서 사라졌다.

        증권거래세법 시행규칙 — 증권거래세 0→5/10,000 인상
        부가가치세법 시행규칙 — 세금계산서 발급 대상 추가
        국민연금법          — 노령연금 감액 기준 변경

    세율 인상이 세무 브리핑에서 안 보이는 것보다 나쁜 결함은 없다.
    모델의 일은 **태그를 다는 것**이지 콘텐츠를 지우는 것이 아니다.
    업종을 못 붙였으면 태그 없이 보이면 된다.
    """
    return stmt.where(
        ~TaxContent.industries.contains([industry.Industry.INTERNAL.value])
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
    db: ReadSession,
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
def public_industries(db: ReadSession) -> list[IndustryBucket]:
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
            # INTERNAL 은 업종이 아니라 숨김 표시다. 필터 버튼으로 나오면 안 된다.
            unnested.c.value != industry.Industry.INTERNAL.value,
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
    db: ReadSession,
    q: Annotated[str | None, Query(description="제목·요약 키워드")] = None,
    legal_status: Annotated[list[LegalStatus] | None, Query()] = None,
    risk_level: Annotated[list[RiskLevel] | None, Query()] = None,
    industries: Annotated[list[str] | None, Query(description="업종 코드")] = None,
    content_kind: Annotated[
        list[str] | None, Query(description="POLICY / TRIBUNAL / INTERPRETATION / BILL / SUPPORT")
    ] = None,
    outcome: Annotated[
        str | None, Query(description="심판례 결론 — 인용 / 일부인용 / 기각 / 각하 / 재조사")
    ] = None,
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
    if outcome:
        # 심판례 결론. 컬럼으로 두었기에 서버가 거르고, 그래서 total 이 맞는다.
        stmt = stmt.where(TaxContent.outcome == outcome)
    if content_kind:
        stmt = stmt.where(TaxContent.content_kind.in_(content_kind))
    else:
        # **기본은 법령만.** 심판례와 법령을 한 목록에 섞으면 "제도가 바뀌었다"와
        # "이런 사례가 있었다"가 구분되지 않는다. 심판례는 /tips 가 따로 보여준다.
        stmt = stmt.where(TaxContent.content_kind == ContentKind.POLICY.value)
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

    # **왕복 횟수가 곧 체감 속도다.**
    #
    # DB 가 미국(Neon us-east-2)이고 화면을 여는 사람은 한국에 있다.
    # 왕복 한 번에 393ms 다. 쿼리가 몇 개인지가 그대로 초 단위로 나온다.
    # 실제로 찾기 화면이 5개 쿼리에 4.9초였다.
    #
    #     415ms  count(*)
    #     418ms  tax_contents
    #     208ms  content_sources    ← 이 목록은 안 쓴다
    #     210ms  content_evidence   ← 이 목록은 안 쓴다
    #     211ms  content_versions
    #
    # 뒤의 둘은 TaxContent 의 관계가 lazy="selectin" 이라 자동으로 딸려
    # 온 것이다. 상세 화면에는 필요하지만 목록에는 한 글자도 안 쓰인다.
    # 끊는다.
    #
    # 세는 쿼리도 따로 돌 이유가 없다. 창 함수는 LIMIT 이 걸리기 전에
    # 계산되므로 한 번에 같이 가져올 수 있다.
    ordered = (
        stmt.order_by(
            TaxContent.risk.desc(),
            TaxContent.application_end.asc().nullslast(),
            TaxContent.updated_at.desc(),
        )
        .options(noload(TaxContent.sources), noload(TaxContent.evidence))
        .add_columns(func.count().over().label("total"))
        # 본문도 같이 끌고 온다. 콘텐츠 하나에 현재 버전은 하나뿐이라
        # 줄 수가 늘지 않는다. 따로 물으면 그것만으로 왕복 한 번이다.
        .outerjoin(ContentVersion, ContentVersion.id == TaxContent.current_version_id)
        .add_columns(ContentVersion.body)
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(ordered).all()
    contents = [row[0] for row in rows]
    total = rows[0][1] if rows else 0
    bodies: dict[UUID, dict] = {
        row[0].current_version_id: (row[2] if isinstance(row[2], dict) else {})
        for row in rows
        if row[0].current_version_id
    }

    # 빈 쪽이 나왔는데 그게 첫 쪽이 아니면, 창 함수는 셀 것이 없어 0 을
    # 준다. 그건 "조건에 맞는 게 없다" 가 아니라 "이 쪽에 없다" 다.
    # 건수를 0 이라고 말하면 거짓이므로 그때만 따로 센다.
    if not rows and offset:
        total = db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ).scalar_one()

    # 본문 없는 종류(법령해석)만 원문 주소를 같이 싣는다. 화면이 우리
    # 상세를 거치지 않고 바로 원문으로 보내야 하기 때문이다.
    linkable = [
        c.id
        for c in contents
        if c.content_kind in (ContentKind.INTERPRETATION.value, ContentKind.PRECEDENT.value)
    ]
    urls: dict[UUID, str] = {}
    if linkable:
        urls = dict(
            db.execute(
                select(ContentSource.tax_content_id, RawContent.canonical_url)
                .join(
                    RawContentVersion,
                    ContentSource.raw_content_version_id == RawContentVersion.id,
                )
                .join(RawContent, RawContentVersion.raw_content_id == RawContent.id)
                .where(ContentSource.tax_content_id.in_(linkable))
            ).all()
        )

    items = [
        _summary(
            c,
            actionable=_actionable(bodies.get(c.current_version_id)),
            source_url=urls.get(c.id),
            body=bodies.get(c.current_version_id),
        )
        for c in contents
    ]
    next_cursor = str(offset + limit) if offset + limit < total else None
    return PublicFeed(items=items, total=total, next_cursor=next_cursor)


#: 뉴스 탭에 나오는 출처 등급. A·B 는 공식 원문이므로 검수 경로로만 나간다.
#: 등급으로 가르는 이유는 그게 실제 구분이기 때문이다 — "공식이냐 보도냐".
NEWS_GRADES = ("C", "D")


class DeadlineOut(BaseModel):
    """세무 일정 한 건."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    title: str
    note: str
    audience: str
    audience_label: str
    basis: str
    """근거 조문. **출처 없는 날짜는 싣지 않는다.**"""

    shifted: bool
    """주말이라 다음 월요일로 민 것인가."""

    days_left: int


@router.get("/calendar", response_model=list[DeadlineOut])
def public_calendar(
    within_days: Annotated[int, Query(ge=1, le=365, description="며칠 안의 마감일")] = 90,
    today: Annotated[dt.date | None, Query(include_in_schema=False)] = None,
) -> list[DeadlineOut]:
    """신고·납부 마감일.

    **DB 를 보지 않는다.** 날짜가 법에 정해져 있어 수집할 것도, 모델에게
    물어볼 것도 없다. 기한을 하루 틀리면 가산세가 붙으므로 지어낼 여지를
    아예 두지 않는다.

    개별 사업자의 기한은 과세유형·결산월·반기납부 여부에 따라 다르다.
    여기 나오는 것은 일반 일정이고, 화면도 그렇게 말한다.
    """
    # 마감일은 한국 시각 기준이다. UTC 로 재면 하루가 어긋나는 날이 생긴다.
    base = today or dt.datetime.now(dt.UTC).astimezone(_SEOUL).date()
    return [
        DeadlineOut(
            date=item.date,
            title=item.title,
            note=item.note,
            audience=item.audience.value,
            audience_label=tax_calendar.LABEL[item.audience],
            basis=item.basis,
            shifted=item.shifted,
            days_left=(item.date - base).days,
        )
        for item in tax_calendar.upcoming(base, within_days=within_days)
    ]


@router.get("/news", response_model=NewsFeed)
def public_news(
    db: ReadSession,
    q: Annotated[str | None, Query(description="제목 키워드")] = None,
    days: Annotated[int, Query(ge=1, le=365, description="최근 N일")] = 30,
    all_topics: Annotated[
        bool, Query(description="세무 무관 기사도 포함. 기본은 세무 기사만")
    ] = False,
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
    if not all_topics:
        # **세무 낱말이 하나도 없는 제목은 뺀다.**
        #
        # 세무 전문지 RSS 라도 기업 홍보와 지역 행사가 섞여 들어온다.
        # 112건 중 39건(34%)이 그랬다. 셋 중 하나가 "게임소통학교 성료"
        # 면 며칠 만에 이 탭을 안 열게 된다.
        #
        # 파이썬이 아니라 SQL 로 거른다. 불러온 다음에 거르면 "112건"
        # 이라고 써 놓고 40건만 보여주게 된다.
        stmt = stmt.where(
            or_(*[RawContent.title.ilike(pattern) for pattern in LIKE_PATTERNS])
        )
    if q:
        stmt = stmt.where(RawContent.title.ilike(f"%{q}%"))

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
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


class SharePlan(BaseModel):
    """카톡으로 돌릴 「챙기실 것」 한 장."""

    text: str
    deadline_count: int
    change_count: int
    #: 업종 건 수. 0 이면 화면이 "이 업종으로 잡힌 건이 아직 없습니다" 를 띄운다.
    industry_count: int = 0


@router.get("/share/deadlines", response_model=SharePlan)
def public_share_deadlines(
    db: ReadSession,
    within_days: Annotated[int, Query(ge=1, le=180)] = 45,
    industry_code: Annotated[str | None, Query(alias="industry")] = None,
    today: Annotated[dt.date | None, Query(include_in_schema=False)] = None,
) -> SharePlan:
    """사업주에게 그대로 돌릴 안내문.

    **업종별로 못 만든다. 아직은.** 사장님 대부분이 음식점인데 콘텐츠
    325건 중 278건이 업종 미분류이고 「요식·음식점」 으로 잡힌 것은 0건이다.
    골라낼 것이 없는데 골라낸 척하면 빈 안내가 나간다.

    대신 마감 일정으로 만든다. 음식점이든 학원이든 똑같이 걸리고, 날짜가
    법에 정해져 있어 지어낼 여지가 없다.
    """
    base = today or dt.datetime.now(dt.UTC).astimezone(_SEOUL).date()
    horizon = base + dt.timedelta(days=within_days)

    deadlines = [
        {
            "date": item.date.isoformat(),
            "title": item.title,
            "audience_label": tax_calendar.LABEL[item.audience],
        }
        for item in tax_calendar.upcoming(base, within_days=within_days)
    ]

    # 이번 기간에 시행되는 **확정된** 개정만. 예고는 넣지 않는다 —
    # 무산될 수 있는 것을 "새로 정해진 것" 아래 두면 거짓이 된다.
    rows = db.execute(
        select(TaxContent.title, TaxContent.effective_date)
        .where(
            TaxContent.workflow.in_(PUBLIC_STATES),
            TaxContent.tenant_id.is_(None),
            TaxContent.content_kind == ContentKind.POLICY.value,
            TaxContent.legal != LegalStatus.PREANNOUNCED,
            TaxContent.effective_date.is_not(None),
            TaxContent.effective_date >= base,
            TaxContent.effective_date <= horizon,
            ~TaxContent.industries.contains([industry.Industry.INTERNAL.value]),
        )
        .order_by(TaxContent.effective_date.asc())
        # 카톡 한 화면을 넘기지 않게. 넘치는 것은 사이트에서 본다.
        .limit(3)
    ).all()
    changes = [{"title": t, "effective_date": d.isoformat()} for t, d in rows]

    # 업종 건.
    #
    # **예고는 넣지 않는다.** 무산될 수 있는 것을 「우리 업종 건」 아래
    # 두면 이미 정해진 것으로 읽힌다. 심판례·해석례는 넣는다 — 음식점
    # 사장님에게 값이 있는 것이 대개 거기다.
    industry_items: list[str] = []
    industry_name: str | None = None
    if industry_code:
        industry_name = industry.label(industry_code)
        industry_items = list(
            db.execute(
                select(TaxContent.title)
                .where(
                    TaxContent.workflow.in_(PUBLIC_STATES),
                    TaxContent.tenant_id.is_(None),
                    TaxContent.legal != LegalStatus.PREANNOUNCED,
                    TaxContent.industries.contains([industry_code]),
                )
                .order_by(TaxContent.updated_at.desc())
                .limit(3)
            ).scalars()
        )

    return SharePlan(
        text=build_deadline_text(
            today=base,
            deadlines=deadlines,
            changes=changes,
            industry_label=industry_name,
            industry_items=industry_items,
        ),
        deadline_count=len(deadlines),
        change_count=len(changes),
        industry_count=len(industry_items),
    )


@router.get("/contents/{content_id}", response_model=PublicContentDetail)
def public_content(content_id: UUID, db: ReadSession) -> PublicContentDetail:
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

    body = _body_of(db, content)
    sources = _sources_of(db, content)
    detail = PublicContentDetail(
        # promulgation_date 는 요약에 이미 들어 있다.
        **_summary(content, actionable=_actionable(body), body=body).model_dump(),
        announcement_date=content.announcement_date,
        application_start=content.application_start,
        body=body,
        share_text=build_share_text(
            title=content.title,
            summary=content.one_line_summary,
            body=body,
            effective_date=content.effective_date,
            comment_deadline=_comment_deadline(body),
            preannounced=content.legal is LegalStatus.PREANNOUNCED,
            source_url=sources[0].url if sources else None,
        ),
        sources=sources,
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
