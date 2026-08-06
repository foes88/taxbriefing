"""AI 제공자 어댑터 (§6.1 '공급자 교체 가능한 구조').

MVP 기본값은 stub 이다. 실제 모델 계정은 미결 항목 ⑨이며, 그 전까지
파이프라인 전체(검증 V1~V7 → 게이트 → 검수)를 stub 으로 개발·테스트한다.

제공자를 바꿔도 ai_analyses 에 저장하는 실행 이력 형태는 같아야 한다 (§9.5).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import get_settings
from app.services.ai.contract import SCHEMA_VERSION

PROMPT_TEMPLATE_ID = "analysis"


@dataclass(frozen=True)
class SourceDocument:
    """프롬프트에 넣는 원문 하나 (§9.2)."""

    source_version_id: str
    authority: str
    publisher: str
    title: str
    canonical_url: str
    published_at: str | None
    collected_at: str | None
    normalized_text: str


@dataclass(frozen=True)
class AnalysisRequest:
    documents: tuple[SourceDocument, ...]
    reference_date: dt.date
    prompt_version: str
    previous_output: dict[str, Any] | None = None
    timezone: str = "Asia/Seoul"

    def input_hash(self) -> str:
        """§9.5 input_hash. 동일 입력 재분석을 피하는 멱등성 키로도 쓴다."""
        payload = {
            "documents": [
                {"id": d.source_version_id, "text_sha": _sha(d.normalized_text)}
                for d in sorted(self.documents, key=lambda d: d.source_version_id)
            ],
            "reference_date": self.reference_date.isoformat(),
            "prompt_version": self.prompt_version,
            "previous_output": self.previous_output,
        }
        return _sha(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class AnalysisResponse:
    raw_output: dict[str, Any]
    model_provider: str
    model_name: str
    latency_ms: int
    token_usage: dict[str, Any] = field(default_factory=dict)
    cost_amount: float | None = None


class AiProvider(Protocol):
    name: str

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...


class StubProvider:
    """결정론적 stub.

    실제 모델을 부르지 않고, 원문에서 **문자열로 실제 확인 가능한 것만** 채운다.
    날짜는 원문에 없으면 null 로 둔다 — 이것이 AT-05 가 검증하는 동작이며,
    stub 이 임의 날짜를 만들어내면 테스트가 통과해도 의미가 없다.
    """

    name = "stub"

    def __init__(self, model_name: str = "stub-analysis-v1") -> None:
        self.model_name = model_name

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        started = time.perf_counter()
        docs = request.documents
        primary = docs[0] if docs else None

        evidence = [
            {
                "id": f"ev{index + 1}",
                "source_version_id": doc.source_version_id,
                "locator": "field:title#p1",
                "support_type": "DIRECT",
                "note": None,
            }
            for index, doc in enumerate(docs)
        ]

        warnings: list[dict[str, Any]] = [
            {
                "code": "MISSING_EVIDENCE",
                "message": (
                    "stub 제공자는 날짜·적용대상을 추출하지 않습니다. "
                    "검수자가 원문에서 확인해야 합니다."
                ),
                "related_fields": [
                    "effective_date",
                    "promulgation_date",
                    "announcement_date",
                    "affected_users",
                ],
            }
        ]

        output: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "title": (primary.title if primary else "제목 없음")[:120],
            "one_line_summary": (
                f"{primary.publisher} 원문 {len(docs)}건이 연결되었습니다. 요약은 검수자가 작성해야 합니다."
                if primary
                else "연결된 원문이 없습니다."
            )[:250],
            # 상태는 절대 추정하지 않는다 (§9.1 금지, FR-AI-003 자동 확정 금지).
            "legal_status": "UNKNOWN",
            "announcement_date": None,
            "promulgation_date": None,
            "effective_date": None,
            "application_period": None,
            "affected_users": [],
            "excluded_users": [],
            "changes": [],
            "business_impact": [],
            "required_actions": [],
            "deadlines": [],
            "risk_level": "MEDIUM",
            "topics": [],
            "warnings": warnings,
            "evidence": evidence
            or [
                {
                    "id": "ev0",
                    "source_version_id": "00000000-0000-0000-0000-000000000000",
                    "locator": "field:title#p1",
                    "support_type": "INFERRED",
                    "note": "원문이 제공되지 않았습니다.",
                }
            ],
        }

        latency = int((time.perf_counter() - started) * 1000)
        return AnalysisResponse(
            raw_output=output,
            model_provider=self.name,
            model_name=self.model_name,
            latency_ms=latency,
            token_usage={"input_tokens": 0, "output_tokens": 0},
            cost_amount=0.0,
        )


def get_provider() -> AiProvider:
    """설정된 제공자를 돌려준다.

    실제 제공자 어댑터는 계정 확보 후 여기에 추가한다. 어떤 제공자를 쓰든
    출력은 validation.validate_output 을 반드시 통과해야 하며, 그 지점이
    제공자 교체의 안전망이다.
    """
    settings = get_settings()
    if settings.ai_provider == "stub":
        return StubProvider(settings.ai_model)
    raise NotImplementedError(
        f"AI 제공자 '{settings.ai_provider}' 어댑터가 아직 구현되지 않았습니다. "
        "미결 항목 ⑨ (AI 모델 제공자 계정) 확정 후 추가하세요."
    )
