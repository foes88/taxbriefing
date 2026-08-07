"""업종 분류와 본문 검색

상담 중에 "학원 원장님이 4대보험 물어보는데" 로 찾을 수 있어야 한다.
지금은 제목과 한 줄 요약만 검색된다 — 정작 답이 들어 있는 개정 내용과
사업자 할 일은 검색되지 않는다.

두 가지를 넣는다.

1. tax_contents.industries — 업종 분류 (app.domain.industry 의 열거값)
2. search_text + GIN 인덱스 — 제목·요약·개정내용·할일을 합친 검색용 텍스트

**search_text 를 생성 컬럼이 아니라 일반 컬럼으로 둔 이유.**
본문은 content_versions 에 있고 tax_contents 에는 없다. 다른 테이블 값을
generated column 으로 끌어올 수 없으므로, 게시 시점에 코드가 채운다.

**형태소 분석기 없이 간다.**
PostgreSQL 기본 설치에는 한국어 사전이 없다. simple 로 토큰을 나누면
"학원" 은 "학원의" 를 못 찾는다. 그래서 pg_trgm 으로 부분일치를 쓴다.
정확도는 형태소 분석보다 낮지만, 사전 설치 없이 어느 호스팅에서든 돈다 —
Neon·Render 로 옮길 예정이므로 이 조건이 실제로 중요하다.

Revision ID: b7c21e4d9f30
Revises: a35a0bffbd18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c21e4d9f30"
down_revision: str | None = "a35a0bffbd18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "tax_contents",
        sa.Column(
            "industries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("tax_contents", sa.Column("search_text", sa.Text(), nullable=True))

    # 업종 필터는 배열 포함 검사다. GIN 이 맞다.
    op.create_index(
        "idx_tax_contents_industries",
        "tax_contents",
        ["industries"],
        postgresql_using="gin",
    )
    # 부분일치 검색. trigram 인덱스가 없으면 61건일 때는 괜찮아도
    # 몇 천 건이 되면 매 검색이 전체 스캔이 된다.
    op.create_index(
        "idx_tax_contents_search",
        "tax_contents",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_tax_contents_search", table_name="tax_contents")
    op.drop_index("idx_tax_contents_industries", table_name="tax_contents")
    op.drop_column("tax_contents", "search_text")
    op.drop_column("tax_contents", "industries")
    # pg_trgm 은 지우지 않는다. 다른 곳에서 쓰고 있을 수 있다.
