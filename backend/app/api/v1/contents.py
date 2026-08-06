"""콘텐츠 생성·수정·검수 (§4.3, §4.5, AT-03/06/07/12)."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession, EditorUser, IdempotencyKey, IfMatch, ReviewerUser, StaffUser
from app.core import audit, idempotency
from app.core.rbac import ensure_tenant_scope
from app.schemas.api import (
    AuditLogOut,
    ContentCreate,
    ContentOut,
    ContentPatch,
    ContentPatchResponse,
    EvidenceIn,
    GateReportOut,
    ReviewOut,
    ReviewRequest,
    ReviewResponse,
    SubmitReviewResponse,
)
from app.services import content as content_service

router = APIRouter(prefix="/contents", tags=["Contents"])


@router.post("", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def create_content(
    payload: ContentCreate,
    db: DbSession,
    key: IdempotencyKey,
    principal: EditorUser,
) -> ContentOut:
    body = payload.model_dump(mode="json")
    replay = idempotency.check(db, scope="contents.create", key=key, payload=body)
    if replay is not None:
        return ContentOut.model_validate(replay.body)

    record = idempotency.begin(db, scope="contents.create", key=key, payload=body)

    roles = {link.source_version_id: link.role for link in payload.source_roles}
    content = content_service.create_content(
        db,
        title=payload.title,
        source_version_ids=payload.source_version_ids,
        policy_cluster_id=payload.policy_cluster_id,
        legal_status=payload.legal_status,
        risk_level=payload.risk_level,
        body=payload.body,
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        roles=roles or None,
    )

    out = ContentOut.of(content)
    audit.record(
        db,
        action=audit.Action.CONTENT_CREATED,
        object_type="tax_content",
        object_id=content.id,
        actor_user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        after=out.model_dump(mode="json"),
    )
    idempotency.complete(
        db, record, status=status.HTTP_201_CREATED, body=out.model_dump(mode="json")
    )
    return out


@router.get("/{content_id}", response_model=ContentOut)
def get_content(
    content_id: UUID,
    db: DbSession,
    principal: StaffUser,
) -> ContentOut:
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)
    return ContentOut.of(content)


@router.patch("/{content_id}", response_model=ContentPatchResponse)
def update_content(
    content_id: UUID,
    payload: ContentPatch,
    db: DbSession,
    if_match: IfMatch,
    principal: EditorUser,
) -> ContentPatchResponse:
    """콘텐츠를 수정한다.

    승인된 콘텐츠의 보호 필드가 바뀌면 승인이 해제되고 재검수 큐로 간다 (AT-07).
    """
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)

    patch = payload.model_dump(exclude_unset=True)
    before = ContentOut.of(content).model_dump(mode="json")

    content, outcome = content_service.update_content(
        db, content, patch, expected_version=if_match, editor_id=principal.user_id
    )
    after = ContentOut.of(content).model_dump(mode="json")

    audit.record(
        db,
        action=audit.Action.CONTENT_UPDATED,
        object_type="tax_content",
        object_id=content.id,
        actor_user_id=principal.user_id,
        tenant_id=content.tenant_id,
        before=before,
        after=after,
        reason=", ".join(outcome.changed_fields) or None,
    )
    if outcome.approval_revoked:
        audit.record(
            db,
            action=audit.Action.CONTENT_APPROVAL_REVOKED,
            object_type="tax_content",
            object_id=content.id,
            actor_user_id=principal.user_id,
            tenant_id=content.tenant_id,
            after={"protected_fields_changed": list(outcome.protected_changed)},
            reason=outcome.reason,
        )

    return ContentPatchResponse(
        content=ContentOut.of(content),
        approval_revoked=outcome.approval_revoked,
        protected_fields_changed=list(outcome.protected_changed),
        message=outcome.reason or None,
    )


@router.post("/{content_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(
    content_id: UUID,
    payload: EvidenceIn,
    db: DbSession,
    principal: EditorUser,
) -> dict[str, str]:
    """필드별 근거를 연결한다 (FR-VER-004)."""
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)

    evidence = content_service.add_evidence(
        db,
        content,
        field_name=payload.field_name,
        raw_content_version_id=payload.raw_content_version_id,
        locator=payload.locator,
        support_type=payload.support_type,
        note=payload.note,
    )
    content_service.refresh_confidence(db, content, now=dt.datetime.now(dt.UTC))
    return {"evidence_id": str(evidence.id), "field_name": evidence.field_name}


@router.get("/{content_id}/gates", response_model=GateReportOut)
def evaluate_gates(
    content_id: UUID,
    db: DbSession,
    principal: StaffUser,
) -> GateReportOut:
    """게이트 G1~G6 현재 판정 (§3.7). 검수 화면에서 무엇이 막혀 있는지 보여준다."""
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)
    report = content_service.evaluate_for_campaign(db, content)
    return GateReportOut.model_validate(report.as_dict())


@router.post("/{content_id}/submit-review", response_model=SubmitReviewResponse)
def submit_review(
    content_id: UUID,
    db: DbSession,
    key: IdempotencyKey,
    principal: EditorUser,
) -> SubmitReviewResponse:
    """검수를 요청한다 (A-02). 뉴스 단독 콘텐츠는 여기서 막힌다 (AT-03)."""
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)

    payload = {"content_id": str(content_id)}
    replay = idempotency.check(db, scope="contents.submit_review", key=key, payload=payload)
    if replay is not None:
        return SubmitReviewResponse.model_validate(replay.body)
    record = idempotency.begin(db, scope="contents.submit_review", key=key, payload=payload)

    report = content_service.submit_for_review(db, content)

    audit.record(
        db,
        action=audit.Action.CONTENT_SUBMITTED_FOR_REVIEW,
        object_type="tax_content",
        object_id=content.id,
        actor_user_id=principal.user_id,
        tenant_id=content.tenant_id,
        after={"gate_report": report.as_dict()},
    )

    out = SubmitReviewResponse(
        content=ContentOut.of(content),
        gate_report=GateReportOut.model_validate(report.as_dict()),
    )
    idempotency.complete(db, record, status=status.HTTP_200_OK, body=out.model_dump(mode="json"))
    return out


@router.post(
    "/{content_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    content_id: UUID,
    payload: ReviewRequest,
    db: DbSession,
    key: IdempotencyKey,
    principal: ReviewerUser,
) -> ReviewResponse:
    """승인·반려를 기록한다 (FR-CMS-003).

    REVIEWER 만 호출할 수 있다. SYSTEM_ADMIN 도 여기서는 403 이다 (§12.2).
    """
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)

    body = payload.model_dump(mode="json")
    replay = idempotency.check(db, scope="contents.review", key=key, payload=body)
    if replay is not None:
        return ReviewResponse.model_validate(replay.body)
    record = idempotency.begin(db, scope="contents.review", key=key, payload=body)

    review, report = content_service.record_review(
        db,
        content,
        reviewer_id=principal.user_id,
        decision=payload.decision,
        review_note=payload.review_note,
        checked_source_version_ids=payload.checked_source_version_ids,
        legal_status=payload.legal_status,
        risk_level=payload.risk_level,
    )

    # AT-12: 누가 어떤 근거를 확인하고 승인했는지가 감사로그에 남아야 한다.
    audit.record(
        db,
        action=audit.Action.CONTENT_REVIEWED,
        object_type="tax_content",
        object_id=content.id,
        actor_user_id=principal.user_id,
        tenant_id=content.tenant_id,
        after={
            "decision": payload.decision.value,
            "checked_source_version_ids": [str(v) for v in payload.checked_source_version_ids],
            "content_version_id": str(review.content_version_id),
            "workflow_status": content.workflow.value,
            "legal_status": content.legal.value,
            "risk_level": content.risk.value,
        },
        reason=payload.review_note,
    )

    out = ReviewResponse(
        review=ReviewOut.model_validate(review),
        content=ContentOut.of(content),
        gate_report=GateReportOut.model_validate(report.as_dict()),
    )
    idempotency.complete(
        db, record, status=status.HTTP_201_CREATED, body=out.model_dump(mode="json")
    )
    return out


@router.post("/{content_id}/publish", response_model=SubmitReviewResponse)
def publish_content(
    content_id: UUID,
    db: DbSession,
    key: IdempotencyKey,
    principal: EditorUser,
) -> SubmitReviewResponse:
    """승인된 콘텐츠를 공개 사이트에 게시한다.

    승인은 REVIEWER 만 하지만, 게시는 운영 행위이므로 EDITOR 도 할 수 있다.
    단 게이트가 다시 평가되므로 미승인 콘텐츠는 여기서 막힌다 (G6).
    """
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)

    payload = {"content_id": str(content_id)}
    replay = idempotency.check(db, scope="contents.publish", key=key, payload=payload)
    if replay is not None:
        return SubmitReviewResponse.model_validate(replay.body)
    record = idempotency.begin(db, scope="contents.publish", key=key, payload=payload)

    report = content_service.publish(db, content)

    audit.record(
        db,
        action=audit.Action.CONTENT_PUBLISHED,
        object_type="tax_content",
        object_id=content.id,
        actor_user_id=principal.user_id,
        tenant_id=content.tenant_id,
        after={
            "workflow_status": content.workflow.value,
            "legal_status": content.legal.value,
            "risk_level": content.risk.value,
        },
    )

    out = SubmitReviewResponse(
        content=ContentOut.of(content),
        gate_report=GateReportOut.model_validate(report.as_dict()),
    )
    idempotency.complete(db, record, status=status.HTTP_200_OK, body=out.model_dump(mode="json"))
    return out


@router.get("/{content_id}/audit", response_model=list[AuditLogOut])
def get_audit_trail(
    content_id: UUID,
    db: DbSession,
    principal: StaffUser,
) -> list[AuditLogOut]:
    """콘텐츠 감사 이력 (AT-12)."""
    content = content_service.get_content(db, content_id)
    ensure_tenant_scope(principal, content.tenant_id)
    entries = audit.history(db, object_type="tax_content", object_id=content_id)
    return [AuditLogOut.model_validate(e) for e in entries]
