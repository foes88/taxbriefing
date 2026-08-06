"""ORM 공통 기반.

DB enum 타입 이름은 docs/contracts/schema.sql 의 CREATE TYPE 이름과 일치해야 한다.
"""

from __future__ import annotations

import datetime as dt
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


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
