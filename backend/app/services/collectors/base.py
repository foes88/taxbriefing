"""수집 어댑터 공통 인터페이스 (§6.2 collector-worker, FR-SRC-002~004).

어댑터는 **원문을 가져오는 일만** 한다. 중복 판정·버전 생성·해시는
services.ingest 가 담당하므로 어댑터가 다시 구현하지 않는다.
그래야 어떤 출처를 붙여도 AT-01(멱등 수집)·AT-02(버전 생성)가 자동으로 성립한다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger, get_trace_id
from app.models.tables import Source, SourceRun
from app.services.ingest import IngestOutcome

logger = get_logger(__name__)


@dataclass
class CollectStats:
    """수집 결과 집계. source_runs 에 그대로 저장된다 (FR-SRC-003)."""

    discovered: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    #: 주제가 맞지 않아 담지 않은 것. 뉴스 RSS 에서 세무와 무관한 기사가
    #: 여기 잡힌다. **숫자로 남긴다** — 조용히 버리면 수집기가 고장 났을 때
    #: "원래 안 오는 건가" 와 구분되지 않는다.
    off_topic: int = 0
    errors: int = 0
    error_details: list[dict[str, Any]] = field(default_factory=list)

    def record(self, outcome: IngestOutcome) -> None:
        if outcome is IngestOutcome.NEW:
            self.new += 1
        elif outcome is IngestOutcome.CHANGED:
            self.changed += 1
        else:
            self.unchanged += 1

    def fail(self, item: str, exc: Exception) -> None:
        self.errors += 1
        # 한 건이 실패해도 나머지는 계속 수집한다. 전체 중단은 최악의 선택이다.
        self.error_details.append(
            {"item": item, "error": f"{type(exc).__name__}: {exc}"[:500]}
        )
        logger.warning("collector.item_failed", item=item, error=str(exc)[:200])

    def as_summary(self) -> dict[str, Any]:
        return {"errors": self.error_details[:50]}


class Collector(Protocol):
    """출처 하나를 수집하는 어댑터."""

    name: str
    version: str

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats: ...


def run_collection(
    db: Session,
    *,
    source: Source,
    collector: Collector,
    since: dt.date | None = None,
    limit: int = 50,
    run_type: str = "SCHEDULED",
    now: dt.datetime | None = None,
) -> tuple[SourceRun, CollectStats]:
    """수집을 실행하고 이력을 남긴다 (FR-SRC-003).

    어댑터가 통째로 실패해도 source_runs 에 FAILED 로 기록한다.
    "왜 오늘 자료가 안 들어왔는가"에 답할 수 없으면 운영이 불가능하다 (§13.1).
    """
    now = now or dt.datetime.now(dt.UTC)
    run = SourceRun(
        source_id=source.id,
        run_type=run_type,
        started_at=now,
        status="RUNNING",
        trace_id=get_trace_id(),
    )
    db.add(run)
    db.flush()

    try:
        stats = collector.collect(db, source, since=since, limit=limit)
    except Exception as exc:
        run.status = "FAILED"
        run.finished_at = dt.datetime.now(dt.UTC)
        run.error_count = 1
        run.error_summary = {"fatal": f"{type(exc).__name__}: {exc}"[:500]}
        source.failure_streak += 1
        db.flush()
        logger.error(
            "collector.run_failed", source=source.display_name, error=str(exc)[:300]
        )
        raise

    run.status = "PARTIAL" if stats.errors else "SUCCESS"
    run.finished_at = dt.datetime.now(dt.UTC)
    run.discovered_count = stats.discovered
    run.new_count = stats.new
    run.changed_count = stats.changed
    run.error_count = stats.errors
    run.error_summary = stats.as_summary()

    if stats.errors:
        source.failure_streak += 1
    else:
        source.failure_streak = 0
        source.last_success_at = run.finished_at

    db.flush()
    logger.info(
        "collector.run_finished",
        source=source.display_name,
        status=run.status,
        discovered=stats.discovered,
        new=stats.new,
        changed=stats.changed,
        errors=stats.errors,
    )
    return run, stats


def source_by_domain(db: Session, domain: str) -> Source | None:
    from sqlalchemy import select

    return db.execute(
        select(Source).where(Source.canonical_domain == domain)
    ).scalar_one_or_none()


__all__ = [
    "UUID",
    "CollectStats",
    "Collector",
    "run_collection",
    "source_by_domain",
]
