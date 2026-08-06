#!/bin/sh
# 컨테이너 기동 스크립트.
#
# 무료 티어는 인스턴스가 1개이므로 기동 시 마이그레이션을 돌려도 안전하다.
# 인스턴스를 여러 개로 늘리면 RUN_MIGRATIONS 를 끄고 배포 파이프라인에서
# 한 번만 실행해야 한다 — 동시에 alembic 을 돌리면 서로 잠금을 문다.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] alembic upgrade head"
    alembic upgrade head
fi

if [ "${RUN_SEED:-0}" = "1" ]; then
    echo "[entrypoint] seeding initial data"
    python -m app.seed || echo "[entrypoint] seed skipped"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
