"""API 계층 통합 테스트 — RBAC·멱등성·오류규약이 HTTP 경로에서 실제로 강제되는지 (§12.2, §8.1).

도메인 테스트가 통과해도 라우터가 잘못된 의존성을 쓰면 권한이 새어나간다.
그래서 같은 규칙을 HTTP 계층에서 한 번 더 확인한다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.domain.enums import AuthorityGrade, Role
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]


@pytest.fixture
def client(db):
    from app.core.db import get_db, get_read_db
    from app.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    # 공개 화면은 읽기 전용 세션을 쓴다(ReadSession). 하나만
    # 갈아끼우면 그쪽이 진짜 DB 로 새서 목록이 통째로 비어 보인다.
    app.dependency_overrides[get_read_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def token(user) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id=user.id, role=Role(user.role), tenant_id=user.tenant_id
        )
    }


def key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


class TestAuthentication:
    def test_missing_token_is_401(self, client):
        r = client.get("/api/v1/sources")
        assert r.status_code == 401
        assert r.json()["code"] == "UNAUTHORIZED"

    def test_malformed_token_is_401(self, client):
        r = client.get("/api/v1/sources", headers={"Authorization": "Bearer nonsense"})
        assert r.status_code == 401

    def test_error_response_carries_trace_id(self, client):
        r = client.get("/api/v1/sources")
        body = r.json()
        assert set(body) == {"code", "message", "details", "trace_id"}
        assert body["trace_id"]
        assert r.headers["X-Trace-Id"]

    def test_login_returns_token(self, client, make_user):
        user = make_user(Role.EDITOR)
        r = client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "test-password-1234"},
        )
        assert r.status_code == 200
        assert r.json()["access_token"]
        assert r.json()["role"] == "EDITOR"

    def test_wrong_password_is_401(self, client, make_user):
        user = make_user(Role.EDITOR)
        r = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "wrong"}
        )
        assert r.status_code == 401


class TestRbacEnforcement:
    def test_editor_cannot_create_source(self, client, make_user):
        """출처 등록은 SYSTEM_ADMIN 전용이다."""
        editor = make_user(Role.EDITOR)
        r = client.post(
            "/api/v1/sources",
            headers={**token(editor), **key()},
            json={
                "display_name": "국세청",
                "canonical_domain": "nts.go.kr",
                "authority": "B",
                "collector_type": "HTML",
            },
        )
        assert r.status_code == 403
        assert r.json()["code"] == "FORBIDDEN"
        assert "SYSTEM_ADMIN" in r.json()["details"]["required_roles"]

    def test_admin_can_create_source(self, client, make_user):
        admin = make_user(Role.SYSTEM_ADMIN)
        r = client.post(
            "/api/v1/sources",
            headers={**token(admin), **key()},
            json={
                "display_name": "국가법령정보센터",
                "canonical_domain": "law.go.kr",
                "authority": "A",
                "collector_type": "API",
            },
        )
        assert r.status_code == 201
        assert r.json()["authority"] == "A"

    def test_system_admin_cannot_review(
        self, client, db, make_user, make_source, make_raw_version
    ):
        """§12.2: SYSTEM_ADMIN 도 검수 책임을 대체할 수 없다."""
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="테스트 콘텐츠", source_version_ids=[version.id]
        )
        admin = make_user(Role.SYSTEM_ADMIN)

        r = client.post(
            f"/api/v1/contents/{content.id}/reviews",
            headers={**token(admin), **key()},
            json={
                "decision": "APPROVE",
                "review_note": "확인",
                "checked_source_version_ids": [str(version.id)],
            },
        )
        assert r.status_code == 403

    def test_campaign_manager_cannot_review(
        self, client, db, make_user, make_source, make_raw_version
    ):
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="테스트 콘텐츠", source_version_ids=[version.id]
        )
        manager = make_user(Role.CAMPAIGN_MANAGER)

        r = client.post(
            f"/api/v1/contents/{content.id}/reviews",
            headers={**token(manager), **key()},
            json={
                "decision": "APPROVE",
                "review_note": "확인",
                "checked_source_version_ids": [str(version.id)],
            },
        )
        assert r.status_code == 403

    def test_subscriber_cannot_read_admin_endpoints(self, client, make_user):
        subscriber = make_user(Role.SUBSCRIBER)
        assert client.get("/api/v1/sources", headers=token(subscriber)).status_code == 403


class TestIdempotencyHeader:
    def test_write_without_key_is_rejected(self, client, make_user):
        admin = make_user(Role.SYSTEM_ADMIN)
        r = client.post(
            "/api/v1/sources",
            headers=token(admin),
            json={
                "display_name": "x",
                "canonical_domain": "x.go.kr",
                "authority": "B",
                "collector_type": "RSS",
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "VALIDATION_FAILED"

    def test_same_key_replays_first_response(self, client, make_user):
        """AT-09 의 HTTP 경로: 같은 키 재요청은 새 객체를 만들지 않는다."""
        admin = make_user(Role.SYSTEM_ADMIN)
        headers = {**token(admin), **key()}
        payload = {
            "display_name": "전자관보",
            "canonical_domain": "gwanbo.go.kr",
            "authority": "A",
            "collector_type": "HTML",
        }

        first = client.post("/api/v1/sources", headers=headers, json=payload)
        second = client.post("/api/v1/sources", headers=headers, json=payload)

        assert first.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert _count_sources(client, admin, "gwanbo.go.kr") == 1

    def test_same_key_different_body_is_409(self, client, make_user):
        admin = make_user(Role.SYSTEM_ADMIN)
        headers = {**token(admin), **key()}

        client.post(
            "/api/v1/sources",
            headers=headers,
            json={
                "display_name": "A기관",
                "canonical_domain": "a.go.kr",
                "authority": "A",
                "collector_type": "API",
            },
        )
        r = client.post(
            "/api/v1/sources",
            headers=headers,
            json={
                "display_name": "B기관",
                "canonical_domain": "b.go.kr",
                "authority": "B",
                "collector_type": "API",
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "CONFLICT"


def _count_sources(client, admin, domain: str) -> int:
    rows = client.get("/api/v1/sources", headers=token(admin)).json()
    return sum(1 for r in rows if r["canonical_domain"] == domain)


class TestContentFlowOverHttp:
    def test_news_only_content_cannot_submit_review(
        self, client, db, make_user, make_source, make_raw_version
    ):
        """AT-03 의 HTTP 경로."""
        from app.services import content as content_service

        source = make_source(AuthorityGrade.D)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="뉴스 기반", source_version_ids=[version.id]
        )
        editor = make_user(Role.EDITOR)

        r = client.post(
            f"/api/v1/contents/{content.id}/submit-review",
            headers={**token(editor), **key()},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "GATE_FAILED"
        assert "G1" in r.json()["details"]["failed_gates"]

    def test_gates_endpoint_explains_blockers(
        self, client, db, make_user, make_source, make_raw_version
    ):
        from app.services import content as content_service

        source = make_source(AuthorityGrade.D)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="뉴스 기반", source_version_ids=[version.id]
        )
        viewer = make_user(Role.VIEWER)

        r = client.get(f"/api/v1/contents/{content.id}/gates", headers=token(viewer))
        assert r.status_code == 200
        body = r.json()
        assert body["can_approve"] is False
        g1 = next(x for x in body["results"] if x["gate"] == "G1")
        assert g1["consequence"] == "BLOCK_APPROVAL"
        assert g1["reason"]

    def test_optimistic_lock_conflict_is_409(
        self, client, db, make_user, make_source, make_raw_version
    ):
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="원본 제목", source_version_ids=[version.id]
        )
        editor = make_user(Role.EDITOR)

        r = client.patch(
            f"/api/v1/contents/{content.id}",
            headers={**token(editor), "If-Match": "999"},
            json={"title": "새 제목"},
        )
        assert r.status_code == 409

    def test_unknown_patch_field_is_rejected(
        self, client, db, make_user, make_source, make_raw_version
    ):
        """A-06: additionalProperties 를 열어두지 않는다."""
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="제목", source_version_ids=[version.id]
        )
        editor = make_user(Role.EDITOR)

        r = client.patch(
            f"/api/v1/contents/{content.id}",
            headers=token(editor),
            json={"source_confidence": 100},
        )
        assert r.status_code == 422

    def test_content_sources_are_listed_for_review(
        self, client, db, make_user, make_source, make_raw_version
    ):
        """AT-12: 검수자가 '무엇을 확인했는지' 고르려면 목록이 먼저 보여야 한다.

        이 엔드포인트가 없어서 관리자 화면이 빈 배열을 보냈고, 승인이 항상 실패했다.
        """
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source, title="관보 공포문")
        content = content_service.create_content(
            db, title="테스트 콘텐츠", source_version_ids=[version.id]
        )
        viewer = make_user(Role.VIEWER)

        r = client.get(f"/api/v1/contents/{content.id}/sources", headers=token(viewer))
        assert r.status_code == 200

        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["raw_content_version_id"] == str(version.id)
        assert rows[0]["authority"] == "A"
        assert rows[0]["role"] == "PRIMARY"
        assert rows[0]["canonical_url"].startswith("https://")

    def test_approve_without_checked_sources_is_rejected(
        self, client, db, make_user, make_source, make_raw_version
    ):
        """빈 배열로 승인하면 422 여야 한다. 화면이 이 규칙을 어기고 있었다."""
        from app.services import content as content_service

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source)
        content = content_service.create_content(
            db, title="테스트", source_version_ids=[version.id]
        )
        reviewer = make_user(Role.REVIEWER)

        r = client.post(
            f"/api/v1/contents/{content.id}/reviews",
            headers={**token(reviewer), **key()},
            json={
                "decision": "APPROVE",
                "review_note": "확인",
                "checked_source_version_ids": [],
            },
        )
        # 스키마(minItems=1)에서 걸리거나 서비스에서 걸리거나, 어느 쪽이든 거부돼야 한다.
        assert r.status_code == 422

    def test_health_needs_no_auth(self, client):
        assert client.get("/health").status_code == 200
