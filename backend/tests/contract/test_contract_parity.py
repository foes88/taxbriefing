"""계약 파일과 코드의 정합성 (§14.1 '계약' 테스트 레벨).

docs/contracts/ 아래 파일이 정본이다. 코드가 계약에서 조용히 벗어나면
프론트엔드·AI 파이프라인과 어긋나므로, 여기서 자동으로 잡는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app.domain import enums
from app.services.ai.contract import load_contract_schema

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts"
SCHEMA_SQL = CONTRACTS / "schema.sql"
OPENAPI_YAML = CONTRACTS / "openapi.yaml"
AI_SCHEMA_JSON = CONTRACTS / "ai_output_schema.json"


def test_contract_files_exist():
    for path in (SCHEMA_SQL, OPENAPI_YAML, AI_SCHEMA_JSON):
        assert path.exists(), f"계약 파일이 없습니다: {path}"


def sql_enum_values(name: str) -> list[str]:
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    m = re.search(rf"CREATE TYPE {name} AS ENUM \(([^)]*)\);", text)
    assert m, f"{name} ENUM 정의를 schema.sql 에서 찾을 수 없습니다."
    return re.findall(r"'([^']+)'", m.group(1))


@pytest.mark.parametrize(
    ("sql_name", "enum_cls"),
    [
        ("authority_grade", enums.AuthorityGrade),
        ("legal_status", enums.LegalStatus),
        ("workflow_status", enums.WorkflowStatus),
        ("risk_level", enums.RiskLevel),
        ("review_decision", enums.ReviewDecision),
        ("delivery_status", enums.DeliveryStatus),
    ],
)
def test_enums_match_schema_sql(sql_name, enum_cls):
    """DB ENUM 과 코드 enum 이 값·순서까지 일치해야 한다."""
    assert sql_enum_values(sql_name) == [m.value for m in enum_cls]


def test_ai_schema_enums_match_code():
    schema = json.loads(AI_SCHEMA_JSON.read_text(encoding="utf-8"))
    props = schema["properties"]

    assert props["legal_status"]["enum"] == [m.value for m in enums.LegalStatus]
    assert props["risk_level"]["enum"] == [m.value for m in enums.RiskLevel]

    defs = schema["$defs"]
    assert defs["action_item"]["properties"]["urgency"]["enum"] == [
        m.value for m in enums.Urgency
    ]
    assert defs["evidence"]["properties"]["support_type"]["enum"] == [
        m.value for m in enums.SupportType
    ]


def test_openapi_enums_match_code():
    spec = yaml.safe_load(OPENAPI_YAML.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]

    assert schemas["LegalStatus"]["enum"] == [m.value for m in enums.LegalStatus]
    assert schemas["WorkflowStatus"]["enum"] == [m.value for m in enums.WorkflowStatus]
    assert schemas["RiskLevel"]["enum"] == [m.value for m in enums.RiskLevel]
    assert schemas["ReviewRequest"]["properties"]["decision"]["enum"] == [
        m.value for m in enums.ReviewDecision
    ]


def test_openapi_channels_do_not_yet_include_telegram():
    """TELEGRAM 은 명세서 v1.0 이후 추가된 채널이다.

    계약 갱신(미결 ①) 전까지 openapi.yaml 의 channels enum 에 없는 것이 정상이다.
    계약이 갱신되면 이 테스트가 실패하며, 그때 코드 주석과 §11.4 를 함께 정리한다.
    """
    spec = yaml.safe_load(OPENAPI_YAML.read_text(encoding="utf-8"))
    channels = spec["components"]["schemas"]["CampaignCreate"]["properties"]["channels"]
    contract_channels = set(channels["items"]["enum"])

    assert contract_channels == {"EMAIL", "KAKAO", "SMS", "WEB"}
    assert enums.Channel.TELEGRAM.value not in contract_channels
    # 계약에 있는 채널은 모두 코드에도 있어야 한다.
    assert contract_channels <= {m.value for m in enums.Channel}


def test_review_request_uses_source_version_ids():
    """A-01: 검수자가 확인한 대상은 원문이 아니라 원문 *버전* 이다."""
    from app.schemas.api import ReviewRequest

    assert "checked_source_version_ids" in ReviewRequest.model_fields
    assert "checked_source_ids" not in ReviewRequest.model_fields

    spec = yaml.safe_load(OPENAPI_YAML.read_text(encoding="utf-8"))
    required = spec["components"]["schemas"]["ReviewRequest"]["required"]
    assert "checked_source_version_ids" in required


def test_ai_contract_schema_loads():
    schema = load_contract_schema()
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["properties"]["schema_version"]["const"] == "1.0"


def test_pydantic_model_covers_every_contract_property():
    """계약에 있는 필드가 Pydantic 모델에 빠짐없이 있어야 한다."""
    from app.services.ai.contract import AnalysisOutput

    contract_props = set(load_contract_schema()["properties"])
    model_fields = set(AnalysisOutput.model_fields)
    assert contract_props <= model_fields, contract_props - model_fields


def test_pydantic_model_adds_no_extra_fields():
    """반대 방향도 확인한다. 모델에만 있는 필드는 계약 위반 출력을 만든다."""
    from app.services.ai.contract import AnalysisOutput

    contract_props = set(load_contract_schema()["properties"])
    model_fields = set(AnalysisOutput.model_fields)
    assert model_fields <= contract_props, model_fields - contract_props


def test_required_fields_match():
    from app.services.ai.contract import AnalysisOutput

    required = set(load_contract_schema()["required"])
    for name in required:
        field = AnalysisOutput.model_fields[name]
        # schema_version 은 const 이므로 기본값이 있어도 계약을 만족한다.
        if name == "schema_version":
            continue
        assert field.is_required(), f"{name} 은 계약상 필수인데 모델에서 선택입니다."
