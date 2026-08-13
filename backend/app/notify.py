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
from app.domain.industry import Industry
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
    db: Session, *, since: dt.datetime, site_base: str, limit: int = 6
) -> tuple[list[BriefingCard], int]:
    """발송 대상 카드와, 자리가 없어 빠진 건수를 돌려준다.

    **게시된 콘텐츠만** 담는다. 검수 전 초안이 텔레그램으로 나가면
    웹보다 먼저 잘못된 정보가 퍼지고, 메시지는 정정할 수도 없다.

    **바뀐 것도 할 일도 없는 건은 보내지 않는다.**
    수집 범위를 넓히니 "이번 훈령은 현행 내용이며 사업자에게 새로운 의무나
    변경사항은 없습니다" 같은 요약이 알림으로 나갔다. 알림은 "당신이 뭔가
    해야 한다"는 신호인데, 할 일이 없다고 적힌 것을 그 신호로 보내면
    다음부터 알림 자체를 안 읽게 된다.

    화면에는 그대로 남는다 — 찾아보러 온 사람에게는 "바뀐 게 없다"도 답이다.
    """
    rows = db.execute(
        select(TaxContent)
        .where(
            TaxContent.workflow.in_(PUBLIC_STATES),
            TaxContent.tenant_id.is_(None),
            TaxContent.updated_at >= since,
            # 기관 내부 문서는 보내지 않는다. 웹에서 숨긴 것을 텔레그램으로
            # 보내면 숨긴 의미가 없다 — 오히려 알림으로 밀어넣는 셈이다.
            ~TaxContent.industries.contains([Industry.INTERNAL.value]),
        )
        # 중요도 → 최신 순. 자리가 모자라면 덜 중요한 것이 빠진다.
        .order_by(TaxContent.risk.desc(), TaxContent.updated_at.desc())
    ).scalars().all()

    cards: list[BriefingCard] = []

    for content in rows:
        body: dict = {}
        if content.current_version_id:
            version = db.get(ContentVersion, content.current_version_id)
            if version and isinstance(version.body, dict):
                body = version.body

        changes = _string_list(body, "changes")
        actions = _string_list(body, "required_actions")
        if not changes and not actions:
            continue

        cards.append(
            BriefingCard(
                title=content.title,
                legal_status=content.legal,
                risk_level=content.risk,
                audience=_string_list(body, "affected_users"),
                effective_date=content.effective_date,
                key_points=changes[:2]
                or ((content.one_line_summary,) if content.one_line_summary else ()),
                actions=actions[:2],
                deadline=content.application_end,
                detail_url=f"{site_base.rstrip('/')}/contents/{content.id}",
                corrected=content.workflow is WorkflowStatus.CORRECTED,
            )
        )

    # 자리가 모자라 빠진 것만 센다. 내용이 없어 걸러진 것은 "더 볼 게 있다"가
    # 아니므로 안내에 넣지 않는다.
    overflow = max(0, len(cards) - limit)
    return cards[:limit], overflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="일일 세무 브리핑 텔레그램 발송")
    parser.add_argument("--hours", type=int, default=24, help="최근 N시간 게시분 (기본 24)")
    # 기본 15 였는데 하루치가 24건 5,900자, 메시지 2개로 나갔다.
    # 그 길이는 아무도 끝까지 읽지 않고, 안 읽는 알림은 다음부터 안 열린다.
    # 중요한 것부터 여섯 건만 보내고 나머지는 사이트로 보낸다.
    parser.add_argument("--limit", type=int, default=6, help="최대 카드 수 (기본 6)")
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
        cards, overflow = collect_cards(
            db, since=since, site_base=args.site, limit=args.limit
        )
    finally:
        db.close()

    today = now.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
    text = render_digest(cards, today=today, site_url=args.site, overflow=overflow)
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
