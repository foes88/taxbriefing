"""구조화 로그와 trace_id 전파 (§NFR-011 관측성).

개인정보·토큰·비밀키는 로그에 남기지 않는다 (§12.3).
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")

# §12.3 로그 마스킹 대상. 키 이름에 아래 조각이 포함되면 값을 가린다.
_SENSITIVE_HINTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "phone",
    "email",
)
_MASK = "***"


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(value: str) -> None:
    _trace_id.set(value)


def get_trace_id() -> str:
    current = _trace_id.get()
    if not current:
        current = new_trace_id()
        _trace_id.set(current)
    return current


def mask_sensitive(data: Any) -> Any:
    """감사로그·구조화 로그에 넣기 전 민감 필드를 가린다 (§7.3 audit_logs before/after)."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if any(hint in str(key).lower() for hint in _SENSITIVE_HINTS):
                out[key] = _MASK
            else:
                out[key] = mask_sensitive(value)
        return out
    if isinstance(data, list):
        return [mask_sensitive(item) for item in data]
    return data


def _add_trace_id(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["trace_id"] = get_trace_id()
    return event_dict


def _mask_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return mask_sensitive(event_dict)


def configure_logging(*, debug: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_id,
            _mask_processor,
            structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
