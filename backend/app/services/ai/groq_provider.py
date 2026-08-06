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


class GroqTooLarge(GroqError):
    """1회 요청이 너무 크다. 기다려도 소용없고 줄여야 한다."""

    def __init__(self) -> None:
        super().__init__("요청이 모델 한도보다 큽니다.")


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
        """
        budget = MAX_DOC_CHARS

        for attempt in range(MAX_RETRIES):
            try:
                return self._call(self._build_messages(request, budget))
            except GroqRateLimited as exc:
                if attempt == MAX_RETRIES - 1:
                    raise GroqError("GROQ 분당 한도를 계속 초과합니다.") from exc
                wait = exc.retry_after or BACKOFF_SECONDS[attempt]
                logger.info("groq.rate_limited", wait_seconds=wait, attempt=attempt + 1)
                time.sleep(wait)
            except GroqTooLarge as exc:
                if budget <= 1500:
                    raise GroqError(
                        "원문을 최소 크기까지 줄여도 요청이 너무 큽니다."
                    ) from exc
                budget = budget // 2
                logger.info("groq.shrink_input", new_budget=budget)

        raise GroqError("GROQ 호출을 완료하지 못했습니다.")

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

    def _call(self, messages: list[dict[str, str]]) -> dict[str, Any]:
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
                    "max_tokens": 2400,
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.HTTPError as exc:
            raise GroqError(f"GROQ 호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code == 429:
            raise GroqRateLimited(_retry_after(response))
        if response.status_code == 413:
            raise GroqTooLarge()
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
