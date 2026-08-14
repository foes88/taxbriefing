"""GROQ 기반 AI 분석 제공자 (§6.1 '공급자 교체 가능한 구조').

**설계상 중요한 결정 하나.**

계약 스키마의 evidence 는 `source_version_id` 로 UUID 를 요구한다. 그런데 LLM 에게
UUID 를 그대로 받아 적게 하면 한 글자씩 틀리는 일이 잦고, 그러면 V5 검증에서
"지어낸 출처"로 반려된다 — 모델이 거짓말한 게 아닌데 거짓말로 처리된다.

그래서 역할을 나눈다.
  - 모델: 원문 어디를 근거로 삼았는지 **locator** 로 말한다 ("제개정이유 2문단")
  - 코드: 그 locator 에 실제 원문 버전 UUID 를 붙인다

모델이 하지 않아도 되는 일(UUID 복사)을 시키지 않으면서, 근거의 실질(원문 어느 부분인가)은
그대로 남는다. 검증 V1~V7 은 조립된 결과에 평소대로 적용된다.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ai.contract import SCHEMA_VERSION
from app.services.ai.provider import AnalysisRequest, AnalysisResponse

logger = get_logger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

#: 원문이 길면 앞부분만 보낸다. 법령 정규화 본문은 서지정보 → 제개정이유 → 개정문 →
#: 변경 조문 순이라, 앞쪽이 판단에 가장 중요하다.
#: 무료 티어는 1회 요청 크기와 분당 토큰이 모두 제한되므로 보수적으로 잡는다.
MAX_DOC_CHARS = 6_000

#: 출력 예산.
#:
#: 추론형 모델은 답을 내기 전에 토큰을 쓴다. 300 으로 잡았을 때는 JSON 이
#: 중간에서 잘렸고, 2,400 으로도 조세특례제한법처럼 항목이 많은 건은
#: 닫는 괄호에 닿기 전에 끝났다. 모자라면 두 배씩 올려 다시 부른다.
MAX_OUTPUT_TOKENS = 2_400
MAX_OUTPUT_TOKENS_CEILING = 9_600

#: 429(분당 한도)는 기다리면 풀린다. 413(요청 과대)은 줄여야 풀린다.
MAX_RETRIES = 4
BACKOFF_SECONDS = (5, 12, 25, 45)

SYSTEM_PROMPT = """\
당신은 한국 세무·정책 원문을 사업자용 정보로 옮기는 추출기다. 해석자나 조언자가 아니다.
당신의 출력은 초안이며, 세무전문가가 원문과 대조해 검수한 뒤에야 사업자에게 전달된다.
따라서 확신이 없으면 비워두는 것이 정답이다. 빈 값은 검수자가 채우지만,
틀린 값은 검수자가 못 보고 지나칠 수 있다.

절대 규칙
1. 원문에 없는 것을 만들지 않는다. 날짜·숫자·금액·비율·기관명·적용대상·예외조항은
   원문에서 문자 그대로 확인되지 않으면 null 또는 빈 배열이다.
2. 추론을 사실로 적지 않는다. "보통 이런 개정은 다음 해 시행"은 추론이다.
3. 세액을 계산하지 않는다. 원문에 적힌 세율·기준금액을 옮기는 것만 허용된다.
4. 정책 단계를 확정하지 않는다. legal_status 는 후보 제안이며, 원문이 공포·시행을
   명시하지 않으면 UNKNOWN 이다.
5. HTML·마크다운을 쓰지 않는다. 순수 텍스트만 쓴다.
6. 사업자가 읽을 문장으로 쓴다. 행정 용어를 풀어 쓰되 사실을 바꾸지 않는다.

무엇을 적고 무엇을 빼는가
- changes 에는 **사업자에게 실질적으로 달라지는 것**만 적는다.
  자구 정리, 인용 조문 번호 변경, 용어 통일, 다른 법 개정에 따른 형식적 반영처럼
  실제 의무·금액·기한·대상이 바뀌지 않는 항목은 넣지 않는다.
  예: "'이 항에서'를 '이 조에서'로 수정" → 넣지 않는다.
  예: "생계비계좌 예금은 압류할 수 없도록 명시" → 넣는다.
