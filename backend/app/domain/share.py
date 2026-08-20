"""사장님에게 보낼 짧은 글 만들기.

세무사무소 직원이 우리 화면을 보고 고객에게 카톡으로 옮겨 적는다.
그 옮겨 적는 일을 대신한다.

**새로 쓰지 않는다. 있는 것만 고른다.**

여기서 모델을 한 번 더 돌려 "쉬운 말로 바꿔" 라고 시키면, 검수를 통과한
문장이 검수를 안 거친 문장으로 바뀐다. 그렇게 만든 글이 고객에게 그대로
간다 — 우리 화면보다 더 멀리 간다. 지어낼 자리를 만들지 않는다.

그래서 하는 일은 **고르고 자르는 것**뿐이다.

    한 줄 요약     → 첫 문장만
    할 일          → 첫 개                (없으면 줄 자체를 안 쓴다)
    대상           → 앞 두 개              (없으면 안 쓴다)
    시행일·마감    → 콘텐츠 필드 그대로
    원문 링크      → 반드시

**모르면 줄을 안 쓴다.** 빈 칸을 "확인 필요" 로 채우면 받는 사람은 뭘
확인하라는 건지 모른 채 불안해진다.

**길이.** 카톡에서 접히지 않는 선이 대략 열 줄이다. 그 안에 들어가게
자르되, 자른 것은 원문 링크가 받는다.
"""

from __future__ import annotations

import datetime as dt
import re

#: 한 줄 요약에서 첫 문장만 쓴다.
#:
#: 요약은 250자까지 쓸 수 있고 실제로 이렇게 길다.
#:
#:     재생에너지전기저장판매사업자·송전제약발생지역전기공급사업자·
#:     분산에너지사업자를 부대비용 세금계산서 발급 대상에 추가하고,
#:     현금매출명세서에 미디어콘텐츠창작업 항목을 신설하며, …
#:
#: 실무자에게는 이게 맞다. 사장님에게는 아니다.
_SENTENCE_END = re.compile(r"(?<=[.。])\s+|(?<=니다)\s+")

#: 이 길이를 넘으면 뒤를 자른다. 카톡 한 줄이 대략 이 정도다.
MAX_LEAD = 110

DISCLAIMER = "※ 일반 안내입니다. 우리 사업장에 어떻게 적용되는지는 담당자에게 확인하세요."


def _first_sentence(text: str) -> str:
    """첫 문장. 그것마저 길면 쉼표에서 한 번 더 끊는다."""
    lead = _SENTENCE_END.split(text.strip(), maxsplit=1)[0].strip()
    if len(lead) <= MAX_LEAD:
        return lead
    # 쉼표 앞까지가 한 덩어리다. 그 경계를 무시하고 글자 수로 자르면
    # "…추가하고, 현금매출명세서에 미디" 처럼 말이 끊긴다.
    cut = lead.rfind(",", 0, MAX_LEAD)
    if cut < MAX_LEAD // 2:
        cut = MAX_LEAD
    return lead[:cut].rstrip(" ,") + " …"


def _texts(items: object) -> list[str]:
    """`[{text, locator}]` 또는 `["문자열"]` 에서 글만 뽑는다."""
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        raw = item.get("text") if isinstance(item, dict) else item
        value = str(raw or "").strip()
        if value:
            out.append(value)
    return out


#: 대상 한 개의 길이 한도.
#:
#: affected_users 에는 사람이 아닌 것이 섞인다. 실제로 이렇게 나왔다.
#:
#:     대상: 체납자, 민사집행법 제246조의2에 따른 생계비계좌에 예치된 예금 등
#:
#: 뒤엣것은 대상이 아니라 압류가 금지되는 재산이다. 모델 잘못이라기보다
#: 원문이 그렇게 적혀 있어서인데, 어느 쪽이든 사장님이 "나야?" 를 판단하는
#: 데는 방해만 된다. 길면 설명이지 대상이 아니라고 보고 뺀다.
MAX_TARGET = 25


def _date(value: dt.date | None) -> str | None:
    return f"{value.year}년 {value.month}월 {value.day}일" if value else None


