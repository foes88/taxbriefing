"""텔레그램 요약 메시지 렌더링 (ADR-001).

텔레그램은 **알림 채널**이다. 표·근거·정정 이력은 웹이 담당하고,
여기서는 사업자가 3초 안에 판단할 수 있는 최소 정보와 링크만 보낸다.

§9.4 V7 원칙에 따라 모델이 아니라 이 템플릿이 표현을 만든다.
근거 없는 값은 렌더링 단계에서도 만들어내지 않는다 — 시행일이 없으면
날짜를 비우는 게 아니라 "시행일 확인 필요"라고 쓴다 (§10.4).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.domain.enums import LegalStatus, RiskLevel

# §10.4 배지 라벨. legal_status 를 사용자 표현으로 옮기는 유일한 지점이다.
STATUS_LABEL: dict[LegalStatus, str] = {
    LegalStatus.EFFECTIVE: "시행 중",
    LegalStatus.PROMULGATED: "공포",
    LegalStatus.ASSEMBLY_PASSED: "국회 통과",
    LegalStatus.GOV_ANNOUNCED: "정부안 발표",
    LegalStatus.PREANNOUNCED: "입법·행정예고",
    LegalStatus.BILL_PROPOSED: "법안 발의",
    LegalStatus.DISCUSSION: "검토·논의",
    LegalStatus.SUSPENDED: "유예·효력정지",
    LegalStatus.ABOLISHED: "폐지",
    LegalStatus.UNKNOWN: "상태 확인 필요",
}

# 확정되지 않은 상태에 반드시 붙는 경고 문구 (§10.4).
STATUS_CAVEAT: dict[LegalStatus, str] = {
    LegalStatus.ASSEMBLY_PASSED: "공포·시행일 확인 필요",
    LegalStatus.GOV_ANNOUNCED: "시행 확정 아님",
    LegalStatus.PREANNOUNCED: "시행 확정 아님 · 최종안 변경 가능",
    LegalStatus.BILL_PROPOSED: "시행 확정 아님",
    LegalStatus.DISCUSSION: "확정 아님",
    LegalStatus.PROMULGATED: "시행일 확인",
    LegalStatus.SUSPENDED: "적용 중단",
    LegalStatus.ABOLISHED: "폐지일·경과조치 확인",
    LegalStatus.UNKNOWN: "확정 아님",
}


def caveat_for(status: LegalStatus, effective_date: dt.date | None) -> str | None:
    """상태에 붙일 경고. 없으면 None.

    **공포됐고 시행일도 아는 건에는 경고를 붙이지 않는다.**

    "공포" 의 경고 문구는 원래 시행일이 안 적힌 경우를 위한 것이었다.
    그런데 시행예정 법령을 수집하면서 시행일이 명확한 공포 건이 34건 들어왔고,
    화면이 이렇게 됐다.

        2027년 1월 1일 시행 예정
        ▲ 시행일 확인

    날짜를 보여주면서 그 날짜를 확인하라고 하는 셈이다. 경고가 이런 식으로
    남발되면 정작 진짜 경고(입법예고는 최종안이 바뀔 수 있다)가 안 읽힌다.

    다른 상태는 그대로다 — 입법예고·발의는 시행일을 알아도 확정이 아니다.
    """
    if status is LegalStatus.PROMULGATED and effective_date is not None:
        return None
    return STATUS_CAVEAT.get(status)

RISK_PREFIX: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "[긴급]",
    RiskLevel.HIGH: "[중요]",
    RiskLevel.MEDIUM: "[안내]",
    RiskLevel.LOW: "[참고]",
}


@dataclass(frozen=True)
class BriefingCard:
    """텔레그램 한 건에 담을 내용. 승인된 콘텐츠에서만 만든다."""

    title: str
    legal_status: LegalStatus
    risk_level: RiskLevel
    audience: tuple[str, ...] = ()
    """적용 대상. 근거가 확인된 것만 넣는다 (게이트 G4)."""

    effective_date: dt.date | None = None
    key_points: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    deadline: dt.date | None = None
    detail_url: str | None = None
    corrected: bool = False
    """정정본이면 상단에 표시한다 (§10.4)."""

    warnings: tuple[str, ...] = field(default_factory=tuple)


def _fmt_date(value: dt.date | None, *, missing: str) -> str:
    if value is None:
        return missing
    return f"{value.year}년 {value.month}월 {value.day}일"


def render_card(card: BriefingCard) -> str:
    """카드 한 건을 텔레그램 본문으로 렌더링한다."""
    lines: list[str] = []

    if card.corrected:
        lines.append("[정정] 이전에 안내드린 내용이 수정되었습니다.")
        lines.append("")

    lines.append(f"{RISK_PREFIX[card.risk_level]} {card.title}")
    lines.append("")

    if card.audience:
        lines.append(f"대상: {' · '.join(card.audience)}")

    status_line = f"상태: {STATUS_LABEL[card.legal_status]}"
    caveat = caveat_for(card.legal_status, card.effective_date)
    if caveat:
        status_line += f" ({caveat})"
    lines.append(status_line)

    # 시행일이 없으면 임의 날짜를 쓰지 않고 '확인 필요'로 표시한다 (§10.4).
    lines.append(f"시행일: {_fmt_date(card.effective_date, missing='확인 필요')}")

    if card.deadline is not None:
        lines.append(f"마감일: {_fmt_date(card.deadline, missing='-')}")

    if card.key_points:
        lines.append("")
        lines.append("핵심 내용")
        lines.extend(f"· {point}" for point in card.key_points)

    if card.actions:
        lines.append("")
        lines.append("사업자가 할 일")
        lines.extend(f"· {action}" for action in card.actions)

    if card.warnings:
        lines.append("")
        lines.append("주의")
        lines.extend(f"· {w}" for w in card.warnings)

    if card.detail_url:
        lines.append("")
        lines.append("상세 내용 및 공식 출처 보기")
        lines.append(card.detail_url)

    return "\n".join(lines)


def render_digest(
    cards: list[BriefingCard],
    *,
    today: dt.date,
    site_url: str | None = None,
    header: str = "오늘의 세무 브리핑",
    overflow: int = 0,
) -> str:
    """일일 브리핑 전체를 렌더링한다.

    중요도 순으로 정렬한다. 사업자는 위에서부터 읽다가 멈추므로,
    긴급 항목이 아래로 밀리면 안 된다.
    """
    order = {
        RiskLevel.CRITICAL: 0,
        RiskLevel.HIGH: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.LOW: 3,
    }
    ordered = sorted(cards, key=lambda c: (order[c.risk_level], c.title))

    lines = [f"{header} ({today.year}.{today.month:02d}.{today.day:02d})", ""]

    if not ordered:
        lines.append("오늘은 새로 확인된 공식 발표가 없습니다.")
    else:
        blocks = [render_card(card) for card in ordered]
        lines.append(("\n" + "─" * 20 + "\n").join(blocks))

    # 자리가 없어 뺀 것이 있으면 **몇 건인지 밝힌다.**
    # 조용히 자르면 사장님은 오늘 나온 게 이게 전부라고 믿는다.
    if overflow > 0:
        lines.append("")
        lines.append(f"이 밖에 {overflow}건이 더 있습니다. 사이트에서 확인하세요.")

    if site_url:
        lines.append("")
        lines.append(f"전체 보기: {site_url}")

    return "\n".join(lines)
