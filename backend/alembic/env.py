from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base
from app.models.base import DB_SCHEMA

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

#: 스키마를 켰을 때 Alembic 도 그 안에서 움직이게 한다.
#:
#: version_table_schema 를 안 주면 버전표(alembic_version)만 public 에
#: 남는다. 그러면 `tb` 를 통째로 드롭할 때 버전표가 살아남아, 다음
#: upgrade 가 "이미 최신" 이라며 표를 안 만든다.
#:
#: include_schemas 는 autogenerate 가 그 스키마를 훑게 한다. 없으면
#: 이미 있는 표를 "없다" 고 보고 CREATE 를 또 적는다.
SCHEMA_OPTS = (
    {"version_table_schema": DB_SCHEMA, "include_schemas": True} if DB_SCHEMA else {}
)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        **SCHEMA_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # **표를 그 스키마 안에 만들려면 search_path 를 여기서 잡아야 한다.**
        # 마이그레이션 파일들은 `op.create_table("audit_logs", ...)` 처럼
        # 스키마 없이 이름만 쓴다. 그래서 DB_SCHEMA 를 켜도 표는 search_path
        # 대로 public 에 만들어지고, 합치는 쪽(신정)의 같은 이름 표와
        # 부딪혀 멈춘다 — 실제로 audit_logs 에서 멈췄다.
        #
        # 접속 문자열의 `options=-csearch_path=...` 로는 안 된다.
        # Supabase 풀러(PgBouncer/Supavisor)가 그 시작 옵션을 버린다.
        if DB_SCHEMA:
            connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
            # public 을 뒤에 붙인다. 표는 맨 앞(tb)에 만들어지고, 이미
            # 있는 타입·확장 함수(gen_random_uuid 등)는 뒤에서 찾는다.
            # tb 만 두면 그것들을 못 찾아 멈춘다.
            connection.exec_driver_sql(f'SET search_path TO "{DB_SCHEMA}", public')
            # **여기서 커밋해야 한다.** SQLAlchemy 2.0 은 첫 실행에서
            # 트랜잭션을 연다. 그 트랜잭션을 안 닫으면 alembic 이 그 위에서
            # 마이그레이션을 돌리고, 커넥션이 닫힐 때 통째로 롤백된다 —
            # **alembic 은 exit 0 을 내는데 표는 하나도 안 생긴다.**
            # search_path 는 SET(LOCAL 아님)이라 커밋해도 세션에 남는다.
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            **SCHEMA_OPTS,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
