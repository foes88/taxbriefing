"""수집 실행 CLI.

    python -m app.collect                    # 최근 30일 공포분
    python -m app.collect --days 90
    python -m app.collect --source law.go.kr
    python -m app.collect --dry-run          # 저장하지 않고 확인만

GitHub Actions cron 에서 이 명령을 호출한다 (ADR-004).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.tables import Source
from app.services.collectors.base import run_collection
from app.services.collectors.law_go_kr import AdmRulCollector, LawCollector, LawGoKrClient

logger = get_logger(__name__)

#: 도메인 → 어댑터. 새 출처를 붙이면 여기만 늘어난다.
ADAPTERS = {
    "law.go.kr": (LawCollector, AdmRulCollector),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TaxBriefing 원문 수집")
    p.add_argument("--source", help="출처 도메인 (기본: 어댑터가 있는 전체)")
    p.add_argument("--days", type=int, default=30, help="최근 N일 공포분만 (기본 30)")
    p.add_argument("--limit", type=int, default=60, help="출처당 최대 조회 건수")
    p.add_argument("--dry-run", action="store_true", help="저장하지 않고 롤백")
    p.add_argument("--run-type", default="MANUAL")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(debug=settings.debug)

    if not settings.law_api_oc:
        print(
            "TAXBRIEFING_LAW_API_OC 가 설정되지 않았습니다.\n"
            "open.law.go.kr 에서 신청한 OC 값을 .env 에 넣으세요.",
            file=sys.stderr,
        )
        return 2

    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=args.days)
    client = LawGoKrClient()
    db = SessionLocal()
    total = {"discovered": 0, "new": 0, "changed": 0, "unchanged": 0, "errors": 0}

    try:
        domains = [args.source] if args.source else list(ADAPTERS)
        for domain in domains:
            adapters = ADAPTERS.get(domain)
            if adapters is None:
                print(f"'{domain}' 어댑터가 없습니다. 사용 가능: {', '.join(ADAPTERS)}")
                continue

            source = db.execute(
                select(Source).where(Source.canonical_domain == domain)
            ).scalar_one_or_none()
            if source is None:
                print(f"출처가 등록되지 않았습니다: {domain}. `python -m app.seed` 를 먼저 실행하세요.")
                continue

            for adapter_cls in adapters:
                collector = adapter_cls(client)
                print(f"\n▶ {source.display_name} / {collector.name} (최근 {args.days}일)")
                run, stats = run_collection(
                    db,
                    source=source,
                    collector=collector,
                    since=since,
                    limit=args.limit,
                    run_type=args.run_type,
                )
                print(
                    f"  조회 {stats.discovered} · 신규 {stats.new} · 변경 {stats.changed} "
                    f"· 동일 {stats.unchanged} · 오류 {stats.errors}  [{run.status}]"
                )
                for detail in stats.error_details[:5]:
                    print(f"    ! {detail['item']}: {detail['error'][:120]}")

                for key in ("discovered", "new", "changed", "unchanged", "errors"):
                    total[key] += getattr(stats, key)

        if args.dry_run:
            db.rollback()
            print("\n[dry-run] 롤백했습니다.")
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"\n합계 — 조회 {total['discovered']} · 신규 {total['new']} · 변경 {total['changed']} "
        f"· 동일 {total['unchanged']} · 오류 {total['errors']}"
    )
    return 1 if total["errors"] and not total["new"] and not total["changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