- 조문 번호를 나열하지 말고 **무엇이 어떻게 달라지는지**를 쓴다.
  조문 번호는 근거가 필요할 때 locator 에 적는다.
- 실질 변경이 하나도 없으면 changes 를 빈 배열로 두고,
  one_line_summary 에 그 사실을 적는다.
  예: "다른 법 개정에 맞춰 서식만 바뀌었고 사업자가 할 일은 없습니다."

JSON 객체 하나만 출력한다. 설명·인사·코드펜스를 붙이지 않는다."""

# 프롬프트 문자열은 줄 길이 검사 대상이 아니다 — 모델이 읽는 형식이 우선이다.
# ruff: noqa: E501
OUTPUT_SPEC = """\
출력 형식:
{
  "title": "사업자용 제목 (120자 이내)",
  "one_line_summary": "무엇이 어떻게 달라지는지 한 문장 (250자 이내)",
  "legal_status": "DISCUSSION|BILL_PROPOSED|PREANNOUNCED|GOV_ANNOUNCED|ASSEMBLY_PASSED|PROMULGATED|EFFECTIVE|SUSPENDED|ABOLISHED|UNKNOWN",
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "affected_users": ["적용 대상. 원문 표현대로. 없으면 빈 배열"],
  "excluded_users": ["제외 대상. 원문에 제외 규정이 있을 때만"],
  "changes": [{"text": "기존 대비 달라지는 점", "locator": "근거 위치"}],
  "business_impact": [{"text": "세금·비용·신고·노무 영향", "locator": "근거 위치"}],
  "required_actions": [{"text": "사업자가 할 일", "urgency": "NOW|BEFORE_DEADLINE|MONITOR|ASK_EXPERT", "locator": "근거 위치"}],
  "topics": ["세목·분야. 예: 부가가치세, 법인세, 성실신고확인"],
  "warnings": [{"code": "MISSING_EVIDENCE|AMBIGUOUS_SCOPE|NEEDS_EXPERT|SOURCE_CONFLICT", "message": "설명", "related_fields": ["필드명"]}]
}

locator 는 원문의 어느 부분인지 짧게 적는다. 예: "제개정이유 1문단", "개정문", "제12조".
risk_level 은 "이 정보가 틀렸을 때 사업자가 얼마나 손해를 보는가"로 정한다.
신고의무·가산세·기한 관련은 HIGH 이상, 절차·서식 변경은 MEDIUM, 해설·동향은 LOW.
날짜는 출력하지 않는다 — 날짜는 시스템이 원문 필드에서 직접 가져온다."""


class GroqError(Exception):
    """GROQ 호출 실패."""


class GroqRateLimited(GroqError):
    """분당 토큰 한도. 기다리면 풀린다."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("GROQ 분당 한도를 초과했습니다.")
        self.retry_after = retry_after


class GroqDailyExhausted(GroqError):
    """하루치 토큰을 다 썼다. **기다려도 오늘은 안 풀린다.**

    429 를 전부 분당 한도로 다뤘던 탓에 크게 헤맸다. 화면에는 이렇게 떴다.

        ! 법인세법 (일부개정): GROQ 분당 한도를 계속 초과합니다.

    그래서 호출이 너무 큰 줄 알고 원문을 자르는 쪽을 팠다. 실제 응답
    본문은 다른 말을 하고 있었다.

        on tokens per day (TPD): Limit 200000, Used 199862

    분당이 아니라 **하루치**였다. 90초씩 세 번 기다린 뒤 실패하기를
    아홉 번 반복했으니 40분을 아무 소득 없이 버린 셈이다.

    한도의 종류가 다르면 대응도 다르다. 분당은 기다리고, 하루치는
    멈춘다. 같은 429 라고 같이 다루면 안 된다.
    """

    def __init__(self, used: int | None = None, limit: int | None = None) -> None:
        detail = f" ({used:,}/{limit:,} 토큰)" if used and limit else ""
        super().__init__(
            f"GROQ 하루치 토큰을 다 썼습니다{detail}. "
            "기다려도 오늘은 풀리지 않습니다 — 내일 이어서 돌리세요."
        )
        self.used = used
        self.limit = limit


