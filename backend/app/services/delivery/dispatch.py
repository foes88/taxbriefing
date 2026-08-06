"""대상 선정과 발송 실행 (§11.2, §11.5, AT-08/09/10).

발송 직전 순서가 이 모듈의 전부다.

    게이트(G4/G6) → 수신동의 재확인 → 하드 제외 → 점수 → 멱등성 → 전송

수신동의를 **발송 실행 시점에** 다시 읽는 것이 중요하다 (§12.4). 캠페인 생성 시점에
확인해두면, 예약과 발송 사이에 철회한 사용자에게 메시지가 나간다 (AT-10).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import Channel, DeliveryStatus
from app.domain.personalization import (
    ContentTargeting,
    ExclusionReason,
    MatchResult,
    UserTargeting,
    match,
)
from app.models.tables import BusinessProfile, Consent, Delivery, User
from app.services.delivery.channels import OutboundMessage, get_adapter

logger = get_logger(__name__)

MARKETING_CONSENT = "MARKETING"


def delivery_idempotency_key(campaign_id: UUID, user_id: UUID, channel: Channel) -> str:
    """§11.5 — deliveries.idempotency_key 생성 규칙 (D-01)."""
    return f"{campaign_id}:{user_id}:{channel.value}"


def has_active_consent(
    db: Session, *, user_id: UUID, channel: Channel, consent_type: str = MARKETING_CONSENT
) -> bool:
    """현재 유효한 수신동의가 있는가 (§12.4, D-05).

    consents 는 append-only 이므로 (user_id, consent_type, channel) 별 **최신 행**이
    현재 상태다. 최신 행이 granted=False 이거나 revoked_at 이 찍혀 있으면 철회된 것이다.
    """
    latest = db.execute(
        select(Consent)
        .where(
            Consent.user_id == user_id,
            Consent.consent_type == consent_type,
            Consent.channel == channel.value,
        )
        .order_by(Consent.granted_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if latest is None:
        return False
    if latest.revoked_at is not None:
        return False
    return latest.granted


@dataclass
class RecipientDecision:
    user_id: UUID
    result: MatchResult

    @property
    def included(self) -> bool:
        return self.result.matched


def select_recipients(
    db: Session,
    *,
    candidate_user_ids: list[UUID],
    targeting: ContentTargeting,
    channel: Channel,
    today: dt.date,
    content_allows_personalization: bool = True,
    threshold: int = 20,
) -> list[RecipientDecision]:
    """캠페인 대상을 선정한다.

    제외된 사용자도 결과에 남긴다. campaign_recipients 에 excluded_reason 과 함께
    저장해야 "왜 이 사람은 안 받았는가"에 답할 수 있다 (§NFR-010).
    """
    profiles = {
        p.user_id: p
        for p in db.execute(
            select(BusinessProfile).where(BusinessProfile.user_id.in_(candidate_user_ids))
        ).scalars()
    }

    decisions: list[RecipientDecision] = []
    for user_id in candidate_user_ids:
        profile = profiles.get(user_id)
        if profile is None:
            decisions.append(
                RecipientDecision(
                    user_id,
                    MatchResult(
                        False,
                        0,
                        excluded_reason=ExclusionReason.BELOW_THRESHOLD,
                        excluded_detail="사업자 프로필이 없어 관련성을 판정할 수 없습니다.",
                    ),
                )
            )
            continue

        user_targeting = UserTargeting(
            business_type=profile.business_type,
            tax_type=profile.tax_type,
            industry_codes=frozenset(profile.industry_codes or ()),
            region_codes=frozenset(profile.region_codes or ()),
            employee_band=profile.employee_band,
            revenue_band=profile.revenue_band,
            interest_topics=frozenset(profile.interest_topics or ()),
        )

        result = match(
            targeting,
            user_targeting,
            today=today,
            has_channel_consent=has_active_consent(db, user_id=user_id, channel=channel),
            content_allows_personalization=content_allows_personalization,
            threshold=threshold,
        )
        decisions.append(RecipientDecision(user_id, result))

    return decisions


@dataclass
class DispatchOutcome:
    delivery: Delivery
    created: bool
    """False 이면 멱등성에 의해 기존 발송을 재사용한 것이다 (AT-09)."""

    sent: bool


def dispatch(
    db: Session,
    *,
    campaign_id: UUID,
    user_id: UUID,
    channel: Channel,
    message: OutboundMessage,
    recipient_address: str | None = None,
    now: dt.datetime | None = None,
    actually_send: bool = False,
) -> DispatchOutcome:
    """사용자 1명에게 1건을 발송한다. 멱등적이다 (AT-09).

    `actually_send=False` 가 기본값이다. 발송은 되돌릴 수 없는 외부 행위이므로,
    호출자가 명시적으로 켜야만 실제 전송한다. 기본 경로는 발송 레코드와
    스냅샷만 만들고 PENDING 으로 둔다.
    """
    now = now or dt.datetime.now(dt.UTC)
    key = delivery_idempotency_key(campaign_id, user_id, channel)

    existing = db.execute(
        select(Delivery).where(Delivery.idempotency_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        # 같은 캠페인·사용자·채널로 두 번째 요청. 새 발송을 만들지 않는다.
        return DispatchOutcome(existing, created=False, sent=False)

    adapter = get_adapter(channel)
    adapter.validate(message)

    delivery = Delivery(
        campaign_id=campaign_id,
        user_id=user_id,
        channel=channel.value,
        provider=adapter.provider,
        idempotency_key=key,
        status=DeliveryStatus.PENDING,
        message_snapshot=message.as_snapshot(),
    )
    db.add(delivery)
    db.flush()

    if not actually_send:
        return DispatchOutcome(delivery, created=True, sent=False)

    address = recipient_address or _default_address(db, user_id, channel)
    delivery.attempted_at = now
    delivery.status = DeliveryStatus.QUEUED
    result = adapter.send(recipient=address, message=message)

    if result.ok:
        delivery.status = DeliveryStatus.SENT
        delivery.provider_message_id = result.provider_message_id
        delivery.delivered_at = now
    else:
        delivery.status = DeliveryStatus.FAILED
        delivery.error_code = result.error_code
        delivery.error_detail = result.error_detail

    db.flush()
    return DispatchOutcome(delivery, created=True, sent=result.ok)


def _default_address(db: Session, user_id: UUID, channel: Channel) -> str:
    user = db.get(User, user_id)
    if user is None:
        return ""
    if channel is Channel.EMAIL:
        return user.email
    if channel is Channel.SMS:
        return user.phone or ""
    return ""
