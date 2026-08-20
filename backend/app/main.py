"""FastAPI 애플리케이션 진입점."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.cache import TTL_SECONDS, TtlCache, cache_key
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, validation_error_handler
from app.core.logging import configure_logging, get_logger, new_trace_id, set_trace_id

settings = get_settings()
configure_logging(debug=settings.debug)
logger = get_logger(__name__)

app = FastAPI(
    title="TaxBriefing API",
    version="1.0.0",
    description=(
        "세무·정책 최신정보 수집·검증·분석·발송 플랫폼. "
        "계약 정본은 docs/contracts/ 아래에 있습니다."
    ),
)

app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

# 웹은 Vercel, API 는 별도 호스트라 교차 출처 호출이 된다 (ADR-004).
# allow_credentials 는 켜지 않는다 — 관리자 토큰은 쿠키가 아니라 Authorization 헤더로 오고,
# 쿠키를 함께 허용하면 CSRF 표면이 넓어진다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match"],
    expose_headers=["X-Trace-Id"],
    max_age=600,
)


#: 공개 화면 응답을 잠깐 들고 있는 자리.
#:
#: 관리자 화면은 담지 않는다 — 사람마다 보이는 것이 다른 응답을 한 통에
#: 담으면 남의 것이 보인다. 경로로 가른다.
_PUBLIC_PREFIX = "/api/v1/public/"
_response_cache = TtlCache()


@app.middleware("http")
async def public_cache_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """공개 GET 응답을 TTL 만큼 들고 있는다.

    자료는 아침 배치가 돌 때 하루 한 번 바뀐다. 그런데 오늘/일정/찾기를
    오가면 같은 값을 매번 미국까지 다시 물어 온다 — 왕복 한 번이 393ms 다.

    **읽기만, 성공만, 공개 경로만 담는다.** 나머지는 그대로 흘려보낸다.
    """
    cacheable = request.method == "GET" and request.url.path.startswith(_PUBLIC_PREFIX)
    if not cacheable:
        return await call_next(request)

    key = cache_key(request.url.path, request.url.query)
    hit = _response_cache.get(key)
    if hit is not None:
        body, media_type = hit  # type: ignore[misc]
        response = Response(content=body, media_type=media_type)
        # 어디서 온 값인지 남긴다. 캐시를 의심할 일이 생겼을 때
        # 이 머리글 하나면 재현이 끝난다.
        response.headers["X-Cache"] = "HIT"
        response.headers["Cache-Control"] = f"public, max-age={TTL_SECONDS}"
        return response

    response = await call_next(request)
    if response.status_code != 200:
        return response

    chunks = [chunk async for chunk in response.body_iterator]
    body = b"".join(chunks)
    _response_cache.set(key, (body, response.media_type))

    fresh = Response(
        content=body,
        status_code=response.status_code,
        media_type=response.media_type,
    )
    for name, value in response.headers.items():
        # 길이는 새 응답이 다시 계산한다. 옛 값을 그대로 옮기면
        # 본문과 어긋나 브라우저가 응답을 잘라 읽는다.
        if name.lower() != "content-length":
            fresh.headers[name] = value
    fresh.headers["X-Cache"] = "MISS"
    fresh.headers["Cache-Control"] = f"public, max-age={TTL_SECONDS}"
    return fresh


@app.middleware("http")
async def trace_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """요청마다 trace_id 를 붙인다 (§8.1 오류 응답, §NFR-011)."""
    trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
    set_trace_id(trace_id)

    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    response.headers["X-Trace-Id"] = trace_id
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


@app.get("/health", tags=["Ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


app.include_router(api_router)
