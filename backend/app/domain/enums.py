"""도메인 열거형.

값은 docs/contracts/schema.sql 의 PostgreSQL ENUM 및
docs/contracts/ai_output_schema.json 과 문자 단위로 일치해야 한다.
tests/contract/test_enum_parity.py 가 이를 강제한다.
"""

from __future__ import annotations

from enum import StrEnum


class AuthorityGrade(StrEnum):
    """출처 권위 등급 (§3.1)."""

    A = "A"  # 법령·관보·의안 원문
    B = "B"  # 정부·공공기관 공식자료
    C = "C"  # 전문기관·전문언론 — 단독 확정 발송 금지
    D = "D"  # 일반뉴스·블로그·SNS — 단독 근거 사용 금지

    @property
    def is_official(self) -> bool:
        """공식 원문 여부. G1 원문성 게이트의 기준 (§3.7)."""
        return self in (AuthorityGrade.A, AuthorityGrade.B)


class LegalStatus(StrEnum):
    """정책의 법적 상태 — 외부 세계의 사실 (§3.2)."""

    DISCUSSION = "DISCUSSION"
    BILL_PROPOSED = "BILL_PROPOSED"
    PREANNOUNCED = "PREANNOUNCED"
    GOV_ANNOUNCED = "GOV_ANNOUNCED"
    ASSEMBLY_PASSED = "ASSEMBLY_PASSED"
    PROMULGATED = "PROMULGATED"
    EFFECTIVE = "EFFECTIVE"
    SUSPENDED = "SUSPENDED"
    ABOLISHED = "ABOLISHED"
    UNKNOWN = "UNKNOWN"

    @property
    def requires_grade_a_evidence(self) -> bool:
        """A등급 근거 없이는 주장할 수 없는 상태 (§9.4 V3)."""
        return self in (LegalStatus.PROMULGATED, LegalStatus.EFFECTIVE)

    @property
    def is_confirmed(self) -> bool:
        """'현재 적용 기준'으로 표현해도 되는 상태인가 (§10.4, AT-04)."""
        return self is LegalStatus.EFFECTIVE


class WorkflowStatus(StrEnum):
    """콘텐츠 내부 처리 상태 (§3.3). legal_status 와 절대 합치지 않는다."""

    DETECTED = "DETECTED"
    UNVERIFIED = "UNVERIFIED"
    SOURCE_CONFIRMED = "SOURCE_CONFIRMED"
    ANALYZED = "ANALYZED"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    MONITORING = "MONITORING"
    CORRECTED = "CORRECTED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class RiskLevel(StrEnum):
    """콘텐츠 위험도 (§7.3)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def requires_expert_approval(self) -> bool:
        """전문가 승인 없이는 발송할 수 없는 위험도 (§9.4 V4, AT-06)."""
        return self in (RiskLevel.HIGH, RiskLevel.CRITICAL)


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    APPROVE_WITH_EDIT = "APPROVE_WITH_EDIT"
    REJECT = "REJECT"

    @property
    def is_approval(self) -> bool:
        return self in (ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_EDIT)


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    CANCELED = "CANCELED"


class SourceRole(StrEnum):
    """가공 콘텐츠에 연결된 원문의 역할 (§7.3)."""

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    REFERENCE = "REFERENCE"


class SupportType(StrEnum):
    """근거가 필드를 뒷받침하는 방식 (ai_output_schema.json $defs.evidence)."""

    DIRECT = "DIRECT"
    INFERRED = "INFERRED"
    CONFLICT = "CONFLICT"


class Urgency(StrEnum):
    """required_actions[].urgency (ai_output_schema.json $defs.action_item)."""

    NOW = "NOW"
    BEFORE_DEADLINE = "BEFORE_DEADLINE"
    MONITOR = "MONITOR"
    ASK_EXPERT = "ASK_EXPERT"


class Role(StrEnum):
    """RBAC 역할 (§12.2)."""

    SUBSCRIBER = "SUBSCRIBER"
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    REVIEWER = "REVIEWER"
    CAMPAIGN_MANAGER = "CAMPAIGN_MANAGER"
    TENANT_ADMIN = "TENANT_ADMIN"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class CollectorType(StrEnum):
    API = "API"
    RSS = "RSS"
    HTML = "HTML"
    EMAIL = "EMAIL"
    MANUAL = "MANUAL"


class Channel(StrEnum):
    """발송 채널 (§11.4).

    TELEGRAM 은 명세서 v1.0 이후 추가된 채널이다. openapi.yaml 의 CampaignCreate.channels
    enum 에는 아직 없으므로, 계약 갱신 승인 전까지는 내부 운영·테스트 용도로만 사용한다.
    (미결 항목 ①: 발송 채널 사업자·계약조건)
    """

    EMAIL = "EMAIL"
    KAKAO = "KAKAO"
    SMS = "SMS"
    WEB = "WEB"
    TELEGRAM = "TELEGRAM"


class CampaignType(StrEnum):
    URGENT = "URGENT"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    DEADLINE = "DEADLINE"
    CORRECTION = "CORRECTION"
