"""인증 토큰과 비밀번호 해시 (§6.1 OIDC/JWT, §12.3)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.domain.enums import Role


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@dataclass(frozen=True)
class Principal:
    """인증된 호출자. 모든 엔드포인트에서 권한을 검증한다 (§12.3)."""

    user_id: UUID
    role: Role
    tenant_id: UUID | None


def create_access_token(*, user_id: UUID, role: Role, tenant_id: UUID | None) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Principal:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("토큰이 만료되었습니다.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("토큰을 검증할 수 없습니다.") from exc

    try:
        role = Role(payload["role"])
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("토큰 페이로드가 올바르지 않습니다.") from exc

    raw_tenant = payload.get("tenant_id")
    return Principal(
        user_id=user_id,
        role=role,
        tenant_id=UUID(raw_tenant) if raw_tenant else None,
    )
