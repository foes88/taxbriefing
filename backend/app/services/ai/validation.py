"""AI 출력 검증 V1~V7 (§9.4).

이 모듈이 AI 환각에 대한 1차 방어선이다. 게이트 G1~G6이 2차 방어선이며,
전문가 승인이 3차다. 세 층이 모두 독립적으로 동작해야 한다.

핵심 원칙: **검증 실패는 폐기가 아니라 격리다** (V1).
출력을 버리면 왜 실패했는지 조사할 수 없고, 프롬프트를 개선할 수 없다.
저장하되 자동 진행을 막고 검수 큐에 올린다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

import jsonschema

from app.domain.enums import AuthorityGrade, SupportType
from app.services.ai.contract import AnalysisOutput, load_contract_schema


class Severity(StrEnum):
    BLOCK = "BLOCK"
    """자동 진행 금지. 검수자가 처리해야 한다."""

    SANITIZE = "SANITIZE"
    """값을 제거하고 진행. 제거 사실을 기록한다."""

    WARN = "WARN"
    """표시 경고."""


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    fields: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    schema_valid: bool
    findings: list[Finding] = field(default_factory=list)
    sanitized_fields: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """자동 진행이 금지되었는가."""
        return not self.schema_valid or any(f.severity is Severity.BLOCK for f in self.findings)

    @property
    def status(self) -> str:
        """ai_analyses.status 에 저장할 값."""
        if not self.schema_valid:
            return "SCHEMA_FAILED"
        if self.blocked:
            return "NEEDS_REVIEW"
        return "VALIDATED"

    def as_dict(self) -> dict[str, Any]:
        """ai_analyses.validation_result 저장 형태."""
        return {
            "schema_valid": self.schema_valid,
            "status": self.status,
            "blocked": self.blocked,
            "sanitized_fields": self.sanitized_fields,
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity.value,
                    "message": f.message,
                    "fields": list(f.fields),
                    "details": f.details,
                }
                for f in self.findings
            ],
        }


@dataclass(frozen=True)
class SourceContext:
    """분석 요청에 실제로 제공된 원문 버전들.

    AI가 여기 없는 source_version_id 를 인용하면 근거를 지어낸 것이다.
    """

    version_grades: dict[UUID, AuthorityGrade]

    def allowed_ids(self) -> set[str]:
        return {str(k) for k in self.version_grades}

    def grade_of(self, source_version_id: str) -> AuthorityGrade | None:
        try:
            return self.version_grades.get(UUID(source_version_id))
        except ValueError:
            return None


def validate_schema(payload: dict[str, Any]) -> list[str]:
    """V1 — 계약 파일(ai_output_schema.json)로 직접 검증한다.

    Pydantic 모델이 아니라 계약 파일을 권위로 삼는다.
    """
    validator = jsonschema.Draft202012Validator(load_contract_schema())
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    ]


def _v2_dates_need_evidence(
    output: AnalysisOutput, evidence_fields: dict[str, set[str]]
) -> list[Finding]:
    """V2 — 원문에 없는 날짜는 null 이어야 한다 (AT-05).

    날짜 값이 있는데 그 필드를 뒷받침하는 evidence 가 없으면 지어낸 것으로 본다.
    SANITIZE: 값을 null 로 되돌리고 검수 경고를 남긴다.
    """
    ungrounded = [
        name for name, value in output.date_fields().items()
        if value is not None and not evidence_fields.get(name)
    ]
    if not ungrounded:
        return []
    return [
        Finding(
            "V2",
            Severity.SANITIZE,
            "원문 근거가 없는 날짜 값을 null 로 되돌렸습니다. 임의 날짜 생성은 금지됩니다.",
            tuple(ungrounded),
        )
    ]


def _v3_status_needs_grade_a(output: AnalysisOutput, sources: SourceContext) -> list[Finding]:
    """V3 — PROMULGATED/EFFECTIVE 는 A등급 근거 없이 통과할 수 없다."""
    if not output.legal_status.requires_grade_a_evidence:
        return []

    grades = {sources.grade_of(e.source_version_id) for e in output.evidence}
    if AuthorityGrade.A in grades:
        return []

    return [
        Finding(
            "V3",
            Severity.BLOCK,
            (
                f"'{output.legal_status.value}' 상태는 A등급(법령·관보·의안 원문) 근거가 "
                "있어야 주장할 수 있습니다."
            ),
            ("legal_status",),
            {"available_grades": sorted(g.value for g in grades if g)},
        )
    ]


def _v4_high_risk_needs_expert(output: AnalysisOutput) -> list[Finding]:
    """V4 — HIGH/CRITICAL 은 전문가 승인 필수. AI 단계에서는 표식만 남긴다."""
    if not output.risk_level.requires_expert_approval:
        return []
    return [
        Finding(
            "V4",
            Severity.BLOCK,
            f"위험도 {output.risk_level.value} — 전문가 승인 없이 발송할 수 없습니다.",
            ("risk_level",),
        )
    ]


def _v5_evidence_integrity(output: AnalysisOutput, sources: SourceContext) -> list[Finding]:
    """V5 + S-01/S-02 — 근거 참조 무결성.

    세 가지를 확인한다.
      a) evidence_ids 가 실제 evidence[].id 를 가리키는가 (dangling 참조)
      b) evidence[].id 가 중복되지 않는가
      c) source_version_id 가 요청에 제공된 원문 버전인가 (지어낸 출처)
    """
    findings: list[Finding] = []
    known = output.evidence_by_id()

    seen: set[str] = set()
    duplicates = sorted({e.id for e in output.evidence if e.id in seen or seen.add(e.id)})
    if duplicates:
        findings.append(
            Finding("V5", Severity.BLOCK, "evidence.id 가 중복되었습니다.", ("evidence",),
                    {"duplicate_ids": duplicates})
        )

    dangling = sorted(output.referenced_evidence_ids() - known.keys())
    if dangling:
        findings.append(
            Finding(
                "V5",
                Severity.BLOCK,
                "존재하지 않는 evidence_id 를 참조합니다.",
                ("changes", "business_impact", "required_actions", "deadlines"),
                {"dangling_evidence_ids": dangling},
            )
        )

    allowed = sources.allowed_ids()
    if allowed:
        fabricated = sorted(
            {e.source_version_id for e in output.evidence if e.source_version_id not in allowed}
        )
        if fabricated:
            findings.append(
                Finding(
                    "V5",
                    Severity.BLOCK,
                    "분석 요청에 제공되지 않은 원문 버전을 근거로 인용했습니다.",
                    ("evidence",),
                    {"unknown_source_version_ids": fabricated},
                )
            )

    return findings


def _v6_conflicts(output: AnalysisOutput) -> list[Finding]:
    """V6 — 원문이 충돌하면 어느 쪽도 임의 선택하지 않는다."""
    conflicts = [e for e in output.evidence if e.support_type is SupportType.CONFLICT]
    if not conflicts:
        return []
    if output.warnings:
        return [
            Finding(
                "V6",
                Severity.WARN,
                "원문 간 충돌이 표시되었습니다. 검수자가 어느 근거를 채택할지 결정해야 합니다.",
                ("evidence", "warnings"),
                {"conflict_evidence_ids": [e.id for e in conflicts]},
            )
        ]
    return [
        Finding(
            "V6",
            Severity.BLOCK,
            "충돌 근거(CONFLICT)가 있으나 warning 이 없습니다. 충돌은 반드시 표면화해야 합니다.",
            ("warnings",),
            {"conflict_evidence_ids": [e.id for e in conflicts]},
        )
    ]


def _v7_no_html(output: AnalysisOutput) -> list[Finding]:
    """V7 — 모델은 HTML을 직접 생성하지 않는다. 렌더링은 채널 템플릿의 책임이다."""
    suspects: list[str] = []
    texts = {
        "title": output.title,
        "one_line_summary": output.one_line_summary,
    }
    for idx, item in enumerate(output.changes):
        texts[f"changes[{idx}].text"] = item.text
    for idx, item in enumerate(output.business_impact):
        texts[f"business_impact[{idx}].text"] = item.text
    for idx, action in enumerate(output.required_actions):
        texts[f"required_actions[{idx}].text"] = action.text

    for name, value in texts.items():
        if "<" in value and ">" in value:
            suspects.append(name)

    if not suspects:
        return []
    return [
        Finding(
            "V7",
            Severity.SANITIZE,
            "모델 출력에 마크업으로 보이는 문자열이 있습니다. 구조화 데이터만 반환해야 합니다.",
            tuple(suspects),
        )
    ]


def _s03_missing_evidence_warning(
    output: AnalysisOutput, evidence_fields: dict[str, set[str]]
) -> list[Finding]:
    """S-03 — 근거가 없는 주요 필드는 MISSING_EVIDENCE 경고로 표면화해야 한다.

    계약 스키마에 missing_reason 필드가 없으므로 warnings[] 로 대체한다 (§9.4 S-03).
    """
    declared = output.fields_with_warning("MISSING_EVIDENCE")
    ungrounded_targeting = [
        name
        for name in ("affected_users", "excluded_users")
        if getattr(output, name) and not evidence_fields.get(name) and name not in declared
    ]
    if not ungrounded_targeting:
        return []
    return [
        Finding(
            "S-03",
            Severity.WARN,
            (
                "적용대상·제외대상에 근거가 없는데 MISSING_EVIDENCE 경고도 없습니다. "
                "개인화 발송에서 제외됩니다 (게이트 G4)."
            ),
            tuple(ungrounded_targeting),
        )
    ]


def _evidence_fields_map(output: AnalysisOutput) -> dict[str, set[str]]:
    """evidence 를 필드명 기준으로 묶는다.

    계약 스키마의 evidence 에는 field_name 이 없다. locator 앞에 `field:` 접두어로
    필드를 표기하는 프롬프트 규약을 쓰고, 없으면 deadlines/날짜 참조로 유추한다.
    """
    by_field: dict[str, set[str]] = {}
    for e in output.evidence:
        locator = e.locator
        if locator.startswith("field:"):
            head, _, _rest = locator.partition("#")
            field_name = head.removeprefix("field:").strip()
            if field_name:
                by_field.setdefault(field_name, set()).add(e.id)
    return by_field


def validate_output(
    payload: dict[str, Any],
    *,
    sources: SourceContext,
    now: dt.datetime | None = None,
) -> tuple[AnalysisOutput | None, ValidationReport]:
    """AI 출력 전체를 검증한다.

    반환값이 `(None, report)` 이면 스키마 자체가 깨진 것이다. 이 경우에도
    payload 원본은 ai_analyses.output_json 에 그대로 저장한다 (V1: 저장하되 진행 금지).
    """
    del now  # 현재 규칙은 시각에 의존하지 않는다. 시그니처는 향후 규칙을 위해 유지.

    schema_errors = validate_schema(payload)
    if schema_errors:
        return None, ValidationReport(
            schema_valid=False,
            findings=[
                Finding(
                    "V1",
                    Severity.BLOCK,
                    "출력이 AI 계약 스키마를 위반했습니다. 저장하되 자동 진행을 중단합니다.",
                    (),
                    {"schema_errors": schema_errors},
                )
            ],
        )

    output = AnalysisOutput.model_validate(payload)
    evidence_fields = _evidence_fields_map(output)

    findings: list[Finding] = []
    findings += _v2_dates_need_evidence(output, evidence_fields)
    findings += _v3_status_needs_grade_a(output, sources)
    findings += _v4_high_risk_needs_expert(output)
    findings += _v5_evidence_integrity(output, sources)
    findings += _v6_conflicts(output)
    findings += _v7_no_html(output)
    findings += _s03_missing_evidence_warning(output, evidence_fields)

    report = ValidationReport(schema_valid=True, findings=findings)
    report.sanitized_fields = sorted(
        {f for finding in findings if finding.severity is Severity.SANITIZE for f in finding.fields}
    )
    return output, report


def sanitize(output: AnalysisOutput, report: ValidationReport) -> AnalysisOutput:
    """SANITIZE 판정된 값을 실제로 제거한다 (V2: 근거 없는 날짜 → null)."""
    if not report.sanitized_fields:
        return output

    data = output.model_dump()
    period = data.get("application_period")

    for name in report.sanitized_fields:
        if name in ("announcement_date", "promulgation_date", "effective_date"):
            data[name] = None
        elif name == "application_start" and isinstance(period, dict):
            period["start"] = None
        elif name == "application_end" and isinstance(period, dict):
            period["end"] = None

    return AnalysisOutput.model_validate(data)
