"""콘텐츠 생성·편집·검수 서비스 (§4.3, §4.5).

게이트 평가에 필요한 GateContext 를 DB 상태에서 조립하는 것이 이 모듈의 핵심 책임이다.
게이트 판정 자체는 app.domain.gates 의 순수 함수가 담당한다.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, GateFailedError, NotFoundError, ValidationFailedError
from app.domain import gates
from app.domain.confidence import score as compute_score
from app.domain.enums import (
    LegalStatus,
    ReviewDecision,
    RiskLevel,
    SourceRole,
    WorkflowStatus,
)
from app.domain.workflow import apply_edit, can_transition, status_after_review
from app.models.tables import (
    ContentEvidence,
    ContentSource,
    ContentVersion,
    RawContent,
    RawContentVersion,
    Review,
    Source,
    TaxContent,
)


def build_gate_context(db: Session, content: TaxContent) -> gates.GateContext:
    """DB 상태에서 게이트 판정용 스냅샷을 만든다.

    출처 등급은 raw_content_version → raw_content → source 를 거쳐 얻는다.
    이 조인이 끊기면 모든 근거가 '등급 없음'이 되어 G1 이 실패하므로, 안전한 방향으로 실패한다.
    """
    rows = db.execute(
        select(ContentSource, RawContentVersion, RawContent, Source)
        .join(RawContentVersion, ContentSource.raw_content_version_id == RawContentVersion.id)
        .join(RawContent, RawContentVersion.raw_content_id == RawContent.id)
        .join(Source, RawContent.source_id == Source.id)
        .where(ContentSource.tax_content_id == content.id)
    ).all()

    links = tuple(
        gates.SourceLink(
            source_version_id=cs.raw_content_version_id,
            authority=src.authority,
            role=SourceRole(cs.role),
            source_id=src.id,
        )
        for cs, _rcv, _rc, src in rows
    )

    evidence_rows = db.execute(
        select(ContentEvidence).where(ContentEvidence.tax_content_id == content.id)
    ).scalars().all()
    evidence = tuple(
        gates.EvidenceRef(
            field_name=e.field_name,
            source_version_id=e.raw_content_version_id,
            locator=e.locator,
        )
        for e in evidence_rows
    )

    approved = _has_reviewer_approval(db, content)

    affected = tuple(e.field_name for e in evidence_rows if e.field_name == "affected_users")

    return gates.GateContext(
        sources=links,
        evidence=evidence,
        legal_status=content.legal,
        risk_level=content.risk,
        dates={
            "announcement_date": content.announcement_date,
            "promulgation_date": content.promulgation_date,
            "effective_date": content.effective_date,
            "application_start": content.application_start,
            "application_end": content.application_end,
        },
        affected_users=affected,
        excluded_users=(),
        approved_by_reviewer=approved,
    )


def _has_reviewer_approval(db: Session, content: TaxContent) -> bool:
    """현재 버전에 대한 REVIEWER 승인이 존재하는가.

    '현재 버전'이 핵심이다. 이전 버전의 승인은 재사용하지 않는다 — 그렇지 않으면
    승인 후 내용을 바꾸고 이전 승인으로 발송하는 우회로가 열린다 (AT-07).
    """
    if content.current_version_id is None:
        return False
    review = db.execute(
        select(Review)
        .where(
            Review.tax_content_id == content.id,
            Review.content_version_id == content.current_version_id,
            Review.decision.in_([ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_EDIT]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return review is not None


def refresh_confidence(db: Session, content: TaxContent, *, now: dt.datetime) -> None:
    """신뢰도 점수와 산정 내역을 다시 계산해 저장한다 (FR-VER-005)."""
    ctx = build_gate_context(db, content)
    last_checked = db.execute(
        select(RawContent.last_checked_at)
        .join(RawContentVersion, RawContentVersion.raw_content_id == RawContent.id)
        .join(ContentSource, ContentSource.raw_content_version_id == RawContentVersion.id)
        .where(ContentSource.tax_content_id == content.id)
        .order_by(RawContent.last_checked_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    result = compute_score(ctx, now=now, last_checked_at=last_checked)
    content.source_confidence = result.total
    content.confidence_breakdown = result.as_dict()


def create_content(
    db: Session,
    *,
    title: str,
    source_version_ids: list[UUID],
    policy_cluster_id: UUID | None = None,
    legal_status: LegalStatus = LegalStatus.UNKNOWN,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    body: dict[str, Any] | None = None,
    tenant_id: UUID | None = None,
    created_by: UUID | None = None,
    roles: dict[UUID, SourceRole] | None = None,
    now: dt.datetime | None = None,
) -> TaxContent:
    """가공 콘텐츠 초안을 만든다.

    A-04: 생성 시점에는 원문 확인 전이므로 legal_status 기본값은 UNKNOWN 이다.
    확정은 검수 단계에서 한다.
    """
    now = now or dt.datetime.now(dt.UTC)
    roles = roles or {}

    found = db.execute(
        select(RawContentVersion.id).where(RawContentVersion.id.in_(source_version_ids))
    ).scalars().all()
    missing = set(source_version_ids) - set(found)
    if missing:
        raise ValidationFailedError(
            "존재하지 않는 원문 버전을 근거로 지정했습니다.",
            {"unknown_source_version_ids": [str(m) for m in missing]},
        )

    content = TaxContent(
        tenant_id=tenant_id,
        policy_cluster_id=policy_cluster_id,
        workflow=WorkflowStatus.DETECTED,
        legal=legal_status,
        risk=risk_level,
        title=title,
        created_by=created_by,
    )
    db.add(content)
    db.flush()

    for index, version_id in enumerate(source_version_ids):
        # 역할을 지정하지 않으면 첫 번째 근거를 PRIMARY 로 둔다.
        default_role = SourceRole.PRIMARY if index == 0 else SourceRole.SECONDARY
        db.add(
            ContentSource(
                tax_content_id=content.id,
                raw_content_version_id=version_id,
                role=(roles.get(version_id) or default_role).value,
            )
        )

    version = ContentVersion(
        tax_content_id=content.id,
        version_no=1,
        body=body or {},
        created_by=created_by,
        change_note="초안 생성",
    )
    db.add(version)
    db.flush()
    content.current_version_id = version.id

    # 공식 근거가 연결되었으면 원문성 확인 단계까지 올린다.
    ctx = build_gate_context(db, content)
    content.workflow = (
        WorkflowStatus.SOURCE_CONFIRMED if ctx.official_sources() else WorkflowStatus.UNVERIFIED
    )
    refresh_confidence(db, content, now=now)
    db.flush()
    return content


def get_content(db: Session, content_id: UUID) -> TaxContent:
    content = db.get(TaxContent, content_id)
    if content is None:
        raise NotFoundError("콘텐츠를 찾을 수 없습니다.", {"content_id": str(content_id)})
    return content


def link_source(
    db: Session,
    content: TaxContent,
    *,
    raw_content_version_id: UUID,
    role: SourceRole = SourceRole.SECONDARY,
    verified_by: UUID | None = None,
    now: dt.datetime | None = None,
) -> ContentSource:
    """원문 버전을 콘텐츠에 연결한다 (FR-VER-001, UC-02).

    뉴스로 이슈를 탐지한 뒤 공식 원문을 찾아 붙이는 경로가 이 함수다.
    공식 근거가 붙으면 원문성이 확인된 것이므로 워크플로를 SOURCE_CONFIRMED 로 올린다.
    """
    now = now or dt.datetime.now(dt.UTC)

    if db.get(RawContentVersion, raw_content_version_id) is None:
        raise ValidationFailedError(
            "존재하지 않는 원문 버전입니다.",
            {"raw_content_version_id": str(raw_content_version_id)},
        )

    existing = db.execute(
        select(ContentSource).where(
            ContentSource.tax_content_id == content.id,
            ContentSource.raw_content_version_id == raw_content_version_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    link = ContentSource(
        tax_content_id=content.id,
        raw_content_version_id=raw_content_version_id,
        role=role.value,
        verified_by=verified_by,
        verified_at=now if verified_by else None,
    )
    db.add(link)
    db.flush()

    ctx = build_gate_context(db, content)
    if content.workflow is WorkflowStatus.UNVERIFIED and ctx.official_sources():
        content.workflow = WorkflowStatus.SOURCE_CONFIRMED

    refresh_confidence(db, content, now=now)
    db.flush()
    return link


def add_evidence(
    db: Session,
    content: TaxContent,
    *,
    field_name: str,
    raw_content_version_id: UUID,
    locator: str,
    support_type: str = "DIRECT",
    note: str | None = None,
) -> ContentEvidence:
    """필드별 근거를 연결한다 (FR-VER-004).

    근거로 쓰려면 그 원문 버전이 콘텐츠에 연결되어 있어야 한다.
    연결되지 않은 원문을 근거로 지목하면 추적성이 깨진다.
    """
    linked = db.execute(
        select(ContentSource).where(
            ContentSource.tax_content_id == content.id,
            ContentSource.raw_content_version_id == raw_content_version_id,
        )
    ).scalar_one_or_none()
    if linked is None:
        raise ValidationFailedError(
            "콘텐츠에 연결되지 않은 원문 버전을 근거로 지정할 수 없습니다.",
            {"raw_content_version_id": str(raw_content_version_id)},
        )

    evidence = ContentEvidence(
        tax_content_id=content.id,
        content_version_id=content.current_version_id,
        field_name=field_name,
        raw_content_version_id=raw_content_version_id,
        locator=locator,
        support_type=support_type,
        note=note,
    )
    db.add(evidence)
    db.flush()
    return evidence


_EDITABLE_FIELDS = frozenset(
    {
        "title",
        "one_line_summary",
        "legal_status",
        "risk_level",
        "announcement_date",
        "promulgation_date",
        "effective_date",
        "application_start",
        "application_end",
        "body",
    }
)

_COLUMN_OF = {
    "legal_status": "legal",
    "risk_level": "risk",
}


def update_content(
    db: Session,
    content: TaxContent,
    patch: dict[str, Any],
    *,
    expected_version: int | None = None,
    editor_id: UUID | None = None,
    now: dt.datetime | None = None,
) -> tuple[TaxContent, Any]:
    """콘텐츠를 수정한다.

    승인된 콘텐츠의 보호 필드가 바뀌면 승인이 해제되고 REVIEW_PENDING 으로 돌아간다 (AT-07).
    낙관적 잠금은 If-Match 헤더의 값과 lock_version 을 비교해 수행한다 (§8.1).
    """
    now = now or dt.datetime.now(dt.UTC)

    if expected_version is not None and expected_version != content.lock_version:
        raise ConflictError(
            "다른 사용자가 먼저 수정했습니다. 최신 내용을 불러온 뒤 다시 시도해 주세요.",
            {"expected_version": expected_version, "current_version": content.lock_version},
        )

    unknown = set(patch) - _EDITABLE_FIELDS
    if unknown:
        raise ValidationFailedError(
            "수정할 수 없는 필드가 포함되어 있습니다.",
            {"unknown_fields": sorted(unknown)},
        )

    before = {
        "title": content.title,
        "one_line_summary": content.one_line_summary,
        "legal_status": content.legal.value,
        "risk_level": content.risk.value,
        "announcement_date": content.announcement_date,
        "promulgation_date": content.promulgation_date,
        "effective_date": content.effective_date,
        "application_start": content.application_start,
        "application_end": content.application_end,
        "body": None,
    }

    outcome = apply_edit(current_status=content.workflow, before=before, patch=patch)

    for key, value in patch.items():
        if key == "body":
            continue
        if key == "legal_status":
            content.legal = LegalStatus(value)
        elif key == "risk_level":
            content.risk = RiskLevel(value)
        else:
            setattr(content, key, value)

    if "body" in patch:
        latest = db.execute(
            select(ContentVersion)
            .where(ContentVersion.tax_content_id == content.id)
            .order_by(ContentVersion.version_no.desc())
            .limit(1)
        ).scalar_one()
        new_version = ContentVersion(
            tax_content_id=content.id,
            version_no=latest.version_no + 1,
            body=patch["body"],
            created_by=editor_id,
            change_note="본문 수정",
        )
        db.add(new_version)
        db.flush()
        content.current_version_id = new_version.id

    if outcome.approval_revoked:
        content.workflow = outcome.next_status

    content.lock_version += 1
    refresh_confidence(db, content, now=now)
    db.flush()
    return content, outcome


def submit_for_review(
    db: Session, content: TaxContent, *, now: dt.datetime | None = None
) -> gates.GateReport:
    """검수를 요청한다 (§8.4 A-02).

    G1 이 실패한 콘텐츠는 검수 큐에도 올리지 않는다. 뉴스만 붙은 콘텐츠를
    검수자 앞에 놓으면 승인 실수가 생길 수 있고, 애초에 승인할 수 없는 콘텐츠다 (AT-03).
    """
    now = now or dt.datetime.now(dt.UTC)
    ctx = build_gate_context(db, content)
    report = gates.evaluate(ctx)

    if not report.can_approve:
        raise GateFailedError(
            "검증 게이트를 통과하지 못해 검수 요청을 할 수 없습니다.",
            {
                "failed_gates": list(report.failed_gate_ids()),
                "gate_report": report.as_dict(),
            },
        )

    # G1 통과가 곧 원문성 확인이다. 뉴스로 탐지한 뒤 공식 원문을 연결한 콘텐츠(UC-02)는
    # 여기서 SOURCE_CONFIRMED 로 올라간 뒤 검수 큐로 간다.
    if content.workflow is WorkflowStatus.UNVERIFIED and ctx.official_sources():
        content.workflow = WorkflowStatus.SOURCE_CONFIRMED

    if not can_transition(content.workflow, WorkflowStatus.REVIEW_PENDING):
        raise ConflictError(
            f"'{content.workflow.value}' 상태에서는 검수를 요청할 수 없습니다.",
            {"current_status": content.workflow.value},
        )

    # G3 실패: 근거 없는 날짜를 실제로 지운다 (§9.4 V2).
    for field_name in report.dates_to_nullify:
        setattr(content, field_name, None)

    content.workflow = WorkflowStatus.REVIEW_PENDING
    refresh_confidence(db, content, now=now)
    db.flush()
    return report


def record_review(
    db: Session,
    content: TaxContent,
    *,
    reviewer_id: UUID,
    decision: ReviewDecision,
    review_note: str,
    checked_source_version_ids: list[UUID],
    legal_status: LegalStatus | None = None,
    risk_level: RiskLevel | None = None,
    now: dt.datetime | None = None,
) -> tuple[Review, gates.GateReport]:
    """검수 결과를 기록한다 (FR-CMS-003).

    승인 전에 게이트를 다시 평가한다. 검수 요청 이후 원문이나 근거가 바뀌었을 수 있고,
    승인은 되돌리기 가장 비싼 행위이기 때문이다.
    """
    now = now or dt.datetime.now(dt.UTC)

    if content.current_version_id is None:
        raise ValidationFailedError("검수할 콘텐츠 버전이 없습니다.")

    if not checked_source_version_ids:
        raise ValidationFailedError(
            "확인한 원문 버전을 최소 1개 이상 지정해야 합니다 (AT-12 추적성)."
        )

    # A-01: 검수자가 확인했다고 주장한 원문 버전이 실제로 이 콘텐츠에 연결되어 있는가.
    linked = set(
        db.execute(
            select(ContentSource.raw_content_version_id).where(
                ContentSource.tax_content_id == content.id
            )
        ).scalars()
    )
    unlinked = set(checked_source_version_ids) - linked
    if unlinked:
        raise ValidationFailedError(
            "콘텐츠에 연결되지 않은 원문 버전을 '확인함'으로 기록할 수 없습니다.",
            {"unlinked_source_version_ids": [str(u) for u in unlinked]},
        )

    if legal_status is not None:
        content.legal = legal_status
    if risk_level is not None:
        content.risk = risk_level

    if decision.is_approval:
        ctx = build_gate_context(db, content)
        # 이 검수로 승인이 성립한다고 가정하고 G6 를 평가한다.
        ctx_after = gates.GateContext(
            sources=ctx.sources,
            evidence=ctx.evidence,
            legal_status=ctx.legal_status,
            risk_level=ctx.risk_level,
            dates=ctx.dates,
            affected_users=ctx.affected_users,
            excluded_users=ctx.excluded_users,
            has_transition_measures=ctx.has_transition_measures,
            approved_by_reviewer=True,
        )
        report = gates.evaluate(ctx_after)
        if not report.can_approve:
            raise GateFailedError(
                "검증 게이트를 통과하지 못해 승인할 수 없습니다.",
                {
                    "failed_gates": list(report.failed_gate_ids()),
                    "gate_report": report.as_dict(),
                },
            )
    else:
        report = gates.evaluate(build_gate_context(db, content))

    review = Review(
        tax_content_id=content.id,
        content_version_id=content.current_version_id,
        reviewer_id=reviewer_id,
        decision=decision,
        review_note=review_note,
        checked_source_version_ids=list(checked_source_version_ids),
    )
    db.add(review)

    content.workflow = status_after_review(content.workflow, decision)
    refresh_confidence(db, content, now=now)
    db.flush()
    return review, report


def publish(
    db: Session, content: TaxContent, *, now: dt.datetime | None = None
) -> gates.GateReport:
    """승인된 콘텐츠를 공개 사이트에 게시한다 (ADR-001 파이프라인의 '사이트 게시').

    게이트를 **다시** 평가한다. 승인 이후 근거가 바뀌었을 수 있고,
    게시는 외부에 노출되는 행위라 되돌리기 비싸다.
    can_schedule 을 기준으로 삼는 이유는 게시가 발송의 전제이기 때문이다 —
    발송할 수 없는 콘텐츠를 사이트에만 올리면 채널 간 내용이 갈라진다.
    """
    now = now or dt.datetime.now(dt.UTC)
    report = gates.evaluate(build_gate_context(db, content))

    if not report.can_schedule:
        raise GateFailedError(
            "검증 게이트를 통과하지 못해 게시할 수 없습니다.",
            {
                "failed_gates": list(report.failed_gate_ids()),
                "gate_report": report.as_dict(),
            },
        )

    if content.workflow is WorkflowStatus.APPROVED:
        content.workflow = WorkflowStatus.SCHEDULED
    if not can_transition(content.workflow, WorkflowStatus.PUBLISHED):
        raise ConflictError(
            f"'{content.workflow.value}' 상태에서는 게시할 수 없습니다. 먼저 승인이 필요합니다.",
            {"current_status": content.workflow.value},
        )

    content.workflow = WorkflowStatus.PUBLISHED
    refresh_confidence(db, content, now=now)
    db.flush()
    return report


def evaluate_for_campaign(db: Session, content: TaxContent) -> gates.GateReport:
    """캠페인 포함 가능 여부를 판정한다 (AT-06).

    CAMPAIGN_MANAGER 가 호출하더라도 G6 는 우회되지 않는다 (§12.2).
    """
    return gates.evaluate(build_gate_context(db, content))
