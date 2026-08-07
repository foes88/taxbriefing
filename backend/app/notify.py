"""일일 브리핑 텔레그램 발송 (ADR-001).

    python -m app.notify --dry-run        # 보낼 내용만 출력 (기본값)
    python -m app.notify --send           # 실제 전송
    python -m app.notify --hours 48

GitHub Actions cron 에서 매일 아침 호출한다 (ADR-004).

**기본값이 --dry-run 인 이유**: 발송은 되돌릴 수 없다. 사람이나 스케줄러가
명시적으로 --send 를 붙여야만 실제로 나간다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.domain.enums import WorkflowStatus
from app.models.tables import ContentVersion, TaxContent
from app.services.delivery.channels import OutboundMessage, TelegramAdapter, split_for_telegram
from app.services.render.telegram import BriefingCard, render_digest

logger = get_logger(__name__)

PUBLIC_STATES = (
    WorkflowStatus.PUBLISHED,
    WorkflowStatus.MONITORING,
    WorkflowStatus.CORRECTED,
)


def _string_list(body: dict, key: str) -> tuple[str, ...]:
    value = body.get(key)
    if isinstance(value, list):
        return tuple(str(v) for v in value if str(v).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def collect_cards(
    db: Session, *, since: dt.datetime, site_base: str, limit: int = 15
) -> list[BriefingCard]:
    """발송 대상 카드를 모은다.

    **게시된 콘텐츠만** 담는다. 검수 전 초안이 텔레그램으로 나가면
    웹보다 먼저 잘못된 정보가 퍼지고, 메시지는 정정할 수도 없다.
    """
    rows = db.execute(
        select(TaxContent)
        .where(
            TaxContent.workflow.in_(PUBLIC_STATES),
            TaxContent.tenant_id.is_(None),
            TaxContent.updated_at >= since,
            # 사업자와 무관하다고 판단된 건은 보내지 않는다. 웹에서 숨긴 것을
            # 텔레그램으로 보내면 숨긴 의미가 없다 — 오히려 알림으로 밀어넣는 셈이다.
            ~(TaxContent.search_text.is_not(None) & (TaxContent.industries == [])),
        )
        .order_by(TaxContent.risk.desc(), TaxContent.updated_at.desc())
        .limit(limit)
    ).scalars().all()

    cards: list[BriefingCard] = []
    for content in rows:
        body: dict = {}
        if content.current_version_id:
            version = db.get(ContentVersion, content.current_version_id)
            if version and isinstance(version.body, dict):
                body = version.body

        cards.append(
            BriefingCard(
                title=content.title,
                legal_status=content.legal,
                risk_level=content.risk,
                audience=_string_list(body, "affected_users"),
                effective_date=content.effective_date,
                key_points=_string_list(body, "changes")[:2]
                or ((content.one_line_summary,) if content.one_line_summary else ()),
                actions=_string_list(body, "required_actions")[:2],
                deadline=content.application_end,
                detail_url=f"{site_base.rstrip('/')}/contents/{content.id}",
                corrected=content.workflow is WorkflowStatus.CORRECTED,
            )
        )
    return cards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="일일 세무 브리핑 텔레그램 발송")
    parser.add_argument("--hours", type=int, default=24, help="최근 N시간 게시분 (기본 24)")
    parser.add_argument("--limit", type=int, default=15, help="최대 카드 수 (기본 15)")
    parser.add_argument("--send", action="store_true", help="실제 전송 (기본은 미리보기)")
    parser.add_argument("--chat-id", help="수신 chat_id (기본: 환경변수)")
    parser.add_argument(
        "--site",
        default=os.environ.get("TAXBRIEFING_SITE_URL", "https://taxbriefing.vercel.app"),
        help="상세 링크 기준 주소",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(debug=settings.debug)

    now = dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(hours=args.hours)

    db = SessionLocal()
    try:
        cards = collect_cards(db, since=since, site_base=args.site, limit=args.limit)
    finally:
        db.close()

    today = now.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
    text = render_digest(cards, today=today, site_url=args.site)
    chunks = split_for_telegram(text)

    print("=" * 60)
    print(text)
    print("=" * 60)
    print(f"\n브리핑 {len(cards)}건 · 메시지 {len(chunks)}개 · {len(text)}자")

    if not args.send:
        print("\n[미리보기] 실제로 보내려면 --send 를 붙이세요.")
        return 0

    if not cards:
        print("\n보낼 내용이 없어 발송하지 않습니다.")
        return 0

    adapter = TelegramAdapter()
    if not adapter.configured:
        print(
            "\nTAXBRIEFING_TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다.\n"
            "봇 토큰과 TAXBRIEFING_TELEGRAM_CHAT_ID 를 .env 에 넣으세요.",
            file=sys.stderr,
        )
        return 2

    message = OutboundMessage(subject=None, body=text, content_url=None)
    adapter.validate(message)
    result = adapter.send(recipient=args.chat_id or "", message=message)

    if result.ok:
        print(f"\n발송 완료 (message_id={result.provider_message_id})")
        return 0

    print(f"\n발송 실패: {result.error_code} — {result.error_detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["UUID", "collect_cards", "main"]
