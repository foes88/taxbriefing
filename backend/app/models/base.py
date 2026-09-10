"""ORM 공통 기반.

DB enum 타입 이름은 docs/contracts/schema.sql 의 CREATE TYPE 이름과 일치해야 한다.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain import enums

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


#: 표를 담을 스키마. 값이 없으면 public — 지금까지와 같다.
#:
#: **신정 결재시스템에 합칠 때 `tb` 로 켠다.** 그러면 표 28개가 통째로
#: `tb` 스키마로 들어가고 신정 표(`public`)와 안 부딪힌다. 겹치던 이름
#: (`attachments` · `audit_logs`)도 이걸로 풀린다.
#:
#: 코드에 박지 않고 환경변수로 둔 이유 — 박으면 지금 도는 Neon 이 그 순간
#: 깨진다. 거기 표는 public 에 있다. 옮기는 날 켠다.
#:
#: 설정(app.core.config)이 아니라 os.environ 을 직접 읽는다. 모델은 설정보다
#: 먼저 만들어지므로 여기서 설정을 부르면 불러오기가 꼬인다.
DB_SCHEMA: str | None = os.environ.get("TAXBRIEFING_DB_SCHEMA") or None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=DB_SCHEMA)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_col() -> Mapped[dt.datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def pg_enum(enum_cls: type, name: str) -> SAEnum:
    """schema.sql 과 이름이 일치하는 PostgreSQL ENUM 타입."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
        create_type=True,
    )


AuthorityGradeType = pg_enum(enums.AuthorityGrade, "authority_grade")
LegalStatusType = pg_enum(enums.LegalStatus, "legal_status")
WorkflowStatusType = pg_enum(enums.WorkflowStatus, "workflow_status")
RiskLevelType = pg_enum(enums.RiskLevel, "risk_level")
ReviewDecisionType = pg_enum(enums.ReviewDecision, "review_decision")
DeliveryStatusType = pg_enum(enums.DeliveryStatus, "delivery_status")
