"""AI 구조화 출력 계약 (§9.3).

**정본은 docs/contracts/ai_output_schema.json 이다.** 아래 Pydantic 모델은 타입 편의를 위한
거울이며, 실제 검증은 계약 파일을 jsonschema 로 직접 적용해 수행한다 (validation.py).
계약 파일을 손으로 옮겨 적은 모델만 믿으면, 파일이 바뀔 때 조용히 어긋난다.
tests/contract/test_ai_schema_parity.py 가 둘의 정합성을 강제한다.
"""

from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.domain.enums import LegalStatus, RiskLevel, SupportType, Urgency

SCHEMA_VERSION = "1.0"


@lru_cache
def load_contract_schema() -> dict[str, Any]:
    """docs/contracts/ai_output_schema.json 을 읽는다."""
    path: Path = get_settings().ai_output_schema_path
    if not path.exists():
        raise FileNotFoundError(
            f"AI 출력 계약 파일을 찾을 수 없습니다: {path}. "
            "docs/contracts/ai_output_schema.json 이 정본입니다."
        )
    return json.loads(path.read_text(encoding="utf-8"))


class Evidence(BaseModel):
    """구조화 필드를 뒷받침하는 원문 위치 (§부록 C)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_version_id: str
    locator: str = Field(description="page/paragraph/offset locator")
    support_type: SupportType
    note: str | None = None


class GroundedItem(BaseModel):
    """근거 없이는 존재할 수 없는 서술 항목."""

    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str] = Field(min_length=1)


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    urgency: Urgency
    evidence_ids: list[str] = Field(min_length=1)


class Deadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    date: dt.date | None
    evidence_ids: list[str]


class ApplicationPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: dt.date | None
    end: dt.date | None


class Warning_(BaseModel):
    """충돌·불확실·추가검토 경고 (§9.1 필수)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    related_fields: list[str] = Field(default_factory=list)


class AnalysisOutput(BaseModel):
    """AI 분석 출력 전체 (§9.3)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    title: str = Field(min_length=1, max_length=120)
    one_line_summary: str = Field(min_length=1, max_length=250)
    legal_status: LegalStatus

    announcement_date: dt.date | None = None
    promulgation_date: dt.date | None = None
    effective_date: dt.date | None = None
    application_period: ApplicationPeriod | None = None

    affected_users: list[str] = Field(max_length=30)
    excluded_users: list[str] = Field(default_factory=list)
    changes: list[GroundedItem] = Field(max_length=20)
    business_impact: list[GroundedItem] = Field(max_length=20)
    required_actions: list[ActionItem] = Field(max_length=20)
    deadlines: list[Deadline] = Field(default_factory=list)

    risk_level: RiskLevel
    topics: list[str] = Field(max_length=30)
    # 계약상 required 다. 기본값을 주면 모델이 계약보다 느슨해지므로 필수로 둔다 —
    # "경고할 것이 없다"는 판단도 명시적으로 빈 배열을 보내야 한다 (§9.1 필수 항목).
    warnings: list[Warning_]
    evidence: list[Evidence] = Field(min_length=1)

    # ---- 파생 조회 ----

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}

    def date_fields(self) -> dict[str, dt.date | None]:
        """§9.4 V2 검사 대상 날짜 필드."""
        return {
            "announcement_date": self.announcement_date,
            "promulgation_date": self.promulgation_date,
            "effective_date": self.effective_date,
            "application_start": self.application_period.start if self.application_period else None,
            "application_end": self.application_period.end if self.application_period else None,
        }

    def referenced_evidence_ids(self) -> set[str]:
        ids: set[str] = set()
        for item in (*self.changes, *self.business_impact, *self.required_actions):
            ids.update(item.evidence_ids)
        for deadline in self.deadlines:
            ids.update(deadline.evidence_ids)
        return ids

    def warning_codes(self) -> set[str]:
        return {w.code for w in self.warnings}

    def fields_with_warning(self, code: str) -> set[str]:
        out: set[str] = set()
        for w in self.warnings:
            if w.code == code:
                out.update(w.related_fields)
        return out
