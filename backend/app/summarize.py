"""수집된 원문을 AI 로 요약해 콘텐츠 본문에 채운다.

    python -m app.summarize --limit 10        # 10건만 (먼저 품질 확인)
    python -m app.summarize                   # 미요약 전체
    python -m app.summarize --force           # 이미 요약된 것도 다시

**한 번 요약하면 다시 부르지 않는다.** ai_analyses 가 input_hash 로 결과를 보관하고,
같은 원문·같은 프롬프트·같은 모델이면 저장된 결과를 재사용한다 (§9.5).
법령은 개정되면 새 버전이 되므로, 사실상 건당 1회만 호출된다.

AI 출력은 **초안이다.** 여기서 채운 내용은 검수자가 원문과 대조해 고칠 수 있고,
고치면 승인이 해제된다 (§1.3, AT-07).
"""

from __future__ import annotations

import argparse
import sys
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.tables import ContentSource, ContentVersion, TaxContent
from app.services.ai import runner
from app.services.ai.contract import AnalysisOutput

logger = get_logger(__name__)

#: AI 가 채우는 본문 키. 이 키들이 공개 화면의 각 블록으로 그대로 간다.
AI_BODY_KEYS = ("affected_users", "excluded_users", "changes", "business_impact",
                "required_actions", "needs_expert")


def _to_body(output: AnalysisOutput) -> dict[str, list[str]]:
    """계약 스키마 출력을 화면이 읽는 본문 구조로 옮긴다."""
    return {
        "affected_users": list(output.affected_users),
        "excluded_users": list(output.excluded_users),
        "changes": [item.text for item in output.changes],
        "business_impact": [item.text for item in output.business_impact],
        "required_actions": [item.text for item in output.required_actions],
        # 경고는 "전문가 확인이 필요한 항목"으로 보여준다 — 사업자에게는
        # 내부 코드보다 "무엇을 더 확인해야 하는가"가 필요하다.
        "needs_expert": [w.message for w in output.warnings],
    }


def _already_summarized(body: dict) -> bool:
    return bool(body.get("changes")) and body.get("_ai") is True


def run(
    db: Session,
    *,
    limit: int,
    force: bool,
    only_id: UUID | None = None,
    pace_seconds: float = 0.0,
) -> dict[str, int]:
    stats = {"대상": 0, "요약": 0, "재사용": 0, "차단": 0, "건너뜀": 0, "실패": 0}

    stmt = select(TaxContent).order_by(TaxContent.promulgation_date.desc().nullslast())
    if only_id is not None:
        stmt = stmt.where(TaxContent.id == only_id)

    for content in db.execute(stmt).scalars():
        # 한도는 **시도 횟수**를 센다. 성공만 세면 계속 실패할 때 멈추지 않는다.
        if stats["대상"] >= limit:
            break

        version = (
            db.get(ContentVersion, content.current_version_id)
            if content.current_version_id
            else None
        )
        if version is None:
            stats["건너뜀"] += 1
            continue

        body = dict(version.body or {})
        if not force and _already_summarized(body):
            stats["건너뜀"] += 1
            continue

        source_ids = list(
            db.execute(
                select(ContentSource.raw_content_version_id).where(
                    ContentSource.tax_content_id == content.id
                )
            ).scalars()
        )
        if not source_ids:
            stats["건너뜀"] += 1
            continue

        stats["대상"] += 1
        if pace_seconds and stats["대상"] > 1:
            # 무료 티어는 분당 토큰 한도가 있다. 제공자 안에서도 429 를 재시도하지만,
            # 애초에 몰아치지 않는 편이 전체적으로 빠르다.
            time.sleep(pace_seconds)

        try:
            result = runner.run_analysis(
                db, source_version_ids=source_ids, tax_content_id=content.id
            )
        except Exception as exc:
            stats["실패"] += 1
            print(f"  ! {content.title[:36]}: {type(exc).__name__}: {exc}"[:150])
            continue

        if result.output is None:
            stats["차단"] += 1
            print(f"  x {content.title[:36]}: 스키마 검증 실패 (검수 큐로)")
            continue

        body.update(_to_body(result.output))
        body["_ai"] = True
        version.body = body

        # 한 줄 요약과 주제는 콘텐츠 레벨에도 반영한다 (목록에 보이는 값).
        if result.output.one_line_summary:
            content.one_line_summary = result.output.one_line_summary[:250]

        db.flush()
        if result.reused:
            stats["재사용"] += 1
            print(f"  = {content.title[:36]} (저장된 결과 재사용)")
        else:
            stats["요약"] += 1
            blocked = " [검수 필요]" if result.report.blocked else ""
            print(f"  + {content.title[:36]}{blocked}")

    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="수집 원문 AI 요약")
    p.add_argument("--limit", type=int, default=1000, help="시도할 최대 건수")
    p.add_argument("--force", action="store_true", help="이미 요약된 것도 다시")
    p.add_argument("--id", help="특정 콘텐츠만")
    p.add_argument(
        "--pace",
        type=float,
        default=6.0,
        help="호출 간 대기 초. 무료 티어 분당 한도를 피한다 (기본 6)",
    )
    args = p.parse_args(argv)

    settings = get_settings()
    configure_logging(debug=False)

    if settings.ai_provider == "stub":
        print(
            "AI 제공자가 stub 입니다. 실제 요약을 만들려면 .env 에 설정하세요:\n"
            "  TAXBRIEFING_AI_PROVIDER=groq\n"
            "  TAXBRIEFING_AI_API_KEY=<GROQ 키>\n"
            f"  TAXBRIEFING_AI_MODEL={settings.ai_model}",
            file=sys.stderr,
        )
        return 2

    print(f"제공자 {settings.ai_provider} · 모델 {settings.ai_model}\n")

    db = SessionLocal()
    try:
        stats = run(
            db,
            limit=args.limit,
            force=args.force,
            only_id=UUID(args.id) if args.id else None,
            pace_seconds=args.pace,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"\n대상 {stats['대상']} · 요약 {stats['요약']} · 재사용 {stats['재사용']} "
        f"· 차단 {stats['차단']} · 건너뜀 {stats['건너뜀']} · 실패 {stats['실패']}"
    )
    if stats["차단"]:
        print("\n차단된 건은 ai_analyses 에 원본이 남아 있습니다. 검수 화면에서 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["AI_BODY_KEYS", "main", "run"]
