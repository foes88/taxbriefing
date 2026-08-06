"""멱등성 처리 (§NFR-005, §8.1, AT-09).

같은 Idempotency-Key 로 두 번 온 요청은 두 번째부터 **새 객체를 만들지 않고**
첫 응답을 그대로 돌려준다. 수집·AI 분석·캠페인 생성·발송 요청에 적용한다.

키가 같은데 본문이 다르면 409 로 거절한다. 클라이언트가 키를 재사용한 버그이거나
요청이 중간에 변조된 것이므로, 조용히 첫 응답을 주면 오히려 위험하다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.tables import IdempotencyRecord


def request_hash(payload: Any) -> str:
    """요청 본문의 정규화 해시. 키 순서가 달라도 같은 값이 나오게 한다."""
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Replay:
    """이미 처리된 요청의 저장된 응답."""

    status: int
    body: dict[str, Any]


def check(
    db: Session, *, scope: str, key: str, payload: Any
) -> Replay | None:
    """이 요청이 이미 처리되었는지 확인한다.

    반환값이 None 이면 처음 보는 요청이므로 계속 진행한다.
    """
    digest = request_hash(payload)
    record = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == key,
        )
    ).scalar_one_or_none()

    if record is None:
        return None

    if record.request_hash != digest:
        raise ConflictError(
            "같은 Idempotency-Key 로 다른 내용의 요청이 도착했습니다.",
            {"scope": scope, "idempotency_key": key},
        )

    if record.response_status is None:
        # 첫 요청이 아직 처리 중이다. 재시도는 나중에.
        raise ConflictError(
            "동일한 요청이 처리 중입니다. 잠시 후 다시 시도해 주세요.",
            {"scope": scope, "idempotency_key": key},
        )

    return Replay(status=record.response_status, body=record.response_body or {})


def begin(db: Session, *, scope: str, key: str, payload: Any) -> IdempotencyRecord:
    """처리 시작을 기록한다. 응답은 아직 없다."""
    record = IdempotencyRecord(
        scope=scope,
        idempotency_key=key,
        request_hash=request_hash(payload),
    )
    db.add(record)
    db.flush()
    return record


def complete(
    db: Session, record: IdempotencyRecord, *, status: int, body: dict[str, Any]
) -> None:
    """처리 결과를 기록한다. 이후 같은 키 요청은 이 응답을 재생한다."""
    record.response_status = status
    record.response_body = body
    db.flush()
