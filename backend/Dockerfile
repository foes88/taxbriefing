# TaxBriefing API
#
# 계약 파일(docs/contracts/)을 런타임에 읽으므로 저장소 루트를 빌드 컨텍스트로 삼는다.
#   docker build -f backend/Dockerfile -t taxbriefing-api .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성만 먼저 설치해 레이어 캐시를 살린다.
COPY backend/pyproject.toml ./backend/
RUN pip install --upgrade pip && pip install ./backend

COPY backend ./backend
# AI 출력 계약을 런타임에 jsonschema 로 직접 적용한다 (§9.4 V1).
COPY docs/contracts ./docs/contracts

WORKDIR /app/backend

# 컨테이너는 비루트로 돈다.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

# 마이그레이션은 배포 파이프라인에서 별도로 돌린다 — 여러 인스턴스가 동시에
# alembic upgrade 를 실행하면 서로 잠금을 물기 때문이다.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
