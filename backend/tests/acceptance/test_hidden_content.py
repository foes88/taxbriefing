"""무엇이 화면에서 숨겨지는가.

**세율 인상이 세무 브리핑에서 안 보이는 것보다 나쁜 결함은 없다.**

한때 "AI 가 업종을 하나도 못 붙였으면 숨긴다"로 되어 있었고, 그래서
증권거래세율 인상과 부가가치세법 시행규칙 개정이 화면에서 사라졌다.
그 일이 다시 일어나면 이 테스트가 먼저 깨져야 한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AuthorityGrade, WorkflowStatus
from app.domain.industry import Industry
from app.services import content as content_service
from tests.conftest import requires_db


@requires_db
class TestHiddenContent:
    @pytest.fixture
    def client(self, db):
        from app.core.db import get_db
        from app.main import app

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def publish(self, db, make_source, make_raw_version, *, title, industries, classified=True):
        version = make_raw_version(make_source(AuthorityGrade.A))
        content = content_service.create_content(
            db, title=title, source_version_ids=[version.id]
        )
        content.workflow = WorkflowStatus.PUBLISHED
        content.industries = industries
        # search_text 는 분류가 끝났을 때만 채워진다.
        content.search_text = title if classified else None
        db.flush()
        return content

    def titles(self, client) -> list[str]:
        return [i["title"] for i in client.get("/api/v1/public/feed").json()["items"]]

    def test_internal_documents_are_hidden(self, client, db, make_source, make_raw_version):
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="국세청 인사관리규정 (훈령)",
            industries=[Industry.INTERNAL.value],
        )

        assert self.titles(client) == []

    def test_untagged_tax_law_stays_visible(self, client, db, make_source, make_raw_version):
        """업종을 못 붙였다고 숨기지 않는다. 이게 세율 인상을 지웠던 버그다."""
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="증권거래세법 시행규칙 (일부개정)",
            industries=[],
        )

        assert self.titles(client) == ["증권거래세법 시행규칙 (일부개정)"]

    def test_tagged_content_stays_visible(self, client, db, make_source, make_raw_version):
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="부가가치세법 시행규칙 (일부개정)",
            industries=[Industry.ALL.value],
        )

        assert self.titles(client) == ["부가가치세법 시행규칙 (일부개정)"]

    def test_internal_is_not_offered_as_a_filter(
        self, client, db, make_source, make_raw_version
    ):
        """INTERNAL 은 업종이 아니라 숨김 표시다. 필터 버튼으로 나오면 안 된다."""
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="재정경제부 위임전결규정 (훈령)",
            industries=[Industry.INTERNAL.value],
        )
        self.publish(
            db,
            make_source,
            make_raw_version,
            title="소득세법 (일부개정)",
            industries=[Industry.ALL.value],
        )

        codes = [b["code"] for b in client.get("/api/v1/public/industries").json()]

        assert Industry.INTERNAL.value not in codes
        assert codes == [Industry.ALL.value]

    def test_no_change_content_is_marked_not_actionable(
        self, client, db, make_source, make_raw_version
    ):
        """실질 변경이 없는 건은 "먼저 볼 것"에 올리지 않는다.

        화면을 열자마자 읽는 첫 문장이 "사업자에게 실질적인 변경사항은
        없습니다" 였던 적이 있다. 그 자리는 그러면 죽은 자리가 된다.
        """
        from app.models.tables import ContentVersion

        content = self.publish(
            db,
            make_source,
            make_raw_version,
            title="국제경기대회 지원법 관련 고시",
            industries=[Industry.ALL.value],
        )
        version = db.get(ContentVersion, content.current_version_id)
        version.body = {"changes": [], "required_actions": []}
        db.flush()

        item = client.get("/api/v1/public/feed").json()["items"][0]

        assert item["actionable"] is False

    def test_real_change_is_actionable(self, client, db, make_source, make_raw_version):
        from app.models.tables import ContentVersion

        content = self.publish(
            db,
            make_source,
            make_raw_version,
            title="증권거래세법 시행규칙 (일부개정)",
            industries=[Industry.ALL.value],
        )
        version = db.get(ContentVersion, content.current_version_id)
        version.body = {"changes": ["세율이 0에서 5/10,000 으로 인상"]}
        db.flush()

        item = client.get("/api/v1/public/feed").json()["items"][0]

        assert item["actionable"] is True

    def test_model_cannot_hide_content(self):
        """모델이 INTERNAL 을 말해도 받지 않는다.

        숨기는 결정은 눈으로 읽을 수 있는 규칙만 내려야 한다.
        """
        from app.domain.industry import normalize

        assert normalize(["INTERNAL"]) == []
        assert normalize(["INTERNAL", "FOOD"]) == ["FOOD"]
