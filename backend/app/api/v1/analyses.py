"""AI 분석 요청·조회 (§9, A-05).

A-05: POST 는 202 + analysis_id 를 돌려주고, 결과는 GET 으로 조회한다.
MVP는 동기 실행이지만 계약은 비동기 형태를 유지해 워커 도입 시 클라이언트를 바꾸지 않는다.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession, EditorUser, IdempotencyKey, StaffUser
from app.core import audit, idempotency
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.tables import AiAnalysis
from app.schemas.api import AnalysisAccepted, AnalysisOut, AnalysisRequestBody
from app.services.ai import runner

router = APIRouter(prefix="/analyses", tags=["AI"])


@router.post("", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
def request_analysis(
    payload: AnalysisRequestBody,
    db: DbSession,
    key: IdempotencyKey,
    principal: EditorUser,
) -> AnalysisAccepted:
    body = payload.model_dump(mode="json")
    replay = idempotency.check(db, scope="analyses.create", key=key, payload=body)
    if replay is not None:
        return AnalysisAccepted.model_validate(replay.body)

    record = idempotency.begin(db, scope="analyses.create", key=key, payload=body)

    try:
        result = runner.run_analysis(
            db,
            source_version_ids=payload.source_version_ids,
            policy_cluster_id=payload.policy_cluster_id,
            tax_content_id=payload.tax_content_id,
            prompt_version=payload.prompt_version,
        )
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc

    audit.record(
        db,
        action=audit.Action.ANALYSIS_COMPLETED,
        object_type="ai_analysis",
        object_id=result.analysis.id,
        actor_user_id=principal.user_id,
        after={
            "status": result.analysis.status,
            "model_name": result.analysis.model_name,
            "prompt_version": result.analysis.prompt_version,
            "input_hash": result.analysis.input_hash,
            "reused": result.reused,
            "blocked": result.report.blocked,
        },
    )

    out = AnalysisAccepted(
        analysis_id=result.analysis.id,
        status=result.analysis.status,
        reused=result.reused,
        blocked=result.report.blocked,
    )
    idempotency.complete(
        db, record, status=status.HTTP_202_ACCEPTED, body=out.model_dump(mode="json")
    )
    return out


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: UUID, db: DbSession, principal: StaffUser
) -> AnalysisOut:
    del principal
    analysis = db.get(AiAnalysis, analysis_id)
    if analysis is None:
        raise NotFoundError("분석 결과를 찾을 수 없습니다.", {"analysis_id": str(analysis_id)})
    return AnalysisOut.model_validate(analysis)
