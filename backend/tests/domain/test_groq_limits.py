"""429 는 두 가지다. 네트워크 없이 실행된다.

한도의 종류가 다르면 대응도 다르다. 분당은 기다리고, 하루치는 멈춘다.
같은 429 라고 같이 다뤘더니 40분을 아무 소득 없이 버렸다.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from app.services.ai.groq_provider import (
    GroqDailyExhausted,
    GroqProvider,
    _daily_exhausted,
    _retry_after,
)
from app.services.ai.provider import AnalysisRequest, SourceDocument


def _provider(handler) -> GroqProvider:
    provider = GroqProvider(
        api_key="test", model="test-model", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    return provider


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        documents=(
            SourceDocument(
                source_version_id="00000000-0000-0000-0000-000000000001",
                authority="A",
                publisher="법제처",
                title="소득세법 시행령",
                canonical_url="https://www.law.go.kr/법령/소득세법 시행령",
                published_at=None,
                collected_at=None,
                normalized_text="제1조 …",
            ),
        ),
        reference_date=dt.date(2026, 8, 14),
        prompt_version="v1",
    )


def _ok_payload() -> dict:
    body = {
        "one_line_summary": "요약",
        "affected_users": [],
        "excluded_users": [],
        "changes": [],
        "business_impact": [],
        "required_actions": [],
        "warnings": [],
    }
    return {"choices": [{"message": {"content": json.dumps(body, ensure_ascii=False)}}], "usage": {}}

DAILY_BODY = (
    '{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in '
    "organization `org_abc` service tier `on_demand` on tokens per day (TPD): "
    'Limit 200000, Used 199862, Requested 3081. Please try again in 21m8s.",'
    '"type":"tokens","code":"rate_limit_exceeded"}}'
)

MINUTE_BODY = (
    '{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` on '
    'tokens per minute (TPM): Limit 8000, Used 7900, Requested 500. '
    'Please try again in 8.5s.","code":"rate_limit_exceeded"}}'
)


def _response(body: str) -> httpx.Response:
    return httpx.Response(429, text=body, request=httpx.Request("POST", "https://api.groq.com/x"))


class TestDailyExhausted:
    """하루치는 기다려도 안 풀린다."""

    def test_detected(self):
        exc = _daily_exhausted(_response(DAILY_BODY))
        assert isinstance(exc, GroqDailyExhausted)
        assert exc.used == 199862
        assert exc.limit == 200000

    def test_message_says_it_wont_clear_today(self):
        """예전 메시지는 "분당 한도를 계속 초과합니다" 였다.

        그걸 보고 호출이 너무 큰 줄 알고 원문을 자르는 쪽을 팠다.
        메시지가 틀리면 고치는 사람도 엉뚱한 데를 판다.
        """
        exc = _daily_exhausted(_response(DAILY_BODY))
        assert exc is not None
        assert "하루치" in str(exc)
        assert "내일" in str(exc)
        assert "199,862" in str(exc)

    def test_minute_limit_is_not_mistaken_for_daily(self):
        assert _daily_exhausted(_response(MINUTE_BODY)) is None

    def test_unrelated_body(self):
        assert _daily_exhausted(_response('{"error":{"message":"nope"}}')) is None


class TestRetryAfter:
    def test_reads_the_body_hint(self):
        """서버가 알려주는 대기 시간을 따른다. 임의로 짐작하지 않는다."""
        assert _retry_after(_response(MINUTE_BODY)) == 9.5

    def test_header_wins(self):
        response = httpx.Response(
            429,
            text=MINUTE_BODY,
            headers={"retry-after": "3"},
            request=httpx.Request("POST", "https://api.groq.com/x"),
        )
        assert _retry_after(response) == 3.0

    def test_capped(self):
        """서버가 21분을 기다리라고 해도 그만큼 붙잡고 있지 않는다."""
        body = '{"error":{"message":"Please try again in 1268s."}}'
        assert _retry_after(_response(body)) == 90.0


UNFINISHED_JSON_BODY = (
    '{"error":{"message":"Failed to validate JSON. Please adjust your prompt. '
    'See \'failed_generation\'.","type":"invalid_request_error",'
    '"failed_generation":"{\\"one_line_summary\\": \\"소득세법 시행령이"}}'
)


class TestUnfinishedJson:
    """모델이 JSON 을 닫기 전에 출력 예산이 떨어진 경우.

    GROQ 문구는 "Failed to validate JSON. Please adjust your prompt." 다.
    프롬프트가 잘못된 것처럼 읽히지만 아니다 — 조세특례제한법처럼 개정
    항목이 많은 건에서만 났고 짧은 건은 같은 프롬프트로 잘 됐다.

    기다려도 안 되고 원문을 줄여도 안 된다. 출력 예산을 늘려야 한다.
    """

    def test_recognised_as_its_own_failure(self):
        from app.services.ai.groq_provider import GroqError

        provider = _provider(lambda r: httpx.Response(400, text=UNFINISHED_JSON_BODY))
        # 예산을 최대까지 올려도 계속 실패하면 그 사실을 말하고 포기한다.
        with pytest.raises(GroqError, match="최대로 올려도"):
            provider.analyze(_request())

    def test_grows_the_budget_and_succeeds(self):
        """한 번 늘려서 되면 그걸로 끝난다."""
        seen: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            seen.append(_json.loads(request.content)["max_tokens"])
            if len(seen) == 1:
                return httpx.Response(400, text=UNFINISHED_JSON_BODY)
            return httpx.Response(200, json=_ok_payload())

        _provider(handler).analyze(_request())
        assert seen[0] == 2_400
        assert seen[1] == 4_800, "예산을 두 배로 올려 다시 불러야 한다"

    def test_other_400_is_not_mistaken_for_this(self):
        from app.services.ai.groq_provider import GroqError

        provider = _provider(
            lambda r: httpx.Response(400, text='{"error":{"message":"bad model"}}')
        )
        with pytest.raises(GroqError, match="HTTP 400"):
            provider.analyze(_request())
