"""인증 (§6.1 OIDC/JWT).

MVP는 비밀번호 로그인만 지원한다. 관리자 MFA(§12.3 NFR-007)와 B2B SSO는 2단계다.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token, verify_password
from app.domain.enums import Role
from app.models.tables import User
from app.schemas.api import LoginRequest, TokenResponse

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    # 계정 존재 여부를 응답으로 구분할 수 없게 한다.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")
    if user.status != "ACTIVE":
        raise UnauthorizedError("비활성 계정입니다.")

    role = Role(user.role)
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, role=role, tenant_id=user.tenant_id
        ),
        role=role,
        tenant_id=user.tenant_id,
    )
