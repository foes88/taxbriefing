"""역할 기반 접근 제어 (§12.2, FR-ADM-001).

원칙 두 가지를 코드로 강제한다.

1. **SYSTEM_ADMIN 도 검수를 대체할 수 없다.** 승인은 REVIEWER 만 수행한다.
   관리자에게 모든 권한을 주면 §1.3 "사람이 최종 승인" 원칙이 무너진다.
2. **CAMPAIGN_MANAGER 는 전문가 승인을 우회할 수 없다.** 캠페인 권한이
   게이트 G6 를 넘어서지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.errors import ForbiddenError
from app.core.security import Principal
from app.domain.enums import Role

# 관리 콘솔 접근 권한이 있는 역할.
STAFF_ROLES: frozenset[Role] = frozenset(
    {
        Role.VIEWER,
        Role.EDITOR,
        Role.REVIEWER,
        Role.CAMPAIGN_MANAGER,
        Role.TENANT_ADMIN,
        Role.SYSTEM_ADMIN,
    }
)

# 콘텐츠 편집 권한.
EDIT_ROLES: frozenset[Role] = frozenset({Role.EDITOR, Role.REVIEWER, Role.SYSTEM_ADMIN})

# 검수·승인 권한. SYSTEM_ADMIN 은 의도적으로 제외한다 (§12.2).
REVIEW_ROLES: frozenset[Role] = frozenset({Role.REVIEWER})

# 출처·시스템 설정 권한.
ADMIN_ROLES: frozenset[Role] = frozenset({Role.SYSTEM_ADMIN})

# 캠페인 운영 권한.
CAMPAIGN_ROLES: frozenset[Role] = frozenset({Role.CAMPAIGN_MANAGER, Role.SYSTEM_ADMIN})


def ensure_role(principal: Principal, allowed: Iterable[Role]) -> None:
    allowed_set = frozenset(allowed)
    if principal.role not in allowed_set:
        raise ForbiddenError(
            "이 작업을 수행할 권한이 없습니다.",
            {
                "required_roles": sorted(r.value for r in allowed_set),
                "actual_role": principal.role.value,
            },
        )


def ensure_tenant_scope(principal: Principal, tenant_id: object | None) -> None:
    """테넌트 격리 (§12.2, AT-13).

    tenant_id 가 None 인 자원은 전체 공용이므로 누구나 읽을 수 있다 (§7.4 D-04).
    SYSTEM_ADMIN 은 운영을 위해 모든 테넌트를 볼 수 있으나, 그 조회는 감사로그에 남는다.
    """
    if tenant_id is None or principal.role is Role.SYSTEM_ADMIN:
        return
    if principal.tenant_id is None or str(principal.tenant_id) != str(tenant_id):
        raise ForbiddenError(
            "다른 테넌트의 자원에 접근할 수 없습니다.",
            {"resource_tenant_id": str(tenant_id)},
        )


def can_review(principal: Principal) -> bool:
    return principal.role in REVIEW_ROLES
