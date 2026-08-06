"""원문 조회와 수동 등록 (FR-SRC-006, AT-01, AT-02)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, EditorUser, IdempotencyKey, StaffUser
from app.core import audit, idempotency
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.tables import RawContent, RawContentVersion, Source
from app.schemas.api import (
    ManualRawContentCreate,
    ManualRawContentResponse,
    RawContentOut,
    RawContentVersionOut,
)
from app.services import ingest

router = APIRouter(prefix="/raw-contents", tags=["RawContent"])


@router.get("", response_model=list[RawContentOut])
def search_raw_contents(
    db: DbSession,
    principal: StaffUser,
    q: Annotated[str | None, Query()] = None,
    source_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RawContentOut]:
    del principal
    stmt = select(RawContent).order_by(RawContent.published_at.desc().nullslast()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(RawContent.source_id == source_id)
    if q:
        stmt = stmt.where(RawContent.title.ilike(f"%{q}%"))
    return [RawContentOut.model_validate(r) for r in db.execute(stmt).scalars()]


@router.get("/{raw_content_id}", response_model=RawContentOut)
def get_raw_content(
    raw_content_id: UUID, db: DbSession, principal: StaffUser
) -> RawContentOut:
    del principal
    raw = db.get(RawContent, raw_content_id)
    if raw is None:
        raise NotFoundError("원문을 찾을 수 없습니다.", {"raw_content_id": str(raw_content_id)})
    return RawContentOut.model_validate(raw)


@router.get("/{raw_content_id}/versions", response_model=list[RawContentVersionOut])
def list_versions(
    raw_content_id: UUID, db: DbSession, principal: StaffUser
) -> list[RawContentVersionOut]:
    del principal
    rows = db.execute(
        select(RawContentVersion)
        .where(RawContentVersion.raw_content_id == raw_content_id)
        .order_by(RawContentVersion.version_no)
    ).scalars().all()
    return [RawContentVersionOut.model_validate(r) for r in rows]


@router.get("/{raw_content_id}/diff")
def get_diff(
    raw_content_id: UUID,
    db: DbSession,
    principal: StaffUser,
    from_version: Annotated[int, Query(ge=1)] = 1,
    to_version: Annotated[int, Query(ge=1)] = 2,
) -> dict[str, str | int]:
    """버전 간 diff (FR-NRM-004, AT-02)."""
    del principal
    versions = {
        v.version_no: v
        for v in db.execute(
            select(RawContentVersion).where(RawContentVersion.raw_content_id == raw_content_id)
        ).scalars()
    }
    if from_version not in versions or to_version not in versions:
        raise NotFoundError(
            "요청한 원문 버전이 없습니다.", {"available_versions": sorted(versions)}
        )
    return {
        "from_version": from_version,
        "to_version": to_version,
        "diff": ingest.version_diff(
            db,
            from_version_id=versions[from_version].id,
            to_version_id=versions[to_version].id,
        ),
    }


@router.post(
    "/manual",
    response_model=ManualRawContentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_manual(
    payload: ManualRawContentCreate,
    db: DbSession,
    key: IdempotencyKey,
    principal: EditorUser,
) -> ManualRawContentResponse:
    """운영자가 원문을 직접 등록한다 (FR-SRC-006).

    공식 사이트 구조 변경이나 자동수집 제한이 있어도 운영이 멈추지 않게 하는 경로다 (§15.4).
    동일 URL 재등록은 새 원문을 만들지 않는다 (AT-01).
    """
    source = db.get(Source, payload.source_id)
    if source is None:
        raise ValidationFailedError(
            "등록되지 않은 출처입니다.", {"source_id": str(payload.source_id)}
        )

    body = payload.model_dump(mode="json")
    replay = idempotency.check(db, scope="raw_contents.manual", key=key, payload=body)
    if replay is not None:
        return ManualRawContentResponse.model_validate(replay.body)

    record = idempotency.begin(db, scope="raw_contents.manual", key=key, payload=body)

    result = ingest.ingest(
        db,
        source_id=payload.source_id,
        canonical_url=payload.canonical_url,
        title=payload.title,
        publisher=payload.publisher,
        raw_body=payload.normalized_text,
        published_at=payload.published_at,
        source_item_id=payload.source_item_id,
    )

    action = {
        ingest.IngestOutcome.NEW: audit.Action.RAW_CONTENT_REGISTERED,
        ingest.IngestOutcome.CHANGED: audit.Action.RAW_CONTENT_VERSION_ADDED,
        ingest.IngestOutcome.REVERTED: audit.Action.RAW_CONTENT_VERSION_ADDED,
        ingest.IngestOutcome.UNCHANGED: audit.Action.RAW_CONTENT_UNCHANGED,
    }[result.outcome]

    audit.record(
        db,
        action=action,
        object_type="raw_content",
        object_id=result.raw_content.id,
        actor_user_id=principal.user_id,
        after={
            "outcome": result.outcome.value,
            "version_no": result.version.version_no,
            "content_hash": result.version.content_hash,
            "canonical_url": result.raw_content.canonical_url,
        },
        reason="수동 원문 등록",
    )

    out = ManualRawContentResponse(
        outcome=result.outcome.value,
        raw_content=RawContentOut.model_validate(result.raw_content),
        version=RawContentVersionOut.model_validate(result.version),
        diff=result.diff,
    )
    idempotency.complete(
        db, record, status=status.HTTP_201_CREATED, body=out.model_dump(mode="json")
    )
    return out
