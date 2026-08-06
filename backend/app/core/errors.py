"""표준 오류 응답 (§8.1).

모든 오류는 code / message / details / trace_id 를 포함한다.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logging import get_trace_id

# Starlette 가 HTTP_422_UNPROCESSABLE_ENTITY 를 ..._CONTENT 로 개명 중이다.
# 숫자를 직접 쓰면 어느 버전에서도 경고 없이 동작한다.
HTTP_422 = 422


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
    trace_id: str


class AppError(Exception):
    """도메인 규칙 위반. HTTP 상태와 기계 판독 가능한 code를 갖는다."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(AppError):
    """낙관적 잠금 충돌 또는 중복 요청 (§8.1)."""

    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class ValidationFailedError(AppError):
    status_code = HTTP_422
    code = "VALIDATION_FAILED"


class GateFailedError(AppError):
    """검증 게이트 G1~G6 실패 (§3.7). 세무정보 안전장치의 최종 방어선."""

    status_code = HTTP_422
    code = "GATE_FAILED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


def _payload(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return ErrorResponse(
        code=code, message=message, details=details, trace_id=get_trace_id()
    ).model_dump()


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.code, exc.message, exc.details),
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_422,
        content=_payload(
            "REQUEST_VALIDATION_FAILED",
            "요청 본문이 API 계약과 일치하지 않습니다.",
            {"errors": exc.errors()},
        ),
    )
