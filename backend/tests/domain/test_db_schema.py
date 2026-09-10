"""표를 담을 스키마. 네트워크 없이 실행된다.

신정 결재시스템에 합칠 때 taxbriefing 표 28개를 `tb` 스키마로 넣는다.
그래야 신정 표(public)와 안 부딪히고, 겹치던 이름(attachments · audit_logs)도
풀린다.

**코드에 박지 않고 환경변수로 둔 이유** — 박으면 지금 도는 Neon 이 그 순간
깨진다. 거기 표는 public 에 있다. 옮기는 날 켠다.
"""

from __future__ import annotations

import subprocess
import sys

CHECK = """
import os, json
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.models import Base

md = Base.metadata
want = os.environ.get("TAXBRIEFING_DB_SCHEMA") or None
out = {
    "schema": md.schema,
    "tables": len(md.tables),
    "wrong_schema": [t.fullname for t in md.tables.values() if t.schema != want],
    "fk_total": sum(len(t.foreign_keys) for t in md.tables.values()),
    # FK 는 코드에 ForeignKey("tenants.id") 처럼 스키마 없이 적혀 있다.
    # 해석이 같은 스키마 안에서 되는지 봐야 한다 — 안 그러면 tb.x 가
    # public.y 를 가리켜 표를 만들 때 깨진다.
    "fk_outside": sum(
        1
        for t in md.tables.values()
        for fk in t.foreign_keys
        if fk.column.table.schema != want
    ),
}
name = "tax_contents" if not want else f"{want}.tax_contents"
out["ddl_head"] = str(
    CreateTable(md.tables[name]).compile(dialect=postgresql.dialect())
).strip().splitlines()[0]
print(json.dumps(out))
"""


def _probe(schema: str | None) -> dict:
    """따로 띄운 파이썬에서 확인한다.

    스키마는 모델을 불러올 때 한 번 박히므로, 같은 프로세스에서 바꿔 가며
    시험할 수 없다.
    """
    import json
    import os

    env = dict(os.environ)
    env.pop("TAXBRIEFING_DB_SCHEMA", None)
    if schema:
        env["TAXBRIEFING_DB_SCHEMA"] = schema
    done = subprocess.run(
        [sys.executable, "-c", CHECK], capture_output=True, text=True, env=env
    )
    if done.returncode:
        raise AssertionError("확인용 프로세스가 죽었습니다:\n" + done.stderr[-800:])
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestSchemaOff:
    """평소 — 환경변수가 없으면 지금까지와 똑같다."""

    def test_tables_stay_in_public(self):
        out = _probe(None)
        assert out["schema"] is None
        assert out["wrong_schema"] == []
        assert out["ddl_head"].startswith("CREATE TABLE tax_contents")


class TestSchemaOn:
    """합치는 날 — `tb` 를 켠다."""

    def test_every_table_moves(self):
        out = _probe("tb")
        assert out["schema"] == "tb"
        assert out["tables"] == 28
        assert out["wrong_schema"] == [], "public 으로 새는 표가 있으면 안 된다"

    def test_foreign_keys_stay_inside(self):
        """FK 가 스키마 밖을 가리키면 표를 만들 때 깨진다.

        코드에는 ForeignKey("tenants.id") 처럼 스키마 없이 적혀 있는데,
        해석은 같은 스키마 안에서 돼야 한다.
        """
        out = _probe("tb")
        assert out["fk_total"] == 52
        assert out["fk_outside"] == 0

    def test_ddl_names_the_schema(self):
        assert _probe("tb")["ddl_head"] == "CREATE TABLE tb.tax_contents ("
