"""FastAPI 애플리케이션 진입점."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
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
