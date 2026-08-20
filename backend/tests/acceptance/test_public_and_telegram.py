"""공개 열람 API 와 텔레그램 요약 렌더링 (ADR-001).

가장 중요한 검증: **미승인 콘텐츠가 공개 경로로 새어나가지 않는가.**
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AuthorityGrade, LegalStatus, RiskLevel, WorkflowStatus
from app.services import content as content_service
from app.services.render.telegram import BriefingCard, render_card, render_digest
from tests.conftest import requires_db

TODAY = dt.date(2026, 8, 6)


# --------------------------------------------------------------- 텔레그램 렌더링
# DB 없이 실행된다.


class TestTelegramRendering:
    def card(self, **kwargs) -> BriefingCard:
        base = {
            "title": "법인 업무용 차량 비용처리 기준 변경",
            "legal_status": LegalStatus.EFFECTIVE,
            "risk_level": RiskLevel.HIGH,
            "audience": ("법인사업자",),
            "effective_date": dt.date(2026, 9, 1),
            "key_points": ("증빙 및 운행기록 기준이 변경됩니다.",),
            "actions": ("차량별 운행기록과 보험 가입조건을 확인하세요.",),
            "detail_url": "https://taxbriefing.example/article/123",
        }
        base.update(kwargs)
        return BriefingCard(**base)

    def test_card_contains_every_decision_field(self):
        text = render_card(self.card())
        assert "[중요]" in text
        assert "대상: 법인사업자" in text
        assert "상태: 시행 중" in text
        assert "시행일: 2026년 9월 1일" in text
        assert "핵심 내용" in text
        assert "사업자가 할 일" in text
        assert "https://taxbriefing.example/article/123" in text

    def test_missing_effective_date_says_confirm_needed(self):
        """§10.4: 시행일이 없으면 임의 날짜를 쓰지 않는다."""
        text = render_card(self.card(effective_date=None))
        assert "시행일: 확인 필요" in text
        assert "2026년" not in text.split("시행일")[1][:20]

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (LegalStatus.PREANNOUNCED, "시행 확정 아님"),
            (LegalStatus.BILL_PROPOSED, "시행 확정 아님"),
            (LegalStatus.GOV_ANNOUNCED, "시행 확정 아님"),
            (LegalStatus.UNKNOWN, "확정 아님"),
        ],
    )
    def test_unconfirmed_status_carries_warning(self, status, expected):
        """AT-04: 확정되지 않은 정책을 확정처럼 보내지 않는다."""
        text = render_card(self.card(legal_status=status))
        assert expected in text
        assert "시행 중" not in text

    def test_effective_status_has_no_false_caveat(self):
        text = render_card(self.card(legal_status=LegalStatus.EFFECTIVE))
        assert "상태: 시행 중" in text
        assert "확정 아님" not in text

    def test_correction_is_flagged_at_top(self):
        text = render_card(self.card(corrected=True))
        assert text.startswith("[정정]")

    def test_digest_orders_by_importance(self):
        cards = [
            self.card(title="참고 항목", risk_level=RiskLevel.LOW),
            self.card(title="긴급 항목", risk_level=RiskLevel.CRITICAL),
            self.card(title="중요 항목", risk_level=RiskLevel.HIGH),
        ]
        text = render_digest(cards, today=TODAY)
        assert text.index("긴급 항목") < text.index("중요 항목") < text.index("참고 항목")

    def test_empty_digest_says_so_plainly(self):
        text = render_digest([], today=TODAY)
        assert "오늘은 새로 확인된 공식 발표가 없습니다." in text

    def test_long_digest_splits_on_line_boundaries(self):
        from app.services.delivery.channels import TELEGRAM_MAX_CHARS, split_for_telegram

        cards = [self.card(title=f"항목 {i}") for i in range(40)]
        text = render_digest(cards, today=TODAY)
        chunks = split_for_telegram(text)

        assert len(chunks) > 1
        assert all(len(c) <= TELEGRAM_MAX_CHARS for c in chunks)
        # 분할해도 내용이 사라지지 않아야 한다.
        assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")

    def test_short_message_is_not_split(self):
        from app.services.delivery.channels import split_for_telegram

        assert len(split_for_telegram(render_card(self.card()))) == 1


# --------------------------------------------------------------- 공개 API


@pytest.mark.integration
@requires_db
class TestPublicApi:
    @pytest.fixture
    def client(self, db):
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

    def make_content(self, db, make_source, make_raw_version, *, workflow, **kwargs):
        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source, title=kwargs.pop("source_title", "관보 공포문"))
        content = content_service.create_content(
            db,
            title=kwargs.pop("title", "부가가치세 관련 제도 변경"),
            source_version_ids=[version.id],
            legal_status=kwargs.pop("legal_status", LegalStatus.EFFECTIVE),
            risk_level=kwargs.pop("risk_level", RiskLevel.HIGH),
        )
        content.workflow = workflow
        content.one_line_summary = kwargs.pop("summary", "기존 기준이 변경됩니다.")
        for key, value in kwargs.items():
            setattr(content, key, value)
        db.flush()
        return content

    def test_feed_needs_no_authentication(self, client):
        assert client.get("/api/v1/public/feed").status_code == 200

    def test_published_content_appears(self, client, db, make_source, make_raw_version):
        content = self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED
        )
        body = client.get("/api/v1/public/feed").json()
        assert any(item["id"] == str(content.id) for item in body["items"])

    @pytest.mark.parametrize(
        "workflow",
        [
            WorkflowStatus.DETECTED,
            WorkflowStatus.UNVERIFIED,
            WorkflowStatus.SOURCE_CONFIRMED,
            WorkflowStatus.ANALYZED,
            WorkflowStatus.REVIEW_PENDING,
            WorkflowStatus.APPROVED,
            WorkflowStatus.SCHEDULED,
        ],
    )
    def test_unpublished_content_never_leaks(
        self, client, db, make_source, make_raw_version, workflow
    ):
        """검수 전·발송 전 콘텐츠는 공개 경로에 나타나지 않는다."""
        content = self.make_content(db, make_source, make_raw_version, workflow=workflow)

        feed = client.get("/api/v1/public/feed").json()
        assert all(item["id"] != str(content.id) for item in feed["items"])

        detail = client.get(f"/api/v1/public/contents/{content.id}")
        assert detail.status_code == 404

    def test_detail_exposes_official_sources(self, client, db, make_source, make_raw_version):
        content = self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED
        )
        body = client.get(f"/api/v1/public/contents/{content.id}").json()

        assert body["sources"]
        assert body["sources"][0]["authority"] == "A"
        assert body["sources"][0]["url"].startswith("https://")
        assert body["reviewed"] is True

    def test_status_label_and_caveat_are_served(
        self, client, db, make_source, make_raw_version
    ):
        """프론트가 라벨을 다시 만들지 않도록 서버가 표현을 확정해 준다 (§10.4)."""
        content = self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.PUBLISHED,
            legal_status=LegalStatus.PREANNOUNCED,
        )
        body = client.get(f"/api/v1/public/contents/{content.id}").json()

        assert body["status_label"] == "입법·행정예고"
        assert "시행 확정 아님" in body["status_caveat"]
        assert body["is_confirmed"] is False

    def test_keyword_search_filters(self, client, db, make_source, make_raw_version):
        self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.PUBLISHED, title="부가가치세 신고 기준 변경",
        )
        self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.PUBLISHED, title="고용보험 요율 조정",
        )

        hits = client.get("/api/v1/public/feed", params={"q": "부가가치세"}).json()
        assert hits["total"] == 1
        assert "부가가치세" in hits["items"][0]["title"]

    def test_risk_filter(self, client, db, make_source, make_raw_version):
        self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.PUBLISHED, risk_level=RiskLevel.LOW, title="참고 정보",
        )
        self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.PUBLISHED, risk_level=RiskLevel.CRITICAL, title="긴급 정보",
        )

        hits = client.get("/api/v1/public/feed", params={"risk_level": "CRITICAL"}).json()
        assert hits["total"] == 1
        assert hits["items"][0]["title"] == "긴급 정보"

    def test_deadline_filter_excludes_past_and_far(
        self, client, db, make_source, make_raw_version
    ):
        self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED,
            title="임박", application_end=TODAY + dt.timedelta(days=3),
        )
        self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED,
            title="지남", application_end=TODAY - dt.timedelta(days=1),
        )
        self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED,
            title="멀었음", application_end=TODAY + dt.timedelta(days=120),
        )

        hits = client.get(
            "/api/v1/public/feed",
            params={"deadline_within_days": 7, "today": TODAY.isoformat()},
        ).json()
        assert [i["title"] for i in hits["items"]] == ["임박"]

    def test_publish_requires_approval(self, db, make_source, make_raw_version):
        """미승인 고위험 콘텐츠는 게시할 수 없다 (게이트 G6)."""
        from app.core.errors import GateFailedError

        content = self.make_content(
            db, make_source, make_raw_version,
            workflow=WorkflowStatus.APPROVED, risk_level=RiskLevel.HIGH,
        )
        with pytest.raises(GateFailedError) as exc:
            content_service.publish(db, content)
        assert "G6" in exc.value.details["failed_gates"]
        assert content.workflow is not WorkflowStatus.PUBLISHED

    def test_publish_after_approval_makes_it_public(
        self, client, db, make_source, make_raw_version, make_user
    ):
        """승인 → 게시 → 공개 노출까지의 경로."""
        from app.domain.enums import AuthorityGrade, ReviewDecision, Role, SourceRole

        source = make_source(AuthorityGrade.A)
        version = make_raw_version(source, title="관보 공포문")
        content = content_service.create_content(
            db,
            title="부가가치세 관련 제도 변경",
            source_version_ids=[version.id],
            legal_status=LegalStatus.PROMULGATED,
            risk_level=RiskLevel.HIGH,
            roles={version.id: SourceRole.PRIMARY},
        )
        for field in ("legal_status", "affected_users"):
            content_service.add_evidence(
                db, content, field_name=field,
                raw_content_version_id=version.id, locator=f"field:{field}#p1",
            )
        content_service.submit_for_review(db, content)

        reviewer = make_user(Role.REVIEWER)
        content_service.record_review(
            db, content,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.APPROVE,
            review_note="관보 원문 확인 완료",
            checked_source_version_ids=[version.id],
        )

        # 게시 전에는 공개되지 않는다.
        assert client.get(f"/api/v1/public/contents/{content.id}").status_code == 404

        content_service.publish(db, content)
        assert content.workflow is WorkflowStatus.PUBLISHED

        detail = client.get(f"/api/v1/public/contents/{content.id}")
        assert detail.status_code == 200
        assert detail.json()["status_label"] == "공포"
        assert detail.json()["sources"][0]["authority"] == "A"

    def test_tenant_content_is_hidden_from_public_feed(
        self, client, db, make_source, make_raw_version
    ):
        """테넌트 전용 콘텐츠는 공개 피드에 나오지 않는다 (§7.4 D-04, AT-13)."""
        from app.models.tables import Tenant

        tenant = Tenant(name="세무법인 A", slug="firm-a")
        db.add(tenant)
        db.flush()

        content = self.make_content(
            db, make_source, make_raw_version, workflow=WorkflowStatus.PUBLISHED
        )
        content.tenant_id = tenant.id
        db.flush()

        assert all(
            i["id"] != str(content.id)
            for i in client.get("/api/v1/public/feed").json()["items"]
        )
        scoped = client.get(
            "/api/v1/public/feed", params={"tenant_id": str(tenant.id)}
        ).json()
        assert any(i["id"] == str(content.id) for i in scoped["items"])
