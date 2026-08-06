"""AI 분석 실행과 이력 저장 (§9.5, FR-AI-006).

같은 입력·프롬프트·모델이면 재분석하지 않고 기존 결과를 돌려준다 (§9.5 input_hash).
분석 비용은 실제 비용이고, 같은 답을 두 번 살 이유가 없다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import AuthorityGrade
from app.models.tables import AiAnalysis, RawContent, RawContentVersion, Source
from app.services.ai.contract import SCHEMA_VERSION, AnalysisOutput
from app.services.ai.provider import (
    PROMPT_TEMPLATE_ID,
    AnalysisRequest,
    SourceDocument,
    get_provider,
)
from app.services.ai.validation import SourceContext, ValidationReport, sanitize, validate_output


@dataclass
class AnalysisResult:
    analysis: AiAnalysis
    output: AnalysisOutput | None
    report: ValidationReport
    reused: bool = False


def _load_documents(
    db: Session, source_version_ids: list[UUID]
) -> tuple[list[SourceDocument], dict[UUID, AuthorityGrade]]:
    rows = db.execute(
        select(RawContentVersion, RawContent, Source)
        .join(RawContent, RawContentVersion.raw_content_id == RawContent.id)
        .join(Source, RawContent.source_id == Source.id)
        .where(RawContentVersion.id.in_(source_version_ids))
    ).all()

    documents: list[SourceDocument] = []
    grades: dict[UUID, AuthorityGrade] = {}
    for version, raw, source in rows:
        grades[version.id] = source.authority
        documents.append(
            SourceDocument(
                source_version_id=str(version.id),
                authority=source.authority.value,
                publisher=raw.publisher,
                title=raw.title,
                canonical_url=raw.canonical_url,
                published_at=raw.published_at.isoformat() if raw.published_at else None,
                collected_at=version.collected_at.isoformat() if version.collected_at else None,
                normalized_text=version.normalized_text,
            )
        )
    return documents, grades


def run_analysis(
    db: Session,
    *,
    source_version_ids: list[UUID],
    policy_cluster_id: UUID | None = None,
    tax_content_id: UUID | None = None,
    reference_date: dt.date | None = None,
    prompt_version: str | None = None,
) -> AnalysisResult:
    settings = get_settings()
    prompt_version = prompt_version or settings.ai_prompt_version
    reference_date = reference_date or dt.datetime.now(dt.UTC).date()

    documents, grades = _load_documents(db, source_version_ids)
    if not documents:
        raise ValueError("분석할 원문 버전을 찾을 수 없습니다.")

    provider = get_provider()
    request = AnalysisRequest(
        documents=tuple(documents),
        reference_date=reference_date,
        prompt_version=prompt_version,
    )
    digest = request.input_hash()

    existing = db.execute(
        select(AiAnalysis)
        .where(
            AiAnalysis.input_hash == digest,
            AiAnalysis.prompt_version == prompt_version,
            AiAnalysis.model_name == getattr(provider, "model_name", settings.ai_model),
            AiAnalysis.schema_version == SCHEMA_VERSION,
        )
        .order_by(AiAnalysis.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        output, report = _revalidate(existing, grades)
        return AnalysisResult(existing, output, report, reused=True)

    response = provider.analyze(request)
    output, report = validate_output(
        response.raw_output, sources=SourceContext(version_grades=grades)
    )
    if output is not None and report.sanitized_fields:
        output = sanitize(output, report)

    analysis = AiAnalysis(
        tax_content_id=tax_content_id,
        policy_cluster_id=policy_cluster_id,
        prompt_template_id=PROMPT_TEMPLATE_ID,
        prompt_version=prompt_version,
        schema_version=SCHEMA_VERSION,
        model_provider=response.model_provider,
        model_name=response.model_name,
        input_hash=digest,
        # V1: 검증에 실패해도 원본 출력을 그대로 보존한다.
        output_json=response.raw_output,
        validation_result=report.as_dict(),
        token_usage=response.token_usage,
        cost_amount=response.cost_amount,
        latency_ms=response.latency_ms,
        status=report.status,
    )
    db.add(analysis)
    db.flush()
    return AnalysisResult(analysis, output, report)


def _revalidate(
    analysis: AiAnalysis, grades: dict[UUID, AuthorityGrade]
) -> tuple[AnalysisOutput | None, ValidationReport]:
    """저장된 출력을 현재 규칙으로 다시 검증한다.

    검증 규칙은 저장 시점보다 강해질 수 있다. 예전에 통과한 출력이라도
    지금 기준으로 다시 판정해야 규칙 강화가 실제로 효력을 갖는다.
    """
    payload = analysis.output_json or {}
    output, report = validate_output(payload, sources=SourceContext(version_grades=grades))
    if output is not None and report.sanitized_fields:
        output = sanitize(output, report)
    return output, report
