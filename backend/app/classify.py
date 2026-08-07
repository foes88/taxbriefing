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
from app.domain.industry import is_internal_document, label
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
    tagged = untagged = failed = 0

    try:
        stmt = select(TaxContent).order_by(TaxContent.updated_at.desc())
        if not args.force:
            # **search_text 하나만 본다.** 이 값은 판단이 끝났을 때만 채워지므로
            # "아직 안 함"의 정확한 표지다. 업종이 비었는지까지 같이 보면
            # "판단해보니 무관"인 건들을 매번 다시 돌리게 되고, 그건 무료 한도를
            # 그냥 태우는 일이다. 실제로 29건이 매 실행마다 다시 돌았다.
            stmt = stmt.where(TaxContent.search_text.is_(None))
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

            print(f"[{index}/{len(contents)}] {content.title[:44]}")

            # 제목만 봐도 아는 것에 AI 호출을 쓰지 않는다. 무료 한도는
            # 정작 판단이 필요한 개정에 써야 한다.
            if is_internal_document(content.title):
                content.search_text = build_search_text(
                    content.title, content.one_line_summary, body
                )
                content.industries = []
                untagged += 1
                print("        (기관 내부 문서 — 규칙으로 판정, 화면에서 숨김)")
                if not args.dry_run:
                    db.commit()
                continue

            result = classify_industries(
                content.title, content.one_line_summary, body, provider=provider
            )

            if result is None:
                # 판단을 못 했다. **아무것도 쓰지 않고 넘어간다.**
                # 여기서 search_text 만 채우면 "분류했는데 무관"으로 보이고,
                # 화면은 그 판단을 믿고 이 건을 숨긴다. API 가 잠깐 죽은 것뿐인데.
                failed += 1
                print("        ! 분류 실패 — 다시 돌리면 이 건부터 이어집니다")
                continue

            content.search_text = build_search_text(
                content.title, content.one_line_summary, body
            )
            content.industries = result.codes

            if result.codes:
                tagged += 1
                names = " · ".join(label(c) for c in result.codes)
            else:
                untagged += 1
                names = "(사업자와 무관 — 화면에서 숨김)"

            print(f"        {names}")
            if result.reason:
                print(f"        └ {result.reason[:80]}")

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

    print(f"\n분류됨 {tagged}건 · 사업자 무관 {untagged}건 · 실패 {failed}건")
    if failed:
        print("실패한 건은 다시 실행하면 이어서 처리됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
