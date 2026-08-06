"""AI 출력 검증 V1~V7 (§9.4). AI 환각에 대한 1차 방어선."""

from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

import pytest

from app.domain.enums import AuthorityGrade
from app.services.ai.validation import (
    Severity,
    SourceContext,
    sanitize,
    validate_output,
    validate_schema,
)

VID_A = uuid4()
VID_B = uuid4()

SOURCES_A = SourceContext(version_grades={VID_A: AuthorityGrade.A})
SOURCES_B = SourceContext(version_grades={VID_B: AuthorityGrade.B})
SOURCES_BOTH = SourceContext(
    version_grades={VID_A: AuthorityGrade.A, VID_B: AuthorityGrade.B}
)


def base_output(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "title": "부가가치세 신고 안내",
        "one_line_summary": "신고 기한과 대상이 안내되었습니다.",
        "legal_status": "PREANNOUNCED",
        "affected_users": ["개인사업자"],
        "excluded_users": [],
        "changes": [],
        "business_impact": [],
        "required_actions": [],
        "deadlines": [],
        "risk_level": "MEDIUM",
        "topics": ["부가세"],
        "warnings": [],
        "evidence": [
            {
                "id": "ev1",
                "source_version_id": str(VID_A),
                "locator": "field:affected_users#p3",
                "support_type": "DIRECT",
                "note": None,
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestV1Schema:
    def test_valid_payload_passes_schema(self):
        assert validate_schema(base_output()) == []

    def test_missing_required_field_fails(self):
        payload = base_output()
        del payload["risk_level"]
        assert validate_schema(payload)

    def test_unknown_field_fails(self):
        assert validate_schema(base_output(unexpected="value"))

    def test_bad_enum_fails(self):
        assert validate_schema(base_output(legal_status="시행중"))

    def test_empty_evidence_fails(self):
        assert validate_schema(base_output(evidence=[]))

    def test_schema_failure_is_stored_not_discarded(self):
        """V1: 검증 실패는 폐기가 아니라 격리다."""
        output, report = validate_output(base_output(risk_level="VERY_HIGH"), sources=SOURCES_A)
        assert output is None
        assert not report.schema_valid
        assert report.blocked
        assert report.status == "SCHEMA_FAILED"
        assert report.as_dict()["findings"][0]["details"]["schema_errors"]

    def test_action_without_evidence_is_rejected_by_schema(self):
        """V5: evidence_ids 가 빈 required_actions 는 스키마 단계에서 막힌다."""
        payload = base_output(
            required_actions=[{"text": "지금 신고하세요", "urgency": "NOW", "evidence_ids": []}]
        )
        assert validate_schema(payload)


class TestV2Dates:
    def test_ungrounded_date_is_sanitized_to_null(self):
        """AT-05: 시행일 근거가 없으면 effective_date 는 null 이다."""
        output, report = validate_output(
            base_output(effective_date="2027-01-01"), sources=SOURCES_A
        )
        assert output is not None
        assert "effective_date" in report.sanitized_fields

        cleaned = sanitize(output, report)
        assert cleaned.effective_date is None

    def test_grounded_date_survives(self):
        payload = base_output(
            effective_date="2027-01-01",
            evidence=[
                {
                    "id": "ev1",
                    "source_version_id": str(VID_A),
                    "locator": "field:effective_date#p7",
                    "support_type": "DIRECT",
                    "note": None,
                }
            ],
        )
        output, report = validate_output(payload, sources=SOURCES_A)
        assert output is not None
        assert "effective_date" not in report.sanitized_fields
        assert sanitize(output, report).effective_date is not None

    def test_application_period_dates_are_checked(self):
        payload = base_output(
            application_period={"start": "2027-01-01", "end": "2027-03-31"}
        )
        output, report = validate_output(payload, sources=SOURCES_A)
        assert output is not None
        assert {"application_start", "application_end"} <= set(report.sanitized_fields)

        cleaned = sanitize(output, report)
        assert cleaned.application_period is not None
        assert cleaned.application_period.start is None
        assert cleaned.application_period.end is None

    def test_null_dates_produce_no_finding(self):
        _, report = validate_output(base_output(), sources=SOURCES_A)
        assert not [f for f in report.findings if f.rule == "V2"]


class TestV3GradeA:
    @pytest.mark.parametrize("status", ["PROMULGATED", "EFFECTIVE"])
    def test_blocks_without_grade_a(self, status):
        _, report = validate_output(
            base_output(
                legal_status=status,
                evidence=[
                    {
                        "id": "ev1",
                        "source_version_id": str(VID_B),
                        "locator": "field:legal_status#p1",
                        "support_type": "DIRECT",
                        "note": None,
                    }
                ],
            ),
            sources=SOURCES_B,
        )
        assert report.blocked
        assert any(f.rule == "V3" and f.severity is Severity.BLOCK for f in report.findings)

    def test_passes_with_grade_a(self):
        _, report = validate_output(base_output(legal_status="EFFECTIVE"), sources=SOURCES_A)
        assert not [f for f in report.findings if f.rule == "V3"]

    @pytest.mark.parametrize("status", ["PREANNOUNCED", "BILL_PROPOSED", "DISCUSSION"])
    def test_non_confirmed_statuses_need_no_grade_a(self, status):
        _, report = validate_output(base_output(legal_status=status), sources=SOURCES_B)
        assert not [f for f in report.findings if f.rule == "V3"]


class TestV4HighRisk:
    @pytest.mark.parametrize("risk", ["HIGH", "CRITICAL"])
    def test_high_risk_blocks_auto_progress(self, risk):
        _, report = validate_output(base_output(risk_level=risk), sources=SOURCES_A)
        assert report.blocked
        assert any(f.rule == "V4" for f in report.findings)

    @pytest.mark.parametrize("risk", ["LOW", "MEDIUM"])
    def test_low_risk_does_not_block(self, risk):
        _, report = validate_output(base_output(risk_level=risk), sources=SOURCES_A)
        assert not [f for f in report.findings if f.rule == "V4"]


class TestV5EvidenceIntegrity:
    def test_dangling_evidence_id_blocks(self):
        payload = base_output(
            changes=[{"text": "세율 인상", "evidence_ids": ["ev-does-not-exist"]}]
        )
        _, report = validate_output(payload, sources=SOURCES_A)
        assert report.blocked
        finding = next(f for f in report.findings if f.rule == "V5")
        assert "ev-does-not-exist" in finding.details["dangling_evidence_ids"]

    def test_fabricated_source_version_blocks(self):
        """요청에 제공되지 않은 원문을 근거로 인용하면 지어낸 것이다."""
        stranger = uuid4()
        payload = base_output(
            evidence=[
                {
                    "id": "ev1",
                    "source_version_id": str(stranger),
                    "locator": "field:title#p1",
                    "support_type": "DIRECT",
                    "note": None,
                }
            ]
        )
        _, report = validate_output(payload, sources=SOURCES_A)
        assert report.blocked
        finding = next(
            f for f in report.findings if f.rule == "V5" and "unknown_source_version_ids" in f.details
        )
        assert str(stranger) in finding.details["unknown_source_version_ids"]

    def test_duplicate_evidence_ids_block(self):
        ev = {
            "id": "ev1",
            "source_version_id": str(VID_A),
            "locator": "field:title#p1",
            "support_type": "DIRECT",
            "note": None,
        }
        payload = base_output(evidence=[ev, copy.deepcopy(ev)])
        _, report = validate_output(payload, sources=SOURCES_A)
        assert report.blocked
        assert any("duplicate_ids" in f.details for f in report.findings if f.rule == "V5")

    def test_valid_references_pass(self):
        payload = base_output(
            changes=[{"text": "세율 인상", "evidence_ids": ["ev1"]}]
        )
        _, report = validate_output(payload, sources=SOURCES_A)
        assert not [f for f in report.findings if f.rule == "V5"]


class TestV6Conflicts:
    def test_conflict_without_warning_blocks(self):
        payload = base_output(
            evidence=[
                {
                    "id": "ev1",
                    "source_version_id": str(VID_A),
                    "locator": "field:effective_date#p2",
                    "support_type": "CONFLICT",
                    "note": "두 원문의 시행일이 다릅니다.",
                }
            ]
        )
        _, report = validate_output(payload, sources=SOURCES_A)
        assert report.blocked
        assert any(f.rule == "V6" and f.severity is Severity.BLOCK for f in report.findings)

    def test_conflict_with_warning_only_warns(self):
        payload = base_output(
            evidence=[
                {
                    "id": "ev1",
                    "source_version_id": str(VID_A),
                    "locator": "field:effective_date#p2",
                    "support_type": "CONFLICT",
                    "note": None,
                }
            ],
            warnings=[
                {
                    "code": "SOURCE_CONFLICT",
                    "message": "두 원문의 시행일이 다릅니다. 검수자가 확인해야 합니다.",
                    "related_fields": ["effective_date"],
                }
            ],
        )
        _, report = validate_output(payload, sources=SOURCES_A)
        finding = next(f for f in report.findings if f.rule == "V6")
        assert finding.severity is Severity.WARN


class TestV7NoMarkup:
    def test_html_in_summary_is_flagged(self):
        _, report = validate_output(
            base_output(one_line_summary="<b>중요</b> 신고 안내"), sources=SOURCES_A
        )
        assert any(f.rule == "V7" for f in report.findings)

    def test_plain_text_passes(self):
        _, report = validate_output(base_output(), sources=SOURCES_A)
        assert not [f for f in report.findings if f.rule == "V7"]


class TestStubProviderContract:
    """stub 제공자의 출력도 계약과 검증을 통과해야 한다."""

    def test_stub_output_is_schema_valid(self):
        import datetime as dt

        from app.services.ai.provider import AnalysisRequest, SourceDocument, StubProvider

        doc = SourceDocument(
            source_version_id=str(VID_A),
            authority="A",
            publisher="국세청",
            title="부가가치세 신고 안내",
            canonical_url="https://www.nts.go.kr/x",
            published_at=None,
            collected_at=None,
            normalized_text="본문",
        )
        response = StubProvider().analyze(
            AnalysisRequest(
                documents=(doc,), reference_date=dt.date(2026, 8, 6), prompt_version="1.0.0"
            )
        )
        assert validate_schema(response.raw_output) == []

    def test_stub_never_invents_dates(self):
        """stub 이 임의 날짜를 만들면 AT-05 테스트가 무의미해진다."""
        import datetime as dt

        from app.services.ai.provider import AnalysisRequest, SourceDocument, StubProvider

        doc = SourceDocument(
            source_version_id=str(VID_A),
            authority="A",
            publisher="국세청",
            title="2027년 1월 1일 시행 예정",
            canonical_url="https://www.nts.go.kr/x",
            published_at=None,
            collected_at=None,
            normalized_text="2027-01-01 부터 시행합니다.",
        )
        out = StubProvider().analyze(
            AnalysisRequest(
                documents=(doc,), reference_date=dt.date(2026, 8, 6), prompt_version="1.0.0"
            )
        ).raw_output

        assert out["effective_date"] is None
        assert out["promulgation_date"] is None
        assert out["announcement_date"] is None
        # 상태도 추정하지 않는다 (FR-AI-003 자동 확정 금지).
        assert out["legal_status"] == "UNKNOWN"
