"""API v1 라우터 집합 (§8.1 기본 경로 /api/v1)."""

from fastapi import APIRouter

from app.api.v1 import analyses, auth, contents, me, public, raw_contents, sources

api_router = APIRouter(prefix="/api/v1")
# 공개 라우터가 먼저다 — 인증 의존성이 붙지 않는 유일한 그룹이라 눈에 띄어야 한다 (ADR-001).
api_router.include_router(public.router)
api_router.include_router(auth.router)
api_router.include_router(sources.router)
api_router.include_router(raw_contents.router)
api_router.include_router(analyses.router)
api_router.include_router(contents.router)
api_router.include_router(me.router)

__all__ = ["api_router"]
