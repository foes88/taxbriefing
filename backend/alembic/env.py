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