class GroqUnfinishedJson(GroqError):
    """JSON 을 닫기 전에 출력 토큰이 떨어졌다.

    `response_format: json_object` 로 부르면 모델이 JSON 을 완성하지
    못했을 때 GROQ 가 400 을 준다.

        Failed to validate JSON. Please adjust your prompt.

    문구만 보면 프롬프트가 잘못된 것 같지만 아니다. 조세특례제한법처럼
    개정 항목이 많은 건에서만 났고, 짧은 건은 같은 프롬프트로 잘 됐다.
    추론형 모델이라 답을 내기 전에 토큰을 쓰고, 그러고 나서 목록이
    길어지면 닫는 괄호에 닿기 전에 예산이 끝난다.

    **기다려도 안 되고 원문을 줄여도 안 된다.** 출력 예산을 늘려야 한다.

    문구가 하나가 아니다. `validate` 로만 걸렀더니 소득세법 시행령이
    이렇게 떨어졌다.

        GroqError: GROQ HTTP 400: {"error":{"message":"Failed to
        generate JSON. Please adjust your prompt. See 'failed_g

    `generate` 와 `validate` 두 가지를 쓴다. 한쪽만 알아보면 나머지는
    예산을 늘리는 사다리를 타지 못하고 원본 응답이 그대로 화면에 뜬다.
    """

    def __init__(self) -> None:
        super().__init__("모델이 JSON 을 끝내기 전에 출력 예산이 떨어졌습니다.")


class GroqTooLarge(GroqError):
    """1회 요청이 너무 크다. 기다려도 소용없고 줄여야 한다."""

    def __init__(self) -> None:
        super().__init__("요청이 모델 한도보다 큽니다.")


#: 하루치 한도를 알리는 429 본문.
#:
#:     on tokens per day (TPD): Limit 200000, Used 199862, Requested 1234
_TPD = re.compile(
    r"tokens per day \(TPD\).*?Limit\s+(\d+).*?Used\s+(\d+)", re.I | re.S
)

#: JSON 을 못 끝냈다는 400 본문.
#:
#: GROQ 는 `generate` 와 `validate` 두 문구를 쓰고, 어느 쪽이든 응답에
#: `failed_generation` 필드를 붙인다. 셋 다 본다 — 문구 하나에 매달면
#: 다음에 표현이 바뀔 때 또 원본 응답이 그대로 화면에 뜬다.
_UNFINISHED = re.compile(
    r"Failed to (generate|validate) JSON|failed_generation", re.I
)


def _daily_exhausted(response: httpx.Response) -> GroqDailyExhausted | None:
    """하루치를 다 쓴 429 인가.

    분당 한도는 기다리면 풀리지만 이건 안 풀린다. 구분하지 않으면
    되지도 않을 재시도에 한 건당 4분 30초를 버린다.
    """
    match = _TPD.search(response.text)
    if not match:
        return None
    return GroqDailyExhausted(used=int(match.group(2)), limit=int(match.group(1)))


def _give_up(seen: dict[str, int]) -> str:
    """재시도를 다 쓴 이유를 **일어난 대로** 적는다.

    한 종류만 났으면 그것을 말하고, 섞였으면 섞였다고 말한다. 어느 쪽이
    많았는지가 다음에 어디를 볼지 정하기 때문이다.
    """
    if not seen:
        return f"GROQ 호출을 {MAX_RETRIES}번 시도했으나 끝내지 못했습니다."
    tally = " · ".join(f"{name} {count}회" for name, count in seen.items())
    if len(seen) == 1:
        return f"GROQ {tally}로 {MAX_RETRIES}번 시도가 모두 실패했습니다."
    return (
        f"GROQ 재시도 {MAX_RETRIES}번을 다 썼습니다 ({tally}). "
        "한 가지 원인이 아니므로 한도만 보지 말고 기록을 확인하세요."
    )


