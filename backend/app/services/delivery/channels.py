"""발송 채널 어댑터 (§11.4, FR-DLV-003 '공급자를 교체 가능한 인터페이스로').

모든 채널은 같은 인터페이스를 구현한다. 채널을 추가해도 캠페인 로직은 바뀌지 않는다.

**어댑터는 렌더링된 메시지를 받아 보내기만 한다.** 게이트 판정, 수신동의 확인,
대상 선정은 모두 이 계층에 도달하기 전에 끝나 있어야 한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.enums import Channel

logger = get_logger(__name__)


@dataclass(frozen=True)
class OutboundMessage:
    """발송할 메시지. deliveries.message_snapshot 에 그대로 저장된다 (§11.4)."""

    subject: str | None
    body: str
    unsubscribe_url: str | None = None
    content_url: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def as_snapshot(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "body": self.body,
            "unsubscribe_url": self.unsubscribe_url,
            "content_url": self.content_url,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


class ChannelAdapter(Protocol):
    channel: Channel
    provider: str

    def validate(self, message: OutboundMessage) -> None:
        """채널 정책 위반이면 예외를 던진다. 발송 전에 호출한다."""
        ...

    def send(self, *, recipient: str, message: OutboundMessage) -> SendResult: ...


class ChannelPolicyError(Exception):
    """채널 정책 위반 (§11.4)."""


# --------------------------------------------------------------------------- 이메일


class EmailAdapter:
    """이메일 (§11.4). 공급자 계약은 미결 항목 ①."""

    channel = Channel.EMAIL
    provider = "unconfigured"

    def validate(self, message: OutboundMessage) -> None:
        # §11.4: 이메일은 수신거부 링크가 필수다. 법적 요건이므로 어댑터에서 강제한다.
        if not message.unsubscribe_url:
            raise ChannelPolicyError("이메일 발송에는 수신거부 링크가 필수입니다 (§11.4).")
        if not message.subject:
            raise ChannelPolicyError("이메일 발송에는 제목이 필요합니다.")

    def send(self, *, recipient: str, message: OutboundMessage) -> SendResult:
        raise NotImplementedError(
            "이메일 공급자가 설정되지 않았습니다. 미결 항목 ① (발송 채널 사업자) 확정 후 구현하세요."
        )


# --------------------------------------------------------------------------- 텔레그램

TELEGRAM_MAX_CHARS = 4096


def split_for_telegram(text: str, limit: int = TELEGRAM_MAX_CHARS) -> list[str]:
    """텔레그램 4096자 제한에 맞춰 줄 경계에서 자른다.

    ai-market-brief 의 분할 방식과 동일하게 마지막 개행에서 자른다.
    세무 브리핑은 항목 단위로 읽히므로, 문장 중간에서 끊기면 오독 위험이 있다.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


class TelegramAdapter:
    """텔레그램 봇 발송.

    기존 ai-market-brief 프로젝트가 쓰는 것과 같은 Bot API 방식이다.
    토큰과 채팅방 ID는 환경변수에서만 읽는다 (§12.1 — 비밀키 DB 저장 금지).

        TAXBRIEFING_TELEGRAM_BOT_TOKEN
        TAXBRIEFING_TELEGRAM_CHAT_ID

    §11.4 는 채널을 이메일·알림톡·SMS·웹으로 규정한다. 텔레그램은 그 이후 추가된
    채널이므로 openapi.yaml 의 channels enum 갱신 승인 전까지는 내부 운영용으로만 쓴다.
    """

    channel = Channel.TELEGRAM
    provider = "telegram-bot-api"

    API_BASE = "https://api.telegram.org"

    def __init__(
        self,
        bot_token: str | None = None,
        default_chat_id: str | None = None,
        *,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        # 환경변수를 먼저 본다. 컨테이너·CI 에서는 .env 파일이 없고 환경변수만 있다.
        # 없으면 설정(.env)에서 읽는다 — 로컬은 반대로 .env 만 있다.
        # 한쪽만 읽으면 "분명히 넣었는데 설정 안 됐다"는 말이 나온다. 실제로 나왔다.
        settings = get_settings()
        self._bot_token = (
            bot_token
            or os.environ.get("TAXBRIEFING_TELEGRAM_BOT_TOKEN")
            or settings.telegram_bot_token
        )
        self._default_chat_id = (
            default_chat_id
            or os.environ.get("TAXBRIEFING_TELEGRAM_CHAT_ID")
            or settings.telegram_chat_id
        )
        self._timeout = timeout
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._bot_token)

    def validate(self, message: OutboundMessage) -> None:
        if not message.body.strip():
            raise ChannelPolicyError("빈 메시지는 보낼 수 없습니다.")
        # 텔레그램은 수신거부 링크를 법적으로 요구하지 않지만, 광고성 정보에는
        # 채널과 무관하게 수신거부 안내가 필요하다 (§12.4). 링크가 없으면 경고만 남긴다.
        if not message.unsubscribe_url:
            logger.warning(
                "telegram.no_unsubscribe_link",
                detail="광고성 발송이면 수신거부 안내가 필요합니다 (§12.4).",
            )

    def send(self, *, recipient: str, message: OutboundMessage) -> SendResult:
        if not self._bot_token:
            return SendResult(
                False,
                error_code="NOT_CONFIGURED",
                error_detail="TAXBRIEFING_TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다.",
            )

        chat_id = recipient or self._default_chat_id or ""
        if not chat_id:
            return SendResult(
                False,
                error_code="NO_CHAT_ID",
                error_detail="수신 chat_id 가 없습니다.",
            )

        text = message.body
        if message.subject:
            text = f"{message.subject}\n\n{text}"
        if message.content_url:
            text = f"{text}\n\n원문·상세: {message.content_url}"
        if message.unsubscribe_url:
            text = f"{text}\n수신거부: {message.unsubscribe_url}"

        client = self._client or httpx.Client(timeout=self._timeout)
        owns_client = self._client is None
        last_id: str | None = None
        try:
            for chunk in split_for_telegram(text):
                response = client.post(
                    f"{self.API_BASE}/bot{self._bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": False},
                )
                if response.status_code >= 400:
                    return SendResult(
                        False,
                        error_code=f"HTTP_{response.status_code}",
                        error_detail=response.text[:500],
                    )
                payload = response.json()
                if not payload.get("ok"):
                    return SendResult(
                        False,
                        error_code="TELEGRAM_ERROR",
                        error_detail=str(payload.get("description"))[:500],
                    )
                last_id = str(payload.get("result", {}).get("message_id", ""))
        except httpx.HTTPError as exc:
            return SendResult(False, error_code="TRANSPORT_ERROR", error_detail=str(exc)[:500])
        finally:
            if owns_client:
                client.close()

        return SendResult(True, provider_message_id=last_id)


# --------------------------------------------------------------------------- 레지스트리


class NullAdapter:
    """미구현 채널의 자리표시자. 발송을 시도하면 실패로 기록된다."""

    def __init__(self, channel: Channel) -> None:
        self.channel = channel
        self.provider = "unconfigured"

    def validate(self, message: OutboundMessage) -> None:
        del message

    def send(self, *, recipient: str, message: OutboundMessage) -> SendResult:
        del recipient, message
        return SendResult(
            False,
            error_code="NOT_CONFIGURED",
            error_detail=f"{self.channel.value} 채널 공급자가 설정되지 않았습니다 (미결 항목 ①).",
        )


def get_adapter(channel: Channel) -> ChannelAdapter:
    if channel is Channel.TELEGRAM:
        return TelegramAdapter()
    if channel is Channel.EMAIL:
        return EmailAdapter()
    return NullAdapter(channel)
