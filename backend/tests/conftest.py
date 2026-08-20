"""테스트 픽스처.

도메인 테스트(tests/domain, tests/contract)는 DB 없이 실행된다.
인수 테스트(tests/acceptance)는 PostgreSQL 이 필요하며,
TAXBRIEFING_TEST_DATABASE_URL 이 없으면 skip 된다.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import Iterator

import pytest

os.environ.setdefault("TAXBRIEFING_ENVIRONMENT", "test")
# HS256 은 32바이트 이상 키를 요구한다 (RFC 7518 §3.2).
os.environ.setdefault(
    "TAXBRIEFING_JWT_SECRET", "test-secret-not-for-production-0123456789abcdef"
)

TEST_DB_URL = os.environ.get(
    "TAXBRIEFING_TEST_DATABASE_URL",
    "postgresql+psycopg://taxbriefing:taxbriefing@localhost:5433/taxbriefing_test",
)
os.environ.setdefault("TAXBRIEFING_DATABASE_URL", TEST_DB_URL)

# AI 제공자는 테스트에서 **항상 스텁이다.** setdefault 가 아니라 덮어쓴다.
#
# `.env` 에 실제 제공자를 넣어두면 AI 경로를 지나는 인수 테스트가 조용히
# 네트워크를 타고, 무료 한도에 걸리는 날 테스트가 빨갛게 된다. 실제로 그랬다 —
# 모델을 groq 로 바꾼 순간 AT-05 가 5분 걸려 실패했다.
# 어떤 개발자의 .env 냐에 따라 결과가 갈리는 테스트는 테스트가 아니다.
os.environ["TAXBRIEFING_AI_PROVIDER"] = "stub"
os.environ["TAXBRIEFING_AI_MODEL"] = "stub-analysis-v1"


def _database_available(url: str) -> bool:
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


DB_AVAILABLE = _database_available(TEST_DB_URL)

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason=(
        "PostgreSQL 이 필요합니다. `docker compose up -d db` 후 "
        "TAXBRIEFING_TEST_DATABASE_URL 을 설정하세요."
    ),
)


@pytest.fixture(scope="session")
def engine():
    if not DB_AVAILABLE:
        pytest.skip("test database unavailable")
    from sqlalchemy import create_engine

    from app.models import Base

    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator:
    """테스트마다 롤백되는 세션.

    바깥 트랜잭션에 세션을 묶어두고 끝나면 롤백한다. 테스트 간 데이터가 새지 않는다.
    """
    from sqlalchemy.orm import Session

    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


# --------------------------------------------------------------------- 데이터 헬퍼


@pytest.fixture
def now() -> dt.datetime:
    return dt.datetime(2026, 8, 6, 0, 0, tzinfo=dt.UTC)


@pytest.fixture
def make_source(db):
    from app.domain.enums import AuthorityGrade
    from app.models.tables import Source

    def _make(
        authority: AuthorityGrade = AuthorityGrade.A,
        display_name: str | None = None,
        domain: str | None = None,
    ) -> Source:
        suffix = uuid.uuid4().hex[:8]
        source = Source(
            display_name=display_name or f"출처-{authority.value}-{suffix}",
            canonical_domain=domain or f"{suffix}.go.kr",
            authority=authority,
            collector_type="MANUAL",
        )
        db.add(source)
        db.flush()
        return source

    return _make


@pytest.fixture
def make_raw_version(db):
    """원문과 v1 을 한 번에 만든다."""
    from app.services.ingest import ingest

    def _make(source, *, title: str = "원문 제목", body: str = "본문 내용입니다.", url: str | None = None):
        result = ingest(
            db,
            source_id=source.id,
            canonical_url=url or f"https://{source.canonical_domain}/board/{uuid.uuid4().hex[:8]}",
            title=title,
            publisher=source.display_name,
            raw_body=body,
        )
        return result.version

    return _make


@pytest.fixture
def make_user(db):
    from app.core.security import hash_password
    from app.domain.enums import Role
    from app.models.tables import User

    def _make(role: Role = Role.EDITOR, email: str | None = None, tenant_id=None) -> User:
        user = User(
            email=email or f"{uuid.uuid4().hex[:8]}@example.test",
            role=role.value,
            tenant_id=tenant_id,
            password_hash=hash_password("test-password-1234"),
            display_name=role.value,
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture(autouse=True)
def _clear_public_cache():
    """공개 응답 캐시를 시험마다 비운다.

    캐시를 시험에서 꺼 버리면 그 미들웨어가 한 번도 안 돌아 보고, 그러면
    운영에서만 나는 버그를 시험이 못 잡는다. 끄지 않고 비운다 — 미들웨어는
    그대로 지나가되 앞 시험이 담아 둔 값은 안 보인다.

    안 비웠더니 16건이 깨졌다. 데이터를 넣고 같은 주소를 부르는 시험들이
    앞 시험의 응답을 받아 갔다.
    """
    from app.main import _response_cache

    _response_cache.clear()
    yield
    _response_cache.clear()
