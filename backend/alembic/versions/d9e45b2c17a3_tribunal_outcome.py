"""심판례 결론을 값으로 둔다

실무 TIP 화면의 결론 필터(인용·일부인용·기각)가 전부 0 을 표시했다.

결론이 제목 끝에 문자열로만 있었고, 그마저 수집기 버전에 따라 두 가지
모양이 섞여 있었기 때문이다.

    …처분의 당부 — 기각
    …환급할 수 있는지 여부 (기각)

화면은 앞의 모양만 찾고 있었다. 정규식을 둘 다 받게 고칠 수도 있지만,
그러면 세 번째 모양이 생겼을 때 또 조용히 0 이 된다. 그리고 결론은
목록을 걸러 낼 값인데 제목 안에 묻혀 있으면 서버가 못 거른다 — 화면에
불러온 스무 건 안에서만 세게 되고, 실제 건수와 어긋난다.

시행예정 건수가 "15" 로 떴다가 실제로는 34 건이었던 것과 같은 종류의
잘못이다. 세는 대상이 전체가 아니라 화면에 있는 것이었다.

Revision ID: d9e45b2c17a3
Revises: c8d34f1a06b2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e45b2c17a3"
down_revision: str | None = "c8d34f1a06b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tax_contents", sa.Column("outcome", sa.Text(), nullable=True))
    # 심판례만 값을 갖는다. 법령에는 결론이라는 것이 없다.
    op.create_index(
        "idx_tax_contents_outcome",
        "tax_contents",
        ["outcome"],
        postgresql_where=sa.text("outcome IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tax_contents_outcome", table_name="tax_contents")
    op.drop_column("tax_contents", "outcome")
