"""워크플로 상태 전이와 승인 해제 규칙 (§3.3, FR-CMS-004, AT-07).

순수 함수. 상태 전이는 여기서만 결정하고, 서비스 계층은 결과를 반영만 한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.enums import ReviewDecision, WorkflowStatus

# 승인 후 변경되면 승인이 해제되는 필드 (§8.4 '보호 필드', AT-07).
# 여기 없는 필드는 오탈자 수정처럼 사실관계를 바꾸지 않는 편집으로 본다.
PROTECTED_FIELDS: frozenset[str] = frozenset(
    {
        "legal_status",
        "risk_level",
        "announcement_date",
        "promulgation_date",
        "effective_date",
        "application_start",
        "application_end",
        "title",
        "one_line_summary",
        "body",
    }
)

# 승인이 유효한 상태들. 이 상태에서 보호 필드를 고치면 재검수로 돌아간다.
_APPROVED_STATES: frozenset[WorkflowStatus] = frozenset(
    {
        WorkflowStatus.APPROVED,
        WorkflowStatus.SCHEDULED,
        WorkflowStatus.PUBLISHED,
        WorkflowStatus.MONITORING,
    }
)

_ALLOWED: Mapping[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DETECTED: frozenset({WorkflowStatus.UNVERIFIED, WorkflowStatus.ARCHIVED}),
    WorkflowStatus.UNVERIFIED: frozenset(
        {WorkflowStatus.SOURCE_CONFIRMED, WorkflowStatus.ARCHIVED}
    ),
    WorkflowStatus.SOURCE_CONFIRMED: frozenset(
        {WorkflowStatus.ANALYZED, WorkflowStatus.REVIEW_PENDING, WorkflowStatus.ARCHIVED}
    ),
    WorkflowStatus.ANALYZED: frozenset(
        {WorkflowStatus.REVIEW_PENDING, WorkflowStatus.SOURCE_CONFIRMED, WorkflowStatus.ARCHIVED}
    ),
    WorkflowStatus.REVIEW_PENDING: frozenset(
        {
            WorkflowStatus.APPROVED,
            WorkflowStatus.ANALYZED,  # 반려
            WorkflowStatus.SOURCE_CONFIRMED,
            WorkflowStatus.ARCHIVED,
        }
    ),
    WorkflowStatus.APPROVED: frozenset(
        {
            WorkflowStatus.SCHEDULED,
            WorkflowStatus.REVIEW_PENDING,  # 보호 필드 수정에 의한 승인 해제
            WorkflowStatus.ARCHIVED,
        }
    ),
    WorkflowStatus.SCHEDULED: frozenset(
        {WorkflowStatus.PUBLISHED, WorkflowStatus.APPROVED, WorkflowStatus.REVIEW_PENDING}
    ),
    WorkflowStatus.PUBLISHED: frozenset(
        {
            WorkflowStatus.MONITORING,
            WorkflowStatus.CORRECTED,
            WorkflowStatus.SUPERSEDED,
            WorkflowStatus.REVIEW_PENDING,
        }
    ),
    WorkflowStatus.MONITORING: frozenset(
        {WorkflowStatus.CORRECTED, WorkflowStatus.SUPERSEDED, WorkflowStatus.ARCHIVED}
    ),
    WorkflowStatus.CORRECTED: frozenset(
        {WorkflowStatus.MONITORING, WorkflowStatus.SUPERSEDED, WorkflowStatus.ARCHIVED}
    ),
    WorkflowStatus.SUPERSEDED: frozenset({WorkflowStatus.ARCHIVED}),
    WorkflowStatus.ARCHIVED: frozenset(),
}


def can_transition(current: WorkflowStatus, target: WorkflowStatus) -> bool:
    if current is target:
        return True
    return target in _ALLOWED.get(current, frozenset())


def allowed_transitions(current: WorkflowStatus) -> frozenset[WorkflowStatus]:
    return _ALLOWED.get(current, frozenset())


@dataclass(frozen=True)
class EditOutcome:
    """보호 필드 수정 판정 결과."""

    changed_fields: tuple[str, ...]
    protected_changed: tuple[str, ...]
    approval_revoked: bool
    next_status: WorkflowStatus

    @property
    def reason(self) -> str:
        if not self.approval_revoked:
            return ""
        return (
            "승인된 콘텐츠의 보호 필드가 변경되어 승인이 해제되고 재검수 큐로 이동했습니다: "
            + ", ".join(self.protected_changed)
        )


def _differs(before: Any, after: Any) -> bool:
    # date 와 ISO 문자열이 섞여 들어와도 같은 값이면 변경으로 보지 않는다.
    if before == after:
        return False
    if before is None or after is None:
        return True
    return str(before) != str(after)


def apply_edit(
    *,
    current_status: WorkflowStatus,
    before: Mapping[str, Any],
    patch: Mapping[str, Any],
) -> EditOutcome:
    """콘텐츠 수정이 승인 상태에 미치는 영향을 판정한다 (AT-07).

    승인된 콘텐츠의 보호 필드가 바뀌면 승인을 해제하고 REVIEW_PENDING 으로 되돌린다.
    '값이 실제로 달라졌을 때만' 해제한다 — 같은 값 재전송으로 승인이 풀리면
    운영자가 저장 버튼을 누르기를 두려워하게 되고, 그건 검수 품질을 떨어뜨린다.
    """
    changed = tuple(k for k, v in patch.items() if _differs(before.get(k), v))
    protected_changed = tuple(k for k in changed if k in PROTECTED_FIELDS)

    revoked = bool(protected_changed) and current_status in _APPROVED_STATES
    next_status = WorkflowStatus.REVIEW_PENDING if revoked else current_status

    return EditOutcome(
        changed_fields=changed,
        protected_changed=protected_changed,
        approval_revoked=revoked,
        next_status=next_status,
    )


def status_after_review(
    current: WorkflowStatus, decision: ReviewDecision
) -> WorkflowStatus:
    """검수 결정에 따른 다음 워크플로 상태 (FR-CMS-003)."""
    if decision.is_approval:
        return WorkflowStatus.APPROVED
    # 반려는 분석 단계로 되돌려 편집·재분석을 받게 한다.
    return WorkflowStatus.ANALYZED if current is WorkflowStatus.REVIEW_PENDING else current
