"""FastAPI 의존성 (§8.1, §12.2).

역할별 의존성은 모듈 수준 타입 별칭으로 둔다. 엔드포인트 시그니처에서
`principal: ReviewerUser` 처럼 읽히므로, 어떤 권한이 필요한지가 한눈에 보인다.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db, get_read_db
from app.core.errors import UnauthorizedError, ValidationFailedError
from app.core.rbac import ADMIN_ROLES, EDIT_ROLES, REVIEW_ROLES, STAFF_ROLES, ensure_role
from app.core.security import Principal, decode_access_token
from app.domain.enums import Role

DbSession = Annotated[Session, Depends(get_db)]

#: 읽기만 하는 엔드포인트용.
#:
#: 트랜잭션을 열지 않으므로 세션을 닫을 때 ROLLBACK 왕복이 없다. DB 가
#: 미국에 있어서 그 한 번이 200ms 다 — 목록 한 번 여는 시간의 5분의 1이었다.
#:
#: **쓰는 엔드포인트에 붙이면 안 된다.** AUTOCOMMIT 이라 한 요청 안의
#: 변경이 하나씩 따로 확정되고, 중간에 실패하면 반쪽만 남는다.
ReadSession = Annotated[Session, Depends(get_read_db)]


def get_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Bearer 토큰에서 호출자를 얻는다. 모든 보호 엔드포인트에서 검증한다 (§12.3)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("인증이 필요합니다.")
    return decode_access_token(authorization.split(" ", 1)[1].strip())


CurrentUser = Annotated[Principal, Depends(get_principal)]


def _role_dependency(roles: Iterable[Role]):
    allowed = frozenset(roles)

    def _dep(principal: CurrentUser) -> Principal:
        ensure_role(principal, allowed)
        return principal

    return _dep


#: 관리 콘솔 조회 권한 (VIEWER 이상).
StaffUser = Annotated[Principal, Depends(_role_dependency(STAFF_ROLES))]

#: 콘텐츠 편집 권한. 최종 승인은 포함하지 않는다 (§12.2).
EditorUser = Annotated[Principal, Depends(_role_dependency(EDIT_ROLES))]

#: 검수·승인 권한. SYSTEM_ADMIN 도 여기 포함되지 않는다 (§12.2).
ReviewerUser = Annotated[Principal, Depends(_role_dependency(REVIEW_ROLES))]

#: 출처·시스템 설정 권한.
AdminUser = Annotated[Principal, Depends(_role_dependency(ADMIN_ROLES))]


def idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """쓰기 요청의 Idempotency-Key (§8.1, A-03: 쓰기에만 강제)."""
    if not idempotency_key or len(idempotency_key) < 8:
        raise ValidationFailedError(
            "Idempotency-Key 헤더가 필요합니다 (8~128자).",
            {"header": "Idempotency-Key"},
        )
    if len(idempotency_key) > 128:
        raise ValidationFailedError("Idempotency-Key 는 128자를 넘을 수 없습니다.")
    return idempotency_key


IdempotencyKey = Annotated[str, Depends(idempotency_key)]


def if_match(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int | None:
    """낙관적 잠금 버전 (§8.1)."""
    if if_match is None:
        return None
    value = if_match.strip().strip('"').removeprefix("W/").strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise ValidationFailedError(
            "If-Match 헤더는 콘텐츠 버전 번호여야 합니다.", {"if_match": if_match}
        ) from exc


IfMatch = Annotated[int | None, Depends(if_match)]
