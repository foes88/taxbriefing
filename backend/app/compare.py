"""신구법 대조표를 이미 게시된 법령 콘텐츠에 붙인다.

    python -m app.compare                # 아직 안 붙은 것만
    python -m app.compare --force        # 전부 다시
    python -m app.compare --limit 20     # 최대 20건
    python -m app.compare --dry-run      # 저장하지 않고 결과만

**AI 를 쓰지 않는다.** 법제처가 구조문과 신조문을 짝지어 주고 바뀐
부분까지 표시해 준다. 우리가 할 일은 옮겨 담는 것뿐이고, 그래서
"모델이 뭐라고 썼는지" 를 검수할 필요가 없다.

짝은 `law_id` + `공포번호` 로 맞춘다. 둘 다 우리가 수집할 때 이미
받아 둔 값이고 법제처가 같은 값을 돌려준다 — 법령명 문자열을 비교하며
"소득세법 시행규칙" 과 "소득세법시행규칙" 이 같은지 고민할 이유가 없다.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.domain.enums import ContentKind
from app.models.tables import ContentSource, ContentVersion, RawContentVersion, TaxContent
from app.services.collectors.law_go_kr import DEFAULT_TAX_QUERIES
from app.services.collectors.old_and_new import OldAndNewClient, OldAndNewError

logger = get_logger(__name__)


def _index(client: OldAndNewClient, laws: tuple[str, ...]) -> dict[tuple[str, str], object]:
    """법령별 대조표 목록을 한 번에 받아 `(법령ID, 공포번호)` 로 색인한다.

    콘텐츠마다 검색을 돌리면 같은 법령을 수십 번 조회하게 된다.
    법령 수는 18개고 콘텐츠는 그보다 훨씬 많다.
    """
    found: dict[tuple[str, str], object] = {}
    for law in laws:
        try:
            items = client.search(law, display=40)
        except OldAndNewError as exc:
            logger.warning("compare.search_failed", law=law, error=str(exc)[:200])
            print(f"  ! {law} 검색 실패 — {exc}")
            continue
        for item in items:
            if item.law_id and item.promulgation_no:
                found.setdefault((item.law_id, item.promulgation_no), item)
    return found


def _meta_of(db: Session, content: TaxContent) -> dict:
    """이 콘텐츠의 근거 원문 메타. 없으면 빈 dict."""
    row = db.execute(
        select(RawContentVersion.doc_metadata)
        .join(ContentSource, ContentSource.raw_content_version_id == RawContentVersion.id)
        .where(ContentSource.tax_content_id == content.id)
        .limit(1)
    ).scalar_one_or_none()
    return row if isinstance(row, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="신구법 대조표 붙이기")
    parser.add_argument("--force", action="store_true", help="이미 붙은 것도 다시")
    parser.add_argument("--limit", type=int, default=0, help="최대 처리 건수 (0=전체)")
    parser.add_argument("--pace", type=float, default=0.5, help="호출 간 대기 초")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않음")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(debug=settings.debug)

    client_http = httpx.Client(timeout=40.0)
    client = OldAndNewClient(client_http)
    if not client.configured:
        print("TAXBRIEFING_LAW_API_OC 가 없습니다.")
        return 1

    db = SessionLocal()
    attached = no_match = failed = skipped = 0

    try:
        print("신구법 대조표 목록을 받는 중…")
        index = _index(client, DEFAULT_TAX_QUERIES)
        print(f"대조표 {len(index)}건 색인\n")

        contents = list(
            db.execute(
                select(TaxContent)
                .where(TaxContent.content_kind == ContentKind.POLICY.value)
                .order_by(TaxContent.updated_at.desc())
            ).scalars()
        )

        for index_no, content in enumerate(contents, start=1):
            if args.limit and attached >= args.limit:
                break

            version = (
                db.get(ContentVersion, content.current_version_id)
                if content.current_version_id
                else None
            )
            if version is None or not isinstance(version.body, dict):
                skipped += 1
                continue
            if version.body.get("comparison") and not args.force:
                skipped += 1
                continue

            meta = _meta_of(db, content)
            key = (str(meta.get("law_id") or ""), str(meta.get("promulgation_no") or ""))
            if not all(key):
                # 행정규칙·고시에는 법령ID 가 없다. 대조표도 없다.
                skipped += 1
                continue

            item = index.get(key)
            if item is None:
                no_match += 1
                continue

            print(f"[{index_no}/{len(contents)}] {content.title[:44]}")
            try:
                rows, dropped = client.diff(item.mst)  # type: ignore[attr-defined]
            except OldAndNewError as exc:
                failed += 1
                print(f"        ! {exc}")
                continue

            if not rows:
                # 대조표는 있는데 바뀐 조문이 없다. 빈 표를 붙이면 화면이
                # "변경 내용" 이라는 제목 아래 아무것도 없는 칸을 그린다.
                skipped += 1
                print("        (변경 표시된 조문 없음)")
                continue

            # **본문을 통째로 갈아치우지 않는다.** 요약 결과가 같이 들어
            # 있는 컬럼이고, 여기서 덮으면 애써 만든 요약이 사라진다.
            version.body = {
                **version.body,
                "comparison": {
                    "rows": [row.as_dict() for row in rows],
                    "dropped": dropped,
                    "law_name": item.law_name,  # type: ignore[attr-defined]
                    "revision_type": item.revision_type,  # type: ignore[attr-defined]
                },
            }
            attached += 1
            tail = f" (외 {dropped}개 생략)" if dropped else ""
            print(f"        변경 조문 {len(rows)}개{tail}")

            if not args.dry_run:
                db.commit()
            if args.pace:
                time.sleep(args.pace)

        if args.dry_run:
            db.rollback()
            print("\n[dry-run] 저장하지 않았습니다.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        client_http.close()

    print(
        f"\n붙임 {attached}건 · 대조표 없음 {no_match}건 "
        f"· 건너뜀 {skipped}건 · 실패 {failed}건"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]
