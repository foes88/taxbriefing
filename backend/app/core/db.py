"""데이터베이스 세션 (§6.1 PostgreSQL 16)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

#: **왕복 한 번에 393ms 다.**
#:
#: DB 는 미국(Neon us-east-2)에 있고 화면을 여는 사람은 한국에 있다.
#: 쿼리를 몇 번 던지느냐가 그대로 초 단위로 화면에 나온다. 목록 한 번
#: 여는 데 이렇게 쓰고 있었다.
#:
#:     +201ms  checkout   연결 살아 있나 확인 (pool_pre_ping)
#:     +404ms  조회
#:     +205ms  조회
#:     +200ms  checkin    ROLLBACK
#:
#: 실제로 자료를 읽는 건 600ms 인데 400ms 가 껍데기였다.
engine = create_engine(
    _settings.database_url,
    # 확인 핑은 켜 둔다. Neon 은 놀고 있는 연결을 끊고, 그때 죽은 연결을
    # 집으면 화면에 500 이 뜬다. 200ms 를 아끼려고 그 위험을 지지 않는다.
    #
    # 대신 **연결을 오래 붙들고 재사용한다.** 기본값은 놀던 연결을 금방
    # 버리는데, 그러면 다음 요청이 TLS 악수부터 다시 한다 — 처음 붙을 때
    # 3.2초가 걸렸다. 30분을 잡아 두면 하루 종일 쓰는 사무실에서는
    # 사실상 늘 살아 있는 연결을 쓴다.
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    pool_pre_ping=True,
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

#: 읽기 전용 세션.
#:
#: 공개 화면은 아무것도 쓰지 않는다. 그런데 세션을 닫을 때마다 ROLLBACK
#: 이 나갔고, 그게 왕복 한 번이라 200ms 였다. 되돌릴 것이 없는데 되돌리는
#: 데 시간을 쓴 셈이다.
#:
#: AUTOCOMMIT 으로 열면 트랜잭션 자체가 시작되지 않아 되돌릴 것도 없다.
#: 읽기만 하는 곳에서만 쓴다 — 쓰는 경로에서 이걸 쓰면 한 요청 안의
#: 여러 변경이 따로 확정되어, 중간에 실패했을 때 반쪽만 남는다.
ReadSessionLocal = sessionmaker(
    bind=engine.execution_options(isolation_level="AUTOCOMMIT"),
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    """FastAPI 의존성. 요청 단위 트랜잭션 경계."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_read_db() -> Iterator[Session]:
    """읽기 전용 FastAPI 의존성. 트랜잭션을 열지 않는다.

    커밋도 롤백도 하지 않는다 — 할 것이 없다.
    """
    session = ReadSessionLocal()
    try:
        yield session
    finally:
        session.close()
