"""세무 일정 — 신고·납부 마감일.

**실무자가 가장 자주 보는 것은 사실 달력이다.** 법령이 어떻게 바뀌었는지는
가끔 보지만, 이번 달에 뭘 신고해야 하는지는 매달 본다.

날짜는 법에 정해져 있다. 그래서 **AI 를 쓰지 않는다.** 모델에게 물어보면
그럴듯한 날짜를 지어낼 수 있고, 신고 기한을 하루 틀리면 가산세가 붙는다.
여기 적힌 것은 전부 법정 기한이고, 근거 조문을 같이 적어 둔다.

**개별 사업자의 기한은 다르다.**
과세유형(일반·간이·면세), 결산월, 반기납부 승인 여부, 성실신고확인대상
여부에 따라 갈린다. 그래서 이 달력은 "일반 일정" 이고, 화면도 그렇게
말한다. 누구에게 어느 것이 해당하는지까지 말하려면 사업자 정보가
있어야 하는데 우리에겐 없다 — 없는 것을 아는 척하지 않는다.

토·일요일이면 다음 월요일로 민다. **공휴일은 밀지 못한다** — 공휴일
목록이 없기 때문이다. 그래서 화면에 "공휴일이면 다음 영업일" 이라고
같이 적는다.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class Audience(StrEnum):
    """누구에게 해당하는가. 화면에서 걸러 보는 데 쓴다."""

    ALL = "ALL"
    """사업자면 대개 해당한다."""

    CORPORATE = "CORPORATE"
    """법인."""

    INDIVIDUAL = "INDIVIDUAL"
    """개인사업자."""

    EMPLOYER = "EMPLOYER"
    """직원을 둔 사업장."""

    TAX_FREE = "TAX_FREE"
    """면세사업자."""


LABEL: dict[Audience, str] = {
    Audience.ALL: "사업자 일반",
    Audience.CORPORATE: "법인",
    Audience.INDIVIDUAL: "개인사업자",
    Audience.EMPLOYER: "직원 있는 사업장",
    Audience.TAX_FREE: "면세사업자",
}


@dataclass(frozen=True)
class Deadline:
    """마감일 하나."""

    date: dt.date
    title: str
    note: str
    audience: Audience
    basis: str
    """근거 조문. **출처 없는 날짜는 싣지 않는다.**"""

    shifted: bool = False
    """주말이라 다음 월요일로 민 것인가."""


@dataclass(frozen=True)
class _Rule:
    month: int | None
    """None 이면 매달."""

    day: int
    """0 이면 그 달의 말일."""

    title: str
    note: str
    audience: Audience
    basis: str


#: 법정 기한.
#:
#: 확실한 것만 넣는다. 애매한 것을 넣어 두면 그 하나 때문에 나머지도
#: 못 믿게 된다 — 여기 있는 날짜는 전부 조문으로 확인되는 것이다.
RULES: tuple[_Rule, ...] = (
    _Rule(
        None, 10, "원천세 신고·납부",
        "전월에 지급한 급여·사업소득 등의 원천징수분입니다. 반기납부 승인을 받은 "
        "사업장은 1월 10일과 7월 10일 두 번만 냅니다.",
        Audience.EMPLOYER, "소득세법 제128조",
    ),
    _Rule(
        None, 10, "4대보험 신고·납부",
        "전월 보수 기준입니다. 원천세와 같은 날이라 함께 처리하는 경우가 많습니다.",
        Audience.EMPLOYER, "국민연금법 제88조 등",
    ),
    _Rule(
        1, 25, "부가가치세 2기 확정신고",
        "직전 해 7월~12월분입니다. 간이과세자는 한 해치를 이때 한 번에 신고합니다.",
        Audience.ALL, "부가가치세법 제49조",
    ),
    _Rule(
        2, 10, "면세사업자 사업장현황신고",
        "직전 해 수입금액과 사업장 현황을 신고합니다. 학원·병의원 등이 해당합니다.",
        Audience.TAX_FREE, "소득세법 제78조",
    ),
    _Rule(
        3, 10, "지급명세서 제출 · 연말정산 원천세",
        "직전 해 근로·퇴직소득 지급명세서를 냅니다. 연말정산분 원천세도 이때 냅니다.",
        Audience.EMPLOYER, "소득세법 제164조",
    ),
    _Rule(
        3, 31, "법인세 신고·납부",
        "12월 결산법인 기준입니다. 결산월이 다르면 사업연도 종료 후 3개월 이내입니다.",
        Audience.CORPORATE, "법인세법 제60조",
    ),
    _Rule(
        4, 25, "부가가치세 1기 예정신고",
        "법인은 신고합니다. 개인 일반과세자는 대개 고지서로 납부만 합니다.",
        Audience.CORPORATE, "부가가치세법 제48조",
    ),
    _Rule(
        5, 31, "종합소득세 신고·납부",
        "직전 해 소득분입니다. 성실신고확인대상 사업자는 6월 30일까지입니다.",
        Audience.INDIVIDUAL, "소득세법 제70조",
    ),
    _Rule(
        6, 30, "성실신고확인대상자 종합소득세",
        "수입금액이 기준을 넘는 개인사업자입니다. 확인서를 함께 냅니다.",
        Audience.INDIVIDUAL, "소득세법 제70조의2",
    ),
    _Rule(
        7, 25, "부가가치세 1기 확정신고",
        "1월~6월분입니다. 개인 일반과세자도 이때는 신고합니다.",
        Audience.ALL, "부가가치세법 제49조",
    ),
    _Rule(
        8, 31, "법인세 중간예납",
        "12월 결산법인 기준입니다. 직전 사업연도 세액의 절반을 내거나 가결산합니다.",
        Audience.CORPORATE, "법인세법 제63조",
    ),
    _Rule(
        10, 25, "부가가치세 2기 예정신고",
        "법인은 신고합니다. 개인 일반과세자는 대개 고지서로 납부만 합니다.",
        Audience.CORPORATE, "부가가치세법 제48조",
    ),
    _Rule(
        11, 30, "종합소득세 중간예납",
        "고지서로 납부합니다. 직전 해 세액의 절반이며, 실적이 크게 줄었으면 "
        "추계액으로 신고할 수 있습니다.",
        Audience.INDIVIDUAL, "소득세법 제65조",
    ),
)


def _shift_off_weekend(date: dt.date) -> tuple[dt.date, bool]:
    """토·일이면 다음 월요일로 민다.

    **공휴일은 밀지 못한다.** 공휴일 목록이 없기 때문이다. 아는 만큼만
    미루고, 나머지는 화면에서 "공휴일이면 다음 영업일" 이라고 말한다.
    지어낸 날짜를 주는 것보다 낫다.
    """
    if date.weekday() == 5:  # 토
        return date + dt.timedelta(days=2), True
    if date.weekday() == 6:  # 일
        return date + dt.timedelta(days=1), True
    return date, False


def _resolve(rule: _Rule, year: int, month: int) -> dt.date:
    day = rule.day or calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def upcoming(today: dt.date, *, within_days: int = 90) -> list[Deadline]:
    """오늘부터 `within_days` 안에 오는 마감일.

    오늘도 포함한다 — 마감일 당일 아침에 화면을 여는 사람이 있고,
    그 사람에게 가장 필요한 정보다.
    """
    horizon = today + dt.timedelta(days=within_days)
    found: list[Deadline] = []

    # 넉넉히 훑는다. 1년을 넘겨 보는 일은 없다고 보고 14개월만 본다.
    year, month = today.year, today.month
    for _ in range(14):
        for rule in RULES:
            if rule.month is not None and rule.month != month:
                continue
            date, shifted = _shift_off_weekend(_resolve(rule, year, month))
            if today <= date <= horizon:
                found.append(
                    Deadline(
                        date=date,
                        title=rule.title,
                        note=rule.note,
                        audience=rule.audience,
                        basis=rule.basis,
                        shifted=shifted,
                    )
                )
        month += 1
        if month > 12:
            month = 1
            year += 1

    return sorted(found, key=lambda d: (d.date, d.title))


__all__ = ["LABEL", "RULES", "Audience", "Deadline", "upcoming"]
