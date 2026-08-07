"""업종 분류·검색 텍스트 채우기 CLI.

    python -m app.classify                # 아직 분류 안 된 것만
    python -m app.classify --force        # 전부 다시
    python -m app.classify --pace 3       # 건마다 3초 쉬기 (무료 티어)
    python -m app.classify --dry-run      # 저장하지 않고 결과만 확인

검색 텍스트는 AI 없이 만들 수 있으므로 분류가 실패해도 항상 채운다.
검색은 되는데 업종 필터만 비는 편이, 둘 다 안 되는 것보다 낫다.
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.domain.industry import label
from app.models.tables import ContentVersion, TaxContent
from app.services.ai.classify import build_search_text, classify_industries
from app.services.ai.groq_provider import GroqProvider

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="업종 분류 및 검색 텍스트 생성")
    parser.add_argument("--force", action="store_true", help="이미 분류된 것도 다시")
    parser.add_argument("--limit", type=int, default=0, help="최대 처리 건수 (0=전체)")
    parser.add_argument("--pace", type=float, default=0.0, help="건마다 쉬는 시간(초)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않음")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(debug=settings.debug)

    provider = GroqProvider()
    db = SessionLocal()
    tagged = untagged = 0

    try:
        stmt = select(TaxContent).order_by(TaxContent.updated_at.desc())
        if not args.force:
            # search_text 가 비었거나 업종이 비었으면 대상이다.
            stmt = stmt.where(
                (TaxContent.search_text.is_(None))
                | (TaxContent.industries == [])
            )
        if args.limit:
            stmt = stmt.limit(args.limit)

        contents = list(db.execute(stmt).scalars())
        print(f"대상 {len(contents)}건\n")

        for index, content in enumerate(contents, start=1):
            body: dict = {}
            if content.current_version_id:
                version = db.get(ContentVersion, content.current_version_id)
                if version and isinstance(version.body, dict):
                    body = version.body

            content.search_text = build_search_text(
                content.title, content.one_line_summary, body
            )

            codes, reason = classify_industries(
                content.title, content.one_line_summary, body, provider=provider
            )
            content.industries = codes

            if codes:
                tagged += 1
                names = " · ".join(label(c) for c in codes)
            else:
                untagged += 1
                names = "(해당 업종 없음)"

            print(f"[{index}/{len(contents)}] {content.title[:44]}")
            print(f"        {names}")
            if reason:
                print(f"        └ {reason[:80]}")

            # **건마다 커밋한다.** 맨 끝에 한 번만 커밋했더니 51건까지 처리하고
            # 죽었을 때 하나도 안 남았다. AI 호출이 섞인 긴 작업은 중간에 죽는다고
            # 보고 짜야 한다 — 다시 돌릴 때 남은 것부터 이어갈 수 있어야 한다.
            if not args.dry_run:
                db.commit()

            if args.pace and index < len(contents):
                time.sleep(args.pace)

        if args.dry_run:
            db.rollback()
            print("\n[dry-run] 저장하지 않았습니다.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\n분류됨 {tagged}건 · 업종 없음 {untagged}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
