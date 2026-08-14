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
from app.domain.enums import CollectorType
from app.models.tables import Source
from app.services.collectors.assembly import AssemblyBillCollector
from app.services.collectors.base import run_collection
from app.services.collectors.interpretation import InterpretationCollector
from app.services.collectors.law_go_kr import (
    AdmRulCollector,
    LawCollector,
    LawGoKrClient,
    UpcomingLawCollector,
)
from app.services.collectors.naver_news import NaverNewsCollector
from app.services.collectors.rss import RssCollector
from app.services.collectors.tribunal import TaxTribunalCollector

logger = get_logger(__name__)

#: 도메인 → 어댑터. 특정 API 를 쓰는 출처만 여기에 둔다.
#: 나머지는 collector_type 으로 고른다 (RSS 등) — 출처를 늘려도 코드가 늘지 않는다.
ADAPTERS = {
    # 현행법 → 행정규칙 → 시행예정 순. 시행예정을 마지막에 두는 이유는 없다 —
    # 별개 canonical_url 을 쓰므로 서로 덮어쓰지 않는다.
    "law.go.kr": (LawCollector, AdmRulCollector, UpcomingLawCollector),
    "law.go.kr/조세심판원": (TaxTribunalCollector,),
    "law.go.kr/법령해석": (InterpretationCollector,),
    "open.assembly.go.kr": (AssemblyBillCollector,),
    "openapi.naver.com": (NaverNewsCollector,),
}


def adapters_for(source: Source) -> tuple[type, ...]:
    """출처에 맞는 어댑터를 고른다."""
    specific = ADAPTERS.get(source.canonical_domain)
    if specific:
        return specific
    if source.collector_type == CollectorType.RSS.value and (source.settings or {}).get(
        "feed_url"
    ):
        return (RssCollector,)
    return ()


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

    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=args.days)
    law_client = LawGoKrClient()
    db = SessionLocal()
    total = {"discovered": 0, "new": 0, "changed": 0, "unchanged": 0, "errors": 0}

    try:
        if args.source:
            sources = db.execute(
                select(Source).where(Source.canonical_domain == args.source)
            ).scalars().all()
            if not sources:
                print(f"출처가 등록되지 않았습니다: {args.source}")
                return 2
        else:
            # 어댑터가 있는 출처만 돈다. 등록만 되고 수집 방법이 없는 출처는 건너뛴다.
            #
            # **꺼 둔 출처는 돌지 않는다.**
            # 네이버 뉴스 검색이 그렇다 — 네이버가 검색 API 신규 등록을
            # 중단해서 401 이 계속 났고, 키를 다시 받을 방법이 없다.
            # 그런데도 매 실행마다 8건씩 실패해 "오류 8" 이 찍혔다.
            # 고칠 수 없는 오류가 매일 찍히면, 고칠 수 있는 오류가 났을 때
            # 그게 안 보인다.
            #
            # 이름으로 거르지 않고 status 로 거른다 — 왜 껐는지는
            # settings.disabled_reason 에 남아 있다.
            sources = [
                s
                for s in db.execute(select(Source).order_by(Source.display_name)).scalars()
                if adapters_for(s) and s.status != "DISABLED"
            ]

        for source in sources:
            adapters = adapters_for(source)
            if not adapters:
                print(f"'{source.canonical_domain}' 에 맞는 어댑터가 없습니다.")
                continue

            for adapter_cls in adapters:
                # 법령 어댑터만 공용 클라이언트를 받는다.
                collector = (
                    adapter_cls(law_client)
                    if adapter_cls in (LawCollector, AdmRulCollector, UpcomingLawCollector)
                    else adapter_cls()
                )
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
                    f"· 동일 {stats.unchanged}"
                    # 세무와 무관해서 안 담은 것. 조용히 버리면 수집기가
                    # 고장 났을 때 "원래 안 오는 건가" 와 구분되지 않는다.
                    + (f" · 세무 무관 {stats.off_topic}" if stats.off_topic else "")
                    + f" · 오류 {stats.errors}  [{run.status}]"
                )
                for detail in stats.error_details[:5]:
                    print(f"    ! {detail['item']}: {detail['error'][:120]}")

                for key in ("discovered", "new", "changed", "unchanged", "errors"):
                    total[key] += getattr(stats, key)

                # **출처마다 커밋한다.**
                # 맨 끝에 한 번만 커밋했더니, 뒤쪽 출처에서 예외가 나면 앞에서
                # 멀쩡히 수집한 것과 실행 기록까지 통째로 롤백됐다. 로그에는
                # "조회 172 · 변경 1" 이 찍혀 있는데 DB 에는 아무것도 없는 상태가 된다.
                # 외부 API 를 여러 개 도는 작업은 중간에 하나가 죽는다고 보고 짜야 한다.
                if not args.dry_run:
                    db.commit()

        if args.dry_run:
            db.rollback()
            print("\n[dry-run] 롤백했습니다.")
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
