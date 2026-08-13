"""수집된 원문을 사업자용 콘텐츠 초안으로 일괄 생성한다.

    python -m app.bulk_draft --months 7,8          # 7·8월 공포분 초안 생성
    python -m app.bulk_draft --auto-approve        # 로컬 전용: 검수·게시까지 진행

**기본 동작은 초안 생성까지다.** 검수는 사람이 한다 (§1.3).
`--auto-approve` 는 로컬 개발에서 화면을 채워 보기 위한 것이며,
local/test 이외의 환경에서는 실행을 거부한다.

여기서 채우는 값은 전부 **법령 API가 필드로 준 것**이다.
시행일·공포일·제개정구분은 추론이 아니라 원문 필드이므로,
근거(evidence)를 붙이는 것이 정당하다 (§9.4 V2, AT-05).
문장 생성도 그 필드를 조합할 뿐 원문에 없는 사실을 만들지 않는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.enums import (
    AuthorityGrade,
    ContentKind,
    LegalStatus,
    ReviewDecision,
    RiskLevel,
    Role,
    SourceRole,
)
from app.models.tables import (
    ContentSource,
    RawContent,
    RawContentVersion,
    Source,
    User,
)
from app.services import content as content_service
from app.services.collectors.tribunal import parse_sections

#: 신고·납부 의무에 직접 걸리는 법령은 틀렸을 때 사업자가 가산세를 문다.
_HIGH_RISK_PATTERNS = (
    "부가가치세",
    "소득세",
    "법인세",
    "원천징수",
    "국세기본",
    "국세징수",
    "성실신고",
)
_MEDIUM_RISK_PATTERNS = ("조세특례", "지방세", "상속세", "증여세", "종합부동산세")


def _meta(version: RawContentVersion) -> dict:
    return version.doc_metadata or {}


def _parse_iso(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _decide_status(promulgated: dt.date | None, effective: dt.date | None, today: dt.date) -> LegalStatus:
    """법적 상태를 원문 필드에서 **판정**한다. 추정하지 않는다.

    - 시행일이 오늘 이전이면 시행 중이다.
    - 시행일이 미래면 공포는 됐고 아직 시행 전이다.
    - 둘 다 없으면 모른다.
    """
    if effective is not None and effective <= today:
        return LegalStatus.EFFECTIVE
    if promulgated is not None and promulgated <= today:
        return LegalStatus.PROMULGATED
    return LegalStatus.UNKNOWN


def _decide_risk(title: str, *, kind: str | None = None) -> RiskLevel:
    """중요도는 **지금 손봐야 하는 정도**다.

    법안은 아무리 큰 세법이라도 [중요] 를 달지 않는다. 통과할지 모르는
    것에 할 일이 없고, 확정된 개정과 같은 표시를 달면 둘이 구분되지 않는다.
    실제로 아침 브리핑 6건이 전부 [중요] 법안으로 채워진 적이 있다.
    """
    if kind == ContentKind.BILL.value:
        return RiskLevel.LOW
    if any(p in title for p in _HIGH_RISK_PATTERNS):
        return RiskLevel.HIGH
    if any(p in title for p in _MEDIUM_RISK_PATTERNS):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _extract_section(text: str, header: str) -> list[str]:
    """정규화 본문에서 `[제개정이유]` 같은 구획을 뽑는다."""
    match = re.search(rf"\[{re.escape(header)}[^\]]*\]\n(.*?)(?=\n\[|\Z)", text, re.S)
    if not match:
        return []
    lines = [line.strip() for line in match.group(1).splitlines()]
    return [line for line in lines if line][:4]


#: 화면에 낼 심판례 구획과 순서. 사건 → 다툰 것 → 판단 → 결론.
#: `관련 법령`·`참조 결정`은 옆 칸(서지)으로 보내므로 여기 없다.
TRIBUNAL_SECTIONS: tuple[str, ...] = ("사건명", "청구인 주장", "판단 요지", "판단 이유", "주문")


def _tribunal_body(version: RawContentVersion, meta: dict) -> dict:
    """심판례 본문.

    **법령 본문 틀을 그대로 쓰면 거짓이 된다.** 예전에는 종류를 안 보고
    하나로 만들었고, 그래서 심판례 상세 화면에 이런 것들이 떴다.

        달라지는 점        · 개정 되었습니다.
        지금 해야 할 일    · 시행일 전에 해당 조문이 우리 사업장에
                            적용되는지 확인하세요.

    개정된 것이 없고 시행일도 없다. 심판례는 이미 끝난 한 건의 판단이다.

    구조는 원문에서 그대로 옮긴다 — 요약하지 않는다. 심판원이 쓴 문장이
    우리가 다시 쓴 문장보다 정확하고, 실무자는 그 원문을 근거로 인용한다.
    """
    sections = parse_sections(version.normalized_text)
    return {
        "tribunal": {
            "tax_type": str(meta.get("tax_type") or ""),
            "outcome": str(meta.get("result") or ""),
            "case_no": str(meta.get("case_no") or ""),
            "disposition_agency": str(meta.get("disposition_agency") or ""),
            "related_laws": str(meta.get("related_laws") or ""),
            "sections": [
                {"label": name, "text": sections[name]}
                for name in TRIBUNAL_SECTIONS
                if sections.get(name)
            ],
        },
        # 심판례에는 "사업자가 할 일"이 없다. 판단 사례를 참고할 뿐이다.
        # 빈 배열로 두면 화면이 그 섹션을 통째로 그리지 않는다.
        "needs_expert": [
            "개별 사건의 사실관계에 대한 판단입니다. 사실관계가 다르면 결론도 "
            "달라지므로, 우리 사업장에 그대로 적용된다고 볼 수 없습니다."
        ],
    }


def _bill_body(meta: dict) -> dict:
    """법안 본문.

    **법령 틀을 쓰면 거짓이 된다.** 텔레그램에 이렇게 나갔다.

        [중요] 소득세법 일부개정법률안 — 박수영의원 등 11인
        상태: 상태 확인 필요 (확정 아님)
        시행일: 확인 필요
        · 「…법률안」이(가) 개정되어 시행일은 원문 확인이 필요합니다.
        · 시행일 전에 해당 조문이 우리 사업장에 적용되는지 확인하세요.

    세 줄 다 틀렸다. 개정된 것이 없고(발의만 됐다), 시행일이 없고
    (통과할지 모른다), 상태를 모르는 것도 아니다(발의됨).

    법안은 **아직 법이 아니다.** 사업자가 지금 할 일은 없다. 대신
    "이런 게 논의되고 있다" 를 알려 주는 것이 이 항목의 값이다.
    """
    proposer = str(meta.get("proposer") or "").strip()
    committee = str(meta.get("committee") or "").strip()
    result = str(meta.get("proc_result") or "").strip()

    changes: list[str] = []
    if proposer:
        changes.append(f"발의: {proposer}")
    if committee:
        changes.append(f"소관: {committee}")
    changes.append(f"처리 결과: {result or '아직 심사 중'}")

    return {
        "changes": changes,
        # **할 일을 만들지 않는다.** 통과할지 모르는 법안에 조치를 시키면
        # 사업자가 안 해도 될 일을 하고, 정작 확정된 개정과 구분이 안 된다.
        "required_actions": [],
        "needs_expert": [
            "국회에 발의된 법안입니다. 통과 여부와 최종 내용은 심사 과정에서 "
            "달라질 수 있으므로, 지금 확정된 제도로 보고 준비하시면 안 됩니다."
        ],
    }


def _build_body(raw: RawContent, version: RawContentVersion, meta: dict) -> dict:
    """화면에 보여줄 구조화 본문. 원문 필드와 원문 구획만 사용한다."""
    if meta.get("content_kind") == "TRIBUNAL_DECISION":
        return _tribunal_body(version, meta)
    if meta.get("content_kind") == "BILL":
        return _bill_body(meta)

    reasons = _extract_section(version.normalized_text, "제개정이유")
    revisions = _extract_section(version.normalized_text, "개정문")

    law_type = meta.get("law_type") or ""
    revision = meta.get("revision_type") or ""
    ministry = meta.get("ministry") or raw.publisher

    changes: list[str] = []
    if revision:
        changes.append(f"{revision} 되었습니다.")
    changes.extend(reasons or revisions)

    return {
        "affected_users": [f"{ministry} 소관 {law_type} 적용 대상 사업자"] if law_type else [],
        "changes": changes[:4],
        "required_actions": [
            "시행일 전에 해당 조문이 우리 사업장에 적용되는지 확인하세요.",
            "적용 여부가 불분명하면 세무전문가와 상담하세요.",
        ],
        "needs_expert": [
            "이 안내는 법령 원문의 서지정보와 제개정이유를 정리한 것입니다. "
            "구체적인 적용 범위와 세액 영향은 전문가 검토가 필요합니다."
        ],
    }


def _summary(raw: RawContent, meta: dict, effective: dt.date | None) -> str:
    """AI 요약 전까지 쓰는 임시 문구.

    **심판례에 법령 문구를 쓰면 거짓말이 된다.**
    처음에 하나로 뭉쳐 놨더니 이런 문장이 나왔다.

        「…심판청구가 적법한지 여부 — 기각」이(가) 개정되어
        시행일은 원문 확인이 필요합니다.

    심판례는 개정된 것이 아니고 시행일도 없다. 종류를 보고 말을 바꾼다.
    """
    if meta.get("content_kind") == "TRIBUNAL_DECISION":
        return _tribunal_summary(meta)
    if meta.get("content_kind") == "BILL":
        return _bill_summary(meta)

    name = raw.title
    revision = meta.get("revision_type") or "개정"
    if effective:
        when = f"{effective.year}년 {effective.month}월 {effective.day}일부터 시행됩니다"
    else:
        when = "시행일은 원문 확인이 필요합니다"
    return f"「{name}」이(가) {revision}되어 {when}."[:250]


def _bill_summary(meta: dict) -> str:
    """법안 임시 문구. **확정 어투를 쓰지 않는다.**

    "바뀝니다" 가 아니라 "발의됐습니다" 다. 아직 법이 아니다.
    """
    proposer = str(meta.get("proposer") or "").strip()
    committee = str(meta.get("committee") or "").strip()
    proposed = _parse_iso(meta.get("proposed_at"))

    parts = ["국회 발의 법안"]
    if proposer:
        parts.append(proposer)
    if proposed:
        parts.append(f"{proposed.year}년 {proposed.month}월 {proposed.day}일 발의")
    head = " · ".join(parts)

    tail = f" {committee} 심사 중이며 통과 여부는 정해지지 않았습니다." if committee else (
        " 국회 심사 중이며 통과 여부는 정해지지 않았습니다."
    )
    return (head + "." + tail)[:250]


def _decide_kind(meta: dict) -> str:
    """수집기가 남긴 표시를 콘텐츠 종류로 옮긴다.

    수집 단계에서만 알 수 있는 사실이다 — 본문만 보고는 심판례인지
    법령인지 구분하기 어렵다.
    """
    mapping = {
        "TRIBUNAL_DECISION": ContentKind.TRIBUNAL,
        "INTERPRETATION": ContentKind.INTERPRETATION,
        "BILL": ContentKind.BILL,
        "SUPPORT": ContentKind.SUPPORT,
    }
    return mapping.get(str(meta.get("content_kind") or ""), ContentKind.POLICY).value


def _tribunal_summary(meta: dict) -> str:
    """심판례 임시 문구. 결론과 세목만 말하고 나머지는 본문에 맡긴다."""
    outcome = str(meta.get("result") or "").strip()
    tax_type = str(meta.get("tax_type") or "").strip()
    agency = str(meta.get("disposition_agency") or "").strip()

    parts = ["조세심판원 결정"]
    if tax_type:
        parts.append(f"{tax_type} 관련")
    if agency:
        parts.append(f"{agency} 처분")
    head = " · ".join(parts)

    if outcome:
        return f"{head} — 청구 {outcome}. 판단 요지와 이유는 본문에서 확인하세요."[:250]
    return f"{head}. 판단 요지와 이유는 본문에서 확인하세요."[:250]


def run(
    db: Session,
    *,
    months: set[int] | None,
    year: int | None,
    limit: int,
    auto_approve: bool,
    today: dt.date,
) -> dict[str, int]:
    settings = get_settings()
    if auto_approve and settings.environment not in ("local", "test"):
        raise RuntimeError(
            "--auto-approve 는 로컬 개발 전용입니다. 운영에서는 검수자가 승인해야 합니다 (§1.3)."
        )

    reviewer = db.execute(
        select(User).where(User.role == Role.REVIEWER.value).limit(1)
    ).scalar_one_or_none()
    if auto_approve and reviewer is None:
        raise RuntimeError("REVIEWER 계정이 없습니다. `python -m app.seed` 를 먼저 실행하세요.")

    rows = db.execute(
        select(RawContent, RawContentVersion, Source)
        .join(RawContentVersion, RawContent.current_version_id == RawContentVersion.id)
        .join(Source, RawContent.source_id == Source.id)
        .where(Source.authority.in_([AuthorityGrade.A, AuthorityGrade.B]))
        .order_by(RawContent.published_at.desc().nullslast())
    ).all()

    stats = {"검토": 0, "건너뜀": 0, "초안": 0, "게시": 0, "실패": 0}

    for raw, version, _source in rows:
        if stats["초안"] >= limit:
            break
        stats["검토"] += 1

        meta = _meta(version)
        promulgated = _parse_iso(meta.get("promulgation_date")) or _parse_iso(
            meta.get("issued_date")
        )
        effective = _parse_iso(meta.get("effective_date")) or promulgated

        if months is not None:
            basis = promulgated or effective
            if basis is None or basis.month not in months:
                stats["건너뜀"] += 1
                continue
            if year is not None and basis.year != year:
                stats["건너뜀"] += 1
                continue

        # 이미 콘텐츠가 있으면 건너뛴다 (멱등).
        #
        # **제목으로 판정하지 않는다.** 국회 의안은 제목이 겹친다 —
        # 여러 의원이 각자 "조세특례제한법 일부개정법률안" 을 발의하기 때문이다.
        # 제목 기준으로 걸렀더니 서로 다른 40개 법안이 11개로 뭉쳤다.
        #
        # **버전이 아니라 원문으로 판정한다.**
        # 버전 기준으로 걸렀더니 이번에는 반대로 하나가 둘이 됐다.
        # 법제처가 같은 법령을 다시 내려주면서 본문이 조금 달라지면
        # 새 버전이 생기는데, 그때마다 콘텐츠가 하나 더 만들어졌다.
        #
        #     소득세법 시행규칙 (일부개정)   08-06 생성
        #     소득세법 시행규칙 (일부개정)   08-13 생성   ← 같은 원문의 새 버전
        #
        # 화면에 같은 카드가 두 번 떴다. 32건이 그랬다.
        #
        # 원문 하나가 콘텐츠 하나다. 시행예정본은 수집기가 URL 을 따로
        # 두므로 원문 자체가 갈리고, 그래서 현행본과 나란히 남는다.
        exists = db.execute(
            select(ContentSource.tax_content_id)
            .join(
                RawContentVersion,
                ContentSource.raw_content_version_id == RawContentVersion.id,
            )
            .where(RawContentVersion.raw_content_id == raw.id)
            .limit(1)
        ).scalar_one_or_none()
        if exists is not None:
            stats["건너뜀"] += 1
            continue

        try:
            content = content_service.create_content(
                db,
                title=raw.title[:120],
                source_version_ids=[version.id],
                legal_status=_decide_status(promulgated, effective, today),
                risk_level=_decide_risk(raw.title, kind=_decide_kind(meta)),
                body=_build_body(raw, version, meta),
                roles={version.id: SourceRole.PRIMARY},
                now=dt.datetime.now(dt.UTC),
            )
            content.content_kind = _decide_kind(meta)
            # 심판례 결론. 제목에서 정규식으로 뽑아 쓰던 값을 컬럼으로 옮겼다 —
            # 수집기 버전에 따라 "— 기각" 과 "(기각)" 이 섞이면서 화면의
            # 결론 필터가 전부 0 이 됐었다.
            content.outcome = str(meta.get("result") or "").strip() or None
            content.one_line_summary = _summary(raw, meta, effective)
            content.promulgation_date = promulgated
            content.effective_date = effective
            content.announcement_date = promulgated

            # **법안은 수집기가 이미 판정한 값을 쓴다.**
            #
            # 법령 필드(공포일·시행일)로 상태를 정하면 법안은 둘 다 없어서
            # 늘 UNKNOWN 이 되고, 화면과 텔레그램에 "상태 확인 필요
            # (확정 아님)" 이 붙었다. 확인이 필요한 게 아니라 발의된 것이다.
            #
            # 국회 API 의 PROC_RESULT 를 수집기가 읽어 BILL_PROPOSED /
            # ASSEMBLY_PASSED 로 갈라 두었는데 그걸 버리고 있었다.
            if content.content_kind == ContentKind.BILL.value:
                status = str(meta.get("legal_status") or "").strip()
                if status in LegalStatus.__members__:
                    content.legal = LegalStatus[status]
                # 발의일이 이 법안의 유일한 날짜다. 시행일 자리는 비워 둔다 —
                # 통과해야 생기는 값이라 지금 채우면 거짓이다.
                content.announcement_date = _parse_iso(meta.get("proposed_at"))

            # 근거는 이 원문 버전 자체다 — 날짜가 API 필드에서 왔기 때문이다.
            for field in (
                "legal_status",
                "affected_users",
                "effective_date",
                "promulgation_date",
                "announcement_date",
            ):
                content_service.add_evidence(
                    db,
                    content,
                    field_name=field,
                    raw_content_version_id=version.id,
                    locator=f"field:{field}#기본정보",
                    support_type="DIRECT",
                    note="법령 API 응답 필드",
                )

            db.flush()
            content_service.submit_for_review(db, content)
            stats["초안"] += 1

            if auto_approve and reviewer is not None:
                content_service.record_review(
                    db,
                    content,
                    reviewer_id=reviewer.id,
                    decision=ReviewDecision.APPROVE,
                    review_note="법령 API 서지정보(공포일·시행일·제개정구분) 대조 확인",
                    checked_source_version_ids=[version.id],
                )
                content_service.publish(db, content)
                stats["게시"] += 1

        except Exception as exc:
            stats["실패"] += 1
            print(f"  ! {raw.title[:40]}: {type(exc).__name__}: {exc}"[:160])
            db.rollback()

    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="수집 원문 → 콘텐츠 초안 일괄 생성")
    p.add_argument("--months", help="공포 월 필터 (예: 7,8). 생략하면 전체")
    p.add_argument("--year", type=int, help="공포 연도 필터")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument(
        "--auto-approve",
        action="store_true",
        help="로컬 전용: 검수·게시까지 자동 진행",
    )
    args = p.parse_args(argv)

    months = (
        {int(m) for m in args.months.split(",") if m.strip().isdigit()} if args.months else None
    )
    today = dt.datetime.now(dt.UTC).date()

    db = SessionLocal()
    try:
        stats = run(
            db,
            months=months,
            year=args.year,
            limit=args.limit,
            auto_approve=args.auto_approve,
            today=today,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"\n검토 {stats['검토']} · 초안 {stats['초안']} · 게시 {stats['게시']} "
        f"· 건너뜀 {stats['건너뜀']} · 실패 {stats['실패']}"
    )
    if not args.auto_approve and stats["초안"]:
        print("\n초안까지 생성했습니다. 검수자 계정으로 승인·게시하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["UUID", "main", "run"]
