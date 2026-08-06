"""감사로그 (§NFR-009, FR-ADM-002, AT-12).

조회를 제외한 모든 주요 변경과 발송 행위를 기록한다. append-only 이며
UPDATE/DELETE 하지 않는다. 민감정보는 저장 전에 마스킹한다 (§7.3).

AT-12 요구: "관리자는 누가 어떤 근거를 확인하고 승인했는지 조회할 수 있다."
따라서 승인 감사에는 검수자가 확인한 원문 버전 목록이 반드시 들어간다.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_trace_id, mask_sensitive
from app.models.tables import AuditLog


class Action:
    """감사 액션 코드. 문자열 오타를 막기 위해 상수로 둔다."""

    SOURCE_CREATED = "SOURCE_CREATED"
    SOURCE_UPDATED = "SOURCE_UPDATED"
    RAW_CONTENT_REGISTERED = "RAW_CONTENT_REGISTERED"
    RAW_CONTENT_VERSION_ADDED = "RAW_CONTENT_VERSION_ADDED"
    RAW_CONTENT_UNCHANGED = "RAW_CONTENT_UNCHANGED"
    ANALYSIS_REQUESTED = "ANALYSIS_REQUESTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    CONTENT_CREATED = "CONTENT_CREATED"
    CONTENT_UPDATED = "CONTENT_UPDATED"
    CONTENT_APPROVAL_REVOKED = "CONTENT_APPROVAL_REVOKED"
    CONTENT_SUBMITTED_FOR_REVIEW = "CONTENT_SUBMITTED_FOR_REVIEW"
    CONTENT_REVIEWED = "CONTENT_REVIEWED"
    CONTENT_PUBLISHED = "CONTENT_PUBLISHED"
    PROFILE_UPDATED = "PROFILE_UPDATED"
    CONSENT_CHANGED = "CONSENT_CHANGED"
    DELIVERY_CREATED = "DELIVERY_CREATED"
    DELIVERY_SENT = "DELIVERY_SENT"


def record(
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str | UUID,
    actor_user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    ip_hash: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        before_data=mask_sensitive(before) if before is not None else None,
        after_data=mask_sensitive(after) if after is not None else None,
        reason=reason,
        ip_hash=ip_hash,
        trace_id=get_trace_id(),
    )
    db.add(entry)
    db.flush()
    return entry


def history(
    db: Session, *, object_type: str, object_id: str | UUID, limit: int = 100
) -> list[AuditLog]:
    """객체 하나의 감사 이력을 최신순으로 조회한다 (AT-12)."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.object_type == object_type, AuditLog.object_id == str(object_id))
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())
