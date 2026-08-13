"""콘텐츠 종류 구분

지금까지는 모든 콘텐츠가 "법령 개정" 이라는 전제로 만들어졌다. 그런데
조세심판원 심판례가 들어오면서 그 전제가 깨졌다.

    심판례는 개정된 것이 아니고, 시행일도 없고, 정책 상태도 없다.

구분이 없으니 화면이 심판례에도 시행일과 상태 배지를 붙이려 하고,
임시 요약은 "…이(가) 개정되어 시행됩니다" 라고 썼다. 둘 다 거짓이다.

앞으로 국회 의안·법령해석례·지원사업이 더 들어온다. 종류를 값으로 두지 않으면
화면마다 "이건 법령인가 아닌가" 를 출처 이름으로 짐작하게 된다.

Revision ID: c8d34f1a06b2
Revises: b7c21e4d9f30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d34f1a06b2"
down_revision: str | None = "b7c21e4d9f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tax_contents",
        sa.Column(
            "content_kind",
            sa.Text(),
            nullable=False,
            # 기존 데이터는 전부 법령·행정규칙이다. 그게 사실이다.
            server_default="POLICY",
        ),
    )
    op.create_index("idx_tax_contents_kind", "tax_contents", ["content_kind", "workflow"])


def downgrade() -> None:
    op.drop_index("idx_tax_contents_kind", table_name="tax_contents")
    op.drop_column("tax_contents", "content_kind")
