"""구독자 프로필과 수신설정 (FR-PER-001, FR-USR-004, §12.4)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core import audit
from app.domain.enums import Channel
from app.models.tables import BusinessProfile, Consent
from app.schemas.api import BusinessProfileIn, BusinessProfileOut

router = APIRouter(prefix="/me", tags=["Subscriber"])


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_type: str = "MARKETING"
    channel: Channel
    granted: bool
    document_version: str


@router.put("/business-profile", response_model=BusinessProfileOut)
def replace_business_profile(
    payload: BusinessProfileIn,
    db: DbSession,
    principal: CurrentUser,
) -> BusinessProfileOut:
    """사업자 프로필을 교체한다.

    개인화에 필요한 최소 항목만 저장한다 (§12.4 '수집 최소화').
    """
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.user_id == principal.user_id)
    ).scalar_one_or_none()

    before = None
    if profile is None:
        profile = BusinessProfile(user_id=principal.user_id, business_type=payload.business_type)
        db.add(profile)
    else:
        before = BusinessProfileOut.model_validate(profile).model_dump(mode="json")

    profile.business_type = payload.business_type
    profile.tax_type = payload.tax_type
    profile.industry_codes = payload.industry_codes
    profile.region_codes = payload.region_codes
    profile.employee_band = payload.employee_band
    profile.revenue_band = payload.revenue_band
    profile.interest_topics = payload.interest_topics
    db.flush()

    out = BusinessProfileOut.model_validate(profile)
    audit.record(
        db,
        action=audit.Action.PROFILE_UPDATED,
        object_type="business_profile",
        object_id=profile.id,
        actor_user_id=principal.user_id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    return out


@router.put("/consents", status_code=200)
def set_consent(
    payload: ConsentIn,
    db: DbSession,
    principal: CurrentUser,
) -> dict[str, object]:
    """채널별 수신동의를 기록한다 (§12.4).

    동의 이력은 append-only 다 (D-05). 철회도 새 행으로 남기며, 기존 행을 고치지 않는다.
    "언제 어떤 문구로 동의했는가"는 나중에 증명해야 할 수 있는 사실이다.
    """
    now = dt.datetime.now(dt.UTC)
    consent = Consent(
        user_id=principal.user_id,
        consent_type=payload.consent_type,
        channel=payload.channel.value,
        granted=payload.granted,
        document_version=payload.document_version,
        granted_at=now,
        revoked_at=None if payload.granted else now,
        source="API",
    )
    db.add(consent)
    db.flush()

    audit.record(
        db,
        action=audit.Action.CONSENT_CHANGED,
        object_type="consent",
        object_id=consent.id,
        actor_user_id=principal.user_id,
        after={
            "consent_type": payload.consent_type,
            "channel": payload.channel.value,
            "granted": payload.granted,
            "document_version": payload.document_version,
        },
    )
    return {
        "consent_id": str(consent.id),
        "channel": payload.channel.value,
        "granted": payload.granted,
        "recorded_at": now.isoformat(),
    }