def _retry_after(response: httpx.Response) -> float | None:
    """서버가 알려주는 대기 시간을 그대로 따른다. 임의로 짐작하지 않는다."""
    raw = response.headers.get("retry-after")
    if raw:
        try:
            return min(float(raw), 90.0)
        except ValueError:
            pass
    # GROQ 는 본문에 "try again in 8.5s" 형태로 알려주기도 한다.
    match = re.search(r"try again in ([\d.]+)s", response.text, re.I)
    if match:
        try:
            return min(float(match.group(1)) + 1.0, 90.0)
        except ValueError:
            pass
    return None


class GroqProvider:
    """GROQ Chat Completions 기반 제공자."""

    name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        timeout: float = 90.0,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.ai_api_key
        self.model_name = model or settings.ai_model
        self._timeout = timeout
        self._client = client

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        if not self.api_key:
            raise GroqError(
                "TAXBRIEFING_AI_API_KEY 가 설정되지 않았습니다. GROQ API 키를 넣으세요."
            )

        started = time.perf_counter()
        payload = self._call_with_retry(request)
        latency = int((time.perf_counter() - started) * 1000)

        raw = self._assemble(payload["content"], request)
        return AnalysisResponse(
            raw_output=raw,
            model_provider=self.name,
            model_name=self.model_name,
            latency_ms=latency,
            token_usage=payload["usage"],
            cost_amount=0.0,  # 무료 티어
        )

    # ---------------------------------------------------------------- 내부

    def _call_with_retry(self, request: AnalysisRequest) -> dict[str, Any]:
        """무료 티어의 두 가지 한계를 각각 다르게 다룬다.

        429 는 분당 토큰 한도라 **기다리면** 풀린다. 서버가 Retry-After 를 주면 그 값을 따른다.
        413 은 요청 자체가 커서 나므로 기다려도 소용없다 — **원문을 줄여서** 다시 보낸다.

        세 가지가 재시도 횟수를 함께 쓴다. 그래서 마지막 시도에서 무엇이
        났는지만 보고 실패 사유를 적으면 거짓이 된다. 실제로 이렇게 떴다.

            ! 소득세법 시행령: GROQ 분당 한도를 계속 초과합니다.

        기록을 보면 분당 한도는 네 번 중 두 번이었고, 나머지 두 번은 JSON
        미완성과 요청 과대였다. "계속 초과" 가 아니다. 어느 쪽을 파야 하는지
        말해 주지 않는 메시지는 없느니만 못하다 — 지난번에도 같은 문장 하나로
        하루를 엉뚱한 데 썼다. **일어난 것을 세어서 그대로 적는다.**
        """
        budget = MAX_DOC_CHARS
        # 출력 예산. JSON 을 못 닫으면 늘려서 다시 부른다.
        out_budget = MAX_OUTPUT_TOKENS
        seen: dict[str, int] = {}

        for attempt in range(MAX_RETRIES):
            try:
                return self._call(
                    self._build_messages(request, budget), max_tokens=out_budget
                )
            except GroqUnfinishedJson as exc:
                seen["JSON 미완성"] = seen.get("JSON 미완성", 0) + 1
                if out_budget >= MAX_OUTPUT_TOKENS_CEILING:
                    raise GroqError(
                        "출력 예산을 최대로 올려도 모델이 JSON 을 끝내지 못합니다. "
                        "개정 항목이 지나치게 많은 건일 수 있습니다."
                    ) from exc
                out_budget = min(out_budget * 2, MAX_OUTPUT_TOKENS_CEILING)
                logger.info("groq.grow_output", new_budget=out_budget)
            except GroqRateLimited as exc:
                seen["분당 한도"] = seen.get("분당 한도", 0) + 1
                if attempt == MAX_RETRIES - 1:
                    raise GroqError(_give_up(seen)) from exc
                wait = exc.retry_after or BACKOFF_SECONDS[attempt]
                logger.info("groq.rate_limited", wait_seconds=wait, attempt=attempt + 1)
                time.sleep(wait)
            except GroqTooLarge as exc:
                seen["요청 과대"] = seen.get("요청 과대", 0) + 1
                if budget <= 1500:
                    raise GroqError(
                        "원문을 최소 크기까지 줄여도 요청이 너무 큽니다."
                    ) from exc
                budget = budget // 2
                logger.info("groq.shrink_input", new_budget=budget)

        raise GroqError(_give_up(seen))

    def _build_messages(
        self, request: AnalysisRequest, budget: int = MAX_DOC_CHARS
    ) -> list[dict[str, str]]:
        parts: list[str] = [
            f"기준일: {request.reference_date.isoformat()}",
            "",
            "아래는 공식 원문이다. 여기 적힌 것만 근거로 삼는다.",
            "",
        ]
        # 원문이 여러 개면 예산을 나눠 쓴다.
        per_doc = max(1000, budget // max(1, len(request.documents)))
        for index, doc in enumerate(request.documents, start=1):
            body = doc.normalized_text[:per_doc]
            truncated = len(doc.normalized_text) > per_doc
            parts += [
                f"--- 원문 {index} ---",
                f"출처 등급: {doc.authority} ({'공식' if doc.authority in 'AB' else '참고'})",
                f"발표기관: {doc.publisher}",
                f"제목: {doc.title}",
                "본문:",
                body + ("\n…(이하 생략)" if truncated else ""),
                "",
            ]
        parts.append(OUTPUT_SPEC)

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)},
        ]

    def complete_json(
        self, system: str, user: str, *, max_tokens: int = 2400
    ) -> dict[str, Any]:
        """JSON 응답을 받는 단발 호출. 429 만 재시도한다.

        분석(analyze)이 아닌 짧은 보조 작업 — 분류·태깅 같은 것 — 이 쓴다.
        입력이 짧아 413 이 날 일이 없으므로 축소 로직은 없다.
        """
        if not self.api_key:
            raise GroqError("TAXBRIEFING_AI_API_KEY 가 설정되지 않았습니다.")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        seen: dict[str, int] = {}
        for attempt in range(MAX_RETRIES):
            try:
                return self._call(messages, max_tokens=max_tokens)
            except GroqRateLimited as exc:
                seen["분당 한도"] = seen.get("분당 한도", 0) + 1
                if attempt == MAX_RETRIES - 1:
                    raise GroqError(_give_up(seen)) from exc
                wait = exc.retry_after or BACKOFF_SECONDS[attempt]
                logger.info("groq.rate_limited", wait_seconds=wait, attempt=attempt + 1)
                time.sleep(wait)
        raise GroqError(_give_up(seen))

    def _call(
        self, messages: list[dict[str, str]], *, max_tokens: int = 2400
    ) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": messages,
                    # 같은 원문에 같은 답이 나와야 재현성이 성립한다 (§9.5).
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.HTTPError as exc:
            raise GroqError(f"GROQ 호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code == 429:
            # 429 는 두 가지다. 본문이 어느 쪽인지 말해 준다.
            daily = _daily_exhausted(response)
            if daily is not None:
                raise daily
            raise GroqRateLimited(_retry_after(response))
        if response.status_code == 413:
            raise GroqTooLarge()
        if response.status_code == 400 and _UNFINISHED.search(response.text):
            raise GroqUnfinishedJson()
        if response.status_code >= 400:
            raise GroqError(f"GROQ HTTP {response.status_code}: {response.text[:300]}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise GroqError(f"GROQ 응답 형식이 예상과 다릅니다: {str(data)[:300]}") from exc

        return {"content": content, "usage": data.get("usage", {})}

    def _assemble(self, content: str, request: AnalysisRequest) -> dict[str, Any]:
        """모델 출력에 원문 UUID 를 붙여 계약 스키마 형태로 조립한다."""
        try:
            model_out = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GroqError(f"모델이 JSON 을 반환하지 않았습니다: {content[:300]}") from exc

        primary = request.documents[0].source_version_id if request.documents else ""

        evidence: list[dict[str, Any]] = []
        counter = {"n": 0}

        def cite(locator: str | None) -> list[str]:
            """근거 항목을 만들고 그 id 를 돌려준다."""
            counter["n"] += 1
            eid = f"ev{counter['n']}"
            evidence.append(
                {
                    "id": eid,
                    "source_version_id": primary,
                    # locator 규약은 프롬프트 문서(analysis_v1.md)와 맞춘다.
                    "locator": f"field:changes#{locator or '원문'}",
                    "support_type": "DIRECT",
                    "note": None,
                }
            )
            return [eid]

        def grounded(items: Any, extra: str | None = None) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                text = _text(item.get("text"))
                if not text:
                    continue
                entry: dict[str, Any] = {
                    "text": text,
                    "evidence_ids": cite(item.get("locator")),
                }
                if extra == "urgency":
                    urgency = _text(item.get("urgency")) or "MONITOR"
                    entry["urgency"] = (
                        urgency
                        if urgency in ("NOW", "BEFORE_DEADLINE", "MONITOR", "ASK_EXPERT")
                        else "MONITOR"
                    )
                out.append(entry)
            return out[:20]

        def strings(value: Any, limit: int = 30) -> list[str]:
            if not isinstance(value, list):
                return []
            return [t for t in (_text(v) for v in value) if t][:limit]

        changes = grounded(model_out.get("changes"))
        impact = grounded(model_out.get("business_impact"))
        actions = grounded(model_out.get("required_actions"), extra="urgency")

        if not evidence:
            # 근거가 하나도 없으면 스키마상 evidence 는 최소 1개여야 한다.
            # 제목이 원문 제목에서 왔다는 사실 자체가 근거다.
            cite("제목")

        warnings = [
            {
                "code": _text(w.get("code")) or "NEEDS_EXPERT",
                "message": _text(w.get("message"))[:500],
                "related_fields": strings(w.get("related_fields"), 10),
            }
            for w in (model_out.get("warnings") or [])
            if isinstance(w, dict) and _text(w.get("message"))
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "title": _text(model_out.get("title"))[:120] or "제목 없음",
            "one_line_summary": _text(model_out.get("one_line_summary"))[:250]
            or "요약이 생성되지 않았습니다.",
            "legal_status": _enum(
                model_out.get("legal_status"),
                (
                    "DISCUSSION",
                    "BILL_PROPOSED",
                    "PREANNOUNCED",
                    "GOV_ANNOUNCED",
                    "ASSEMBLY_PASSED",
                    "PROMULGATED",
                    "EFFECTIVE",
                    "SUSPENDED",
                    "ABOLISHED",
                    "UNKNOWN",
                ),
                "UNKNOWN",
            ),
            # 날짜는 모델에게 받지 않는다. 수집 어댑터가 API 필드에서 가져온 값을 쓴다.
            "announcement_date": None,
            "promulgation_date": None,
            "effective_date": None,
            "application_period": None,
            "affected_users": strings(model_out.get("affected_users")),
            "excluded_users": strings(model_out.get("excluded_users")),
            "changes": changes,
            "business_impact": impact,
            "required_actions": actions,
            "deadlines": [],
            "risk_level": _enum(
                model_out.get("risk_level"), ("LOW", "MEDIUM", "HIGH", "CRITICAL"), "MEDIUM"
            ),
            "topics": strings(model_out.get("topics")),
            "warnings": warnings,
            "evidence": evidence,
        }


def _enum(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    text = _text(value).upper()
    return text if text in allowed else fallback


def _text(value: Any) -> str:
    """모델이 null 을 주면 빈 문자열로 만든다.

    `str(None)` 은 `"None"` 이라는 **문자열**이 된다. 그게 그대로 저장되면
    화면에 "None" 이 찍힌다 — 실제로 그렇게 나갔다.
    """
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("none", "null", "n/a") else text
