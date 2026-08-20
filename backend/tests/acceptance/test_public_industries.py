"""업종 필터와 본문 검색.

세무 실무자가 상담 중에 쓰는 경로다. "학원 원장님이 4대보험 물어보는데" 로
찾을 수 있어야 하고, 답이 제목이 아니라 개정 내용에 있어도 찾아져야 한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AuthorityGrade, WorkflowStatus
from app.services import content as content_service
from tests.conftest import requires_db


@requires_db
class TestIndustryFilterAndSearch:
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

    def publish(
        self,
        db,
        make_source,
        make_raw_version,
        *,
        title: str,
        industries: list[str],
        search_text: str = "",
    ):
        version = make_raw_version(make_source(AuthorityGrade.A))
        content = content_service.create_content(
            db, title=title, source_version_ids=[version.id]
        )
        content.workflow = WorkflowStatus.PUBLISHED
        content.industries = industries
        content.search_text = search_text or title
        db.flush()
        return content

    def test_filters_by_industry(self, client, db, make_source, make_raw_version):
        self.publish(db, make_source, make_raw_version, title="학원 건", industries=["EDU"])
        self.publish(db, make_source, make_raw_version, title="음식점 건", industries=["FOOD"])

        body = client.get("/api/v1/public/feed?industries=EDU").json()

        assert [i["title"] for i in body["items"]] == ["학원 건"]

    def test_multiple_industries_are_or_not_and(
        self, client, db, make_source, make_raw_version
    ):
        """둘 다 해당하는 것만 내면 상담 중에 찾으려던 건이 사라진다."""
        self.publish(db, make_source, make_raw_version, title="학원 건", industries=["EDU"])
        self.publish(db, make_source, make_raw_version, title="음식점 건", industries=["FOOD"])

        body = client.get("/api/v1/public/feed?industries=EDU&industries=FOOD").json()

        assert body["total"] == 2

    def test_common_items_are_not_returned_by_specific_industry(
        self, client, db, make_source, make_raw_version
    ):
        """ALL 은 별도 항목이다. 업종을 고르면 그 업종 것만 나온다."""
        self.publish(db, make_source, make_raw_version, title="전 업종", industries=["ALL"])
        self.publish(db, make_source, make_raw_version, title="학원", industries=["EDU"])

        body = client.get("/api/v1/public/feed?industries=EDU").json()

        assert [i["title"] for i in body["items"]] == ["학원"]

    def test_summary_carries_labels(self, client, db, make_source, make_raw_version):
        """분류표를 프론트에 복사해두지 않는다. 이름은 서버가 만든다."""
        self.publish(db, make_source, make_raw_version, title="학원 건", industries=["EDU"])

        item = client.get("/api/v1/public/feed").json()["items"][0]

        assert item["industries"] == ["EDU"]
        assert item["industry_labels"] == ["학원·교육"]

    def test_searches_body_not_just_title(
        self, client, db, make_source, make_raw_version
    ):
        """답은 제목이 아니라 개정 내용에 있다."""
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="국민건강보험법 시행령 (일부개정)",
            industries=["ALL"],
            search_text="국민건강보험법 시행령\n학원 사업장의 4대보험 가입 기준이 변경됩니다",
        )

        body = client.get("/api/v1/public/feed?q=4대보험").json()

        assert body["total"] == 1

    def test_industry_buckets_only_list_what_exists(
        self, client, db, make_source, make_raw_version
    ):
        """0건짜리 필터 버튼을 눌러 빈 화면을 보는 일이 없어야 한다."""
        self.publish(db, make_source, make_raw_version, title="학원", industries=["EDU"])

        buckets = client.get("/api/v1/public/industries").json()

        codes = [b["code"] for b in buckets]
        assert codes == ["EDU"]
        assert buckets[0]["label"] == "학원·교육"
        assert buckets[0]["count"] == 1

    def test_unpublished_items_are_not_counted(
        self, client, db, make_source, make_raw_version
    ):
        content = self.publish(
            db, make_source, make_raw_version, title="초안", industries=["EDU"]
        )
        content.workflow = WorkflowStatus.REVIEW_PENDING
        db.flush()

        buckets = client.get("/api/v1/public/industries").json()

        assert buckets == []
