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
from app.domain.industry import is_internal_document
from app.models.tables import ContentSource, ContentVersion, TaxContent
from app.services.ai import runner
from app.services.ai.contract import AnalysisOutput

logger = get_logger(__name__)

#: AI 가 채우는 본문 키. 이 키들이 공개 화면의 각 블록으로 그대로 간다.
AI_BODY_KEYS = ("affected_users", "excluded_users", "changes", "business_impact",
                "required_actions", "needs_expert")


#: 화면에 그대로 나가면 안 되는 값. 모델이 null 을 준 것을 문자열로 굳힌 흔적이다.
_PLACEHOLDER = {"none", "null", "n/a", "na", "-", "없음", "undefined"}


def _clean(value: str | None) -> str:
    """저장된 값에도 방어한다.

    생성 쪽을 고쳐도 **이미 저장된 분석 결과**에는 "None" 이 남아 있고,
    그것을 재사용할 때 다시 화면으로 나간다. 읽는 쪽에서도 막아야 한다.
    """
    text = (value or "").strip()
    return "" if text.lower() in _PLACEHOLDER else text


def _clean_list(values: list[str]) -> list[str]:
    return [t for t in (_clean(v) for v in values) if t]


def _to_body(output: AnalysisOutput) -> dict[str, list[str]]:
    """계약 스키마 출력을 화면이 읽는 본문 구조로 옮긴다."""
    return {
        "affected_users": _clean_list(list(output.affected_users)),
        "excluded_users": _clean_list(list(output.excluded_users)),
        "changes": _clean_list([item.text for item in output.changes]),
        "business_impact": _clean_list([item.text for item in output.business_impact]),
        "required_actions": _clean_list([item.text for item in output.required_actions]),
        # 경고는 "전문가 확인이 필요한 항목"으로 보여준다 — 사업자에게는
        # 내부 코드보다 "무엇을 더 확인해야 하는가"가 필요하다.
        "needs_expert": _clean_list([w.message for w in output.warnings]),
    }


def _already_summarized(body: dict) -> bool:
    """AI 를 이미 돌렸는가.

    **`changes` 가 비었는지는 보지 않는다.** 빈 배열은 실패가 아니라 정상적인
    결과다 — 프롬프트가 "실질 변경이 하나도 없으면 changes 를 빈 배열로 두라"고
    시킨다. 자구 정리나 인용 조문 번호만 바뀐 개정이 여기 해당한다.

    이전에는 `bool(body["changes"]) and body["_ai"]` 였다. 그래서 실질 변경이
    없는 건이 영원히 "아직 요약 안 됨"으로 남아, 돌릴 때마다 다시 집혔고
    한도만 태웠다. 한 배치에서 24건 중 22건이 그런 재처리였다.

    판단 기준은 하나다 — 우리가 이 본문에 AI 를 돌렸는가.
    """
    return body.get("_ai") is True


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

        # 화면에서 숨기는 기관 내부 문서는 요약하지 않는다.
        # "국세청 인사관리규정" 을 사장님용 문장으로 옮겨 봐야 아무도 안 보고,
        # 무료 티어의 분당 토큰은 정작 필요한 개정에서 모자란다.
        if not force and is_internal_document(content.title):
            stats["건너뜀"] += 1
            continue

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

        # 한 줄 요약은 콘텐츠 레벨에도 반영한다 (목록에 보이는 값).
        summary = _clean(result.output.one_line_summary)
        if summary:
            content.one_line_summary = summary[:250]

        # 건별로 커밋한다. 수십 건을 돌리는 작업이라 마지막에 한 번만 저장하면
        # 중간에 끊겼을 때 이미 지불한 API 호출이 통째로 날아간다.
        db.commit()

        if result.reused:
            stats["재사용"] += 1
            print(f"  = {content.title[:36]} (저장된 결과 재사용)", flush=True)
        else:
            stats["요약"] += 1
            blocked = " [검수 필요]" if result.report.blocked else ""
            print(f"  + {content.title[:36]}{blocked}", flush=True)

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
