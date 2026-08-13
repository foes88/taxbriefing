"""429 는 두 가지다. 네트워크 없이 실행된다.

한도의 종류가 다르면 대응도 다르다. 분당은 기다리고, 하루치는 멈춘다.
같은 429 라고 같이 다뤘더니 40분을 아무 소득 없이 버렸다.
"""

from __future__ import annotations

import httpx

from app.services.ai.groq_provider import GroqDailyExhausted, _daily_exhausted, _retry_after

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