def build_share_text(
    *,
    title: str,
    summary: str | None,
    body: dict | None,
    effective_date: dt.date | None = None,
    comment_deadline: dt.date | None = None,
    preannounced: bool = False,
    source_url: str | None = None,
    with_disclaimer: bool = True,
) -> str:
    """카톡에 그대로 붙여 넣을 글.

    줄 순서는 사장님이 궁금해하는 순서다.

        무엇이 바뀌나 → 나도 해당되나 → 언제부터 → 뭘 해야 하나
    """
    body = body if isinstance(body, dict) else {}
    lines: list[str] = [title.strip()]

    lead = _first_sentence(summary or "")
    if preannounced:
        # 예고는 "바뀐다" 가 아니라 "바꾸겠다고 한다" 다. 요약에 든
        # 마감 문장을 그대로 쓰면 무엇에 관한 예고인지가 빠진다.
        lead = "아직 확정된 개정이 아닙니다. 정부가 의견을 받는 중입니다."
    if lead:
        lines += ["", lead]

    facts: list[str] = []
    targets = [t for t in _texts(body.get("affected_users")) if len(t) <= MAX_TARGET][:2]
    if targets:
        facts.append(f"· 대상: {', '.join(targets)}")
    if preannounced:
        when = _date(comment_deadline)
        if when:
            facts.append(f"· 의견 마감: {when}")
    else:
        when = _date(effective_date)
        if when:
            facts.append(f"· 시행: {when}")
        todo = _texts(body.get("required_actions"))
        if todo:
            facts.append(f"· 할 일: {_first_sentence(todo[0])}")
    if facts:
        lines += ["", *facts]

    if source_url:
        lines += ["", f"원문 {source_url}"]
    # 여러 건을 묶어 보낼 때는 맨 끝에 한 번만 붙인다. 건마다 반복하면
    # 세 건짜리 메시지에 같은 문장이 세 번 나오고, 그러면 아무도 안 읽는다.
    if with_disclaimer:
        lines += ["", DISCLAIMER]

    return "\n".join(lines)





#: 제목 끝의 개정 구분. 「고용보험법 (일부개정, 2026-09-18 시행예정)」.
#:
#: 실무자 화면에서는 이게 정보다 — 같은 법의 개정이 여럿이라 구분이 된다.
#: 사장님한테 보내는 글에서는 아니다. 바로 뒤에 「2026년 9월 18일 시행」 을
#: 다시 적으므로 같은 날짜가 두 번 나오고, 괄호 안이 길어서 줄이 넘어간다.
_REVISION_SUFFIX = re.compile(
    r"\s*\((?:전부개정|일부개정|타법개정|제정|폐지)[^)]*\)\s*$"
)


def _law_name(title: str) -> str:
    return _REVISION_SUFFIX.sub("", title).strip()


def _dday(days: int) -> str:
    """D-day. 오늘이면 「오늘」, 지난 것은 애초에 넣지 않는다."""
    if days == 0:
        return "오늘"
    if days == 1:
        return "내일"
    return f"{days}일 뒤"


def build_deadline_text(
    *,
    today: dt.date,
    deadlines: list[dict],
    changes: list[dict] | None = None,
    audience_label: str | None = None,
) -> str:
    """카톡으로 돌릴 「챙기실 것」 한 장.

    **업종별로 못 만든다. 아직은.**

    사장님 대부분이 음식점이라 요식업만 골라 보내면 좋겠는데, 콘텐츠
    325건 중 278건이 업종 미분류다. 「요식·음식점」 으로 잡힌 것은 0건이다.
    골라낼 것이 없는데 골라낸 척하면 빈 안내가 나간다.

    그래서 업종이 아니라 **마감 일정**으로 만든다. 이건 음식점이든
    학원이든 똑같이 걸리고, 날짜가 법에 정해져 있어 지어낼 여지가 없다.
    사장님이 실제로 물어보는 것도 "언제까지 뭘 내야 하나" 다.

    대상(개인사업자·법인·직원 있는 사업장)은 항목마다 적는다. 거르지
    않는다 — 「나는 법인이 아니니까 이건 아니구나」 를 사장님이 직접
    확인하는 편이, 우리가 잘못 걸러서 하나를 빠뜨리는 것보다 낫다.
    """
    lines = [f"[사장님 안내] {today.month}월 챙기실 것"]
    if audience_label:
        lines.append(f"({audience_label} 기준)")

    if deadlines:
        lines += ["", "■ 신고·납부 마감"]
        for item in deadlines:
            date = dt.date.fromisoformat(str(item["date"]))
            left = (date - today).days
            head = f"· {date.month}월 {date.day}일 ({_dday(left)}) {item['title']}"
            lines.append(head)
            who = str(item.get("audience_label") or "").strip()
            if who:
                lines.append(f"    대상: {who}")

    if changes:
        lines += ["", "■ 새로 정해진 것"]
    for change in changes or []:
        title = str(change.get("title") or "").strip()
        when = change.get("effective_date")
        if not title:
            continue
        line = f"· {_law_name(title)}"
        if when:
            date = dt.date.fromisoformat(str(when))
            line += f" — {date.year}년 {date.month}월 {date.day}일 시행"
        lines.append(line)

    if len(lines) <= 2:
        return ""

    lines += [
        "",
        "※ 일반적인 일정입니다. 과세유형·결산월·반기납부 여부에 따라 "
        "달라질 수 있으니 담당자에게 확인하세요.",
    ]
    return "\n".join(lines)


__all__ = [
    "DISCLAIMER",
    "MAX_LEAD",
    "MAX_TARGET",
    "build_deadline_text",
    "build_share_text",
]
