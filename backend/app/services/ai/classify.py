"""업종 분류와 검색 텍스트 생성.

분류는 **상담 참고용 색인**이지 적용 여부 판정이 아니다 (§1.3).
"이 개정이 요식업 사장님께 적용되는가"는 사실관계를 봐야 알 수 있고 그건
세무전문가의 일이다. 우리는 "요식업 상담할 때 이 건은 한 번 보시라"까지만 한다.

그래서 애매하면 **넓게** 잡는다. 놓쳐서 못 보는 것보다 낫다.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.domain.industry import GUIDE, Industry, normalize
from app.services.ai.groq_provider import GroqError, GroqProvider

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
당신은 한국 세무 개정 내용을 업종별로 분류하는 색인기다.

이 분류는 상담할 때 "이 건 한 번 보시라"고 짚어주기 위한 것이다.
적용 여부를 판정하는 게 아니다. 그건 세무전문가가 사실관계를 보고 판단한다.

따라서 **애매하면 넓게 잡는다.** 빠뜨려서 못 보는 것이 잘못 넣는 것보다 나쁘다.

판단 기준
- 사업 종류와 무관하게 모든 사업자에게 적용되면 ALL 하나만 쓴다.
  신고 절차, 가산세, 납부기한, 4대보험, 전자세금계산서 같은 것이다.
- 특정 업종에만 해당하면 그 업종만 쓴다. 최대 4개까지.
- 사업자와 무관한 개정(공무원 인사, 기관 내부 절차, 국가기관 간 업무분장)이면
  빈 배열로 둔다. 억지로 채우지 않는다.
- ALL 과 개별 업종을 같이 쓰지 않는다. 둘 중 하나다.

분류표에 있는 코드만 쓴다. 새 코드를 만들지 않는다.

JSON 객체 하나만 출력한다. 설명·코드펜스를 붙이지 않는다.
{"industries": ["코드", ...], "reason": "한 문장"}"""


def _taxonomy_block() -> str:
    return "\n".join(f"- {item.value}: {GUIDE[item]}" for item in Industry)


def _text_list(body: dict[str, Any], key: str, limit: int = 6) -> list[str]:
    """본문 배열을 문자열 목록으로. 근거가 붙은 항목은 `text` 안에 들어 있다."""
    values = body.get(key)
    if not isinstance(values, list):
        return []

    out: list[str] = []
    for item in values[:limit]:
        # 근거가 붙은 항목은 dict 안의 text 에, 아닌 것은 문자열 그대로 온다.
        text = (
            str(item.get("text") or "").strip()
            if isinstance(item, dict)
            else str(item).strip()
        )
        if text:
            out.append(text)
    return out


def build_search_text(title: str, one_line: str | None, body: dict[str, Any]) -> str:
    """검색 대상 텍스트를 한 덩어리로 합친다.

    제목·요약만 검색하면 "학원 4대보험" 같은 실무 질문이 안 걸린다.
    정작 답은 개정 내용과 사업자 할 일에 들어 있기 때문이다.
    """
    parts: list[str] = [title]
    if one_line:
        parts.append(one_line)
    for key in ("changes", "required_actions", "business_impact", "affected_users", "topics"):
        parts.extend(_text_list(body, key, limit=20))
    for item in body.get("deadlines") or []:
        if isinstance(item, dict) and item.get("label"):
            parts.append(str(item["label"]))

    # 중복 제거하되 순서는 유지한다. 같은 문구가 여러 번 들어가도 검색에는
    # 도움이 안 되고 컬럼만 커진다.
    seen: set[str] = set()
    unique = [p for p in parts if p and not (p in seen or seen.add(p))]
    return "\n".join(unique)


def classify_industries(
    title: str,
    one_line: str | None,
    body: dict[str, Any],
    *,
    provider: GroqProvider | None = None,
) -> tuple[list[str], str]:
    """업종 코드 목록과 판단 이유를 돌려준다.

    실패하면 빈 목록을 준다. **추측으로 채우지 않는다** — 틀린 업종 태그는
    "우리 업종 건 아니네" 하고 넘기게 만들어서, 아예 없는 것보다 나쁘다.
    """
    provider = provider or GroqProvider()

    lines = [
        "분류표",
        _taxonomy_block(),
        "",
        "분류할 내용",
        f"제목: {title}",
    ]
    if one_line:
        lines.append(f"요약: {one_line}")
    for label, key in (
        ("대상", "affected_users"),
        ("바뀌는 것", "changes"),
        ("사업자가 할 일", "required_actions"),
    ):
        values = _text_list(body, key)
        if values:
            lines.append(f"{label}:")
            lines.extend(f"  · {v}" for v in values)

    try:
        # 출력 자체는 두 줄짜리 JSON 이지만 추론형 모델은 답을 내기 전에
        # 토큰을 쓴다. 300 으로 잡았더니 JSON 이 중간에서 잘려
        # json_validate_failed 가 났다. 답 길이가 아니라 생각 길이에 맞춘다.
        payload = provider.complete_json(
            SYSTEM_PROMPT, "\n".join(lines), max_tokens=1200
        )
        data = json.loads(payload["content"])
    except (GroqError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("classify.failed", title=title[:60], error=str(exc)[:200])
        return [], ""

    return normalize(data.get("industries")), str(data.get("reason") or "").strip()[:300]
