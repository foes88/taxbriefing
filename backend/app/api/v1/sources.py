"""출처 레지스트리 (FR-SRC-001, §부록 A).

출처명·URL을 코드에 하드코딩하지 않는다는 부록 A의 원칙이 이 엔드포인트의 존재 이유다.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession, IdempotencyKey, StaffUser
from app.core import audit, idempotency
from app.models.tables import Source
from app.schemas.api import SourceCreate, SourceOut

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(db: DbSession, principal: StaffUser) -> list[SourceOut]:
    del principal
    rows = db.execute(select(Source).order_by(Source.display_name)).scalars().all()
    return [SourceOut.model_validate(row) for row in rows]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    db: DbSession,
    key: IdempotencyKey,
    principal: AdminUser,
) -> SourceOut:
    body = payload.model_dump(mode="json")
    replay = idempotency.check(db, scope="sources.create", key=key, payload=body)
    if replay is not None:
        return SourceOut.model_validate(replay.body)

    record = idempotency.begin(db, scope="sources.create", key=key, payload=body)

    source = Source(
        display_name=payload.display_name,
        canonical_domain=payload.canonical_domain.lower(),
        authority=payload.authority,
        collector_type=payload.collector_type.value,
        organization_code=payload.organization_code,
        schedule_cron=payload.schedule_cron,
        rate_limit_per_min=payload.rate_limit_per_min,
        terms_url=payload.terms_url,
        settings=payload.settings,
    )
    db.add(source)
    db.flush()

    out = SourceOut.model_validate(source)
    audit.record(
        db,
        action=audit.Action.SOURCE_CREATED,
        object_type="source",
        object_id=source.id,
        actor_user_id=principal.user_id,
        after=out.model_dump(mode="json"),
    )
    idempotency.complete(
        db, record, status=status.HTTP_201_CREATED, body=out.model_dump(mode="json")
    )
    return out
