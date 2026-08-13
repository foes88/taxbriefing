"""심판례 결론 필터.

실무 TIP 화면의 결론 칩(인용·일부인용·기각)이 전부 0 을 표시했다.
결론이 제목 끝 문자열로만 있었고, 수집기 버전에 따라 두 모양이 섞였다.

    …처분의 당부 — 기각
    …환급할 수 있는지 여부 (기각)

화면은 앞의 모양만 찾고 있었다. 그리고 세는 대상이 서버 전체가 아니라
불러온 스무 건이었다 — 시행예정이 "15" 로 떴다가 실제로는 34 건이었던
것과 같은 잘못이다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AuthorityGrade, ContentKind, WorkflowStatus
from app.services import content as content_service
from tests.conftest import requires_db


@requires_db
class TestOutcomeFilter:
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

    def publish(self, db, make_source, make_raw_version, *, title, outcome=None, kind=None):
        version = make_raw_version(make_source(AuthorityGrade.A))
        content = content_service.create_content(
            db, title=title, source_version_ids=[version.id]
        )
        content.workflow = WorkflowStatus.PUBLISHED
        content.content_kind = (kind or ContentKind.TRIBUNAL).value
        content.outcome = outcome
        db.flush()
        return content

    def test_filters_by_outcome(self, client, db, make_source, make_raw_version):
        self.publish(db, make_source, make_raw_version, title="가공세금계산서", outcome="기각")
        self.publish(db, make_source, make_raw_version, title="가지급금 인정이자", outcome="인용")

        body = client.get("/api/v1/public/feed?content_kind=TRIBUNAL&outcome=인용").json()

        assert [i["title"] for i in body["items"]] == ["가지급금 인정이자"]

    def test_total_counts_the_whole_set_not_the_page(
        self, client, db, make_source, make_raw_version
    ):
        """**화면에 있는 것이 아니라 전체를 센다.**

        limit=1 로 불러도 total 은 전체 건수여야 한다. 결론 칩의 숫자가
        그 값이다.
        """
        for i in range(5):
            self.publish(db, make_source, make_raw_version, title=f"기각 {i}", outcome="기각")

        body = client.get("/api/v1/public/feed?content_kind=TRIBUNAL&outcome=기각&limit=1").json()

        assert body["total"] == 5
        assert len(body["items"]) == 1

    def test_outcome_is_exposed_on_the_summary(self, client, db, make_source, make_raw_version):
        """화면이 제목을 파싱하지 않아도 되도록 값으로 내려준다."""
        self.publish(db, make_source, make_raw_version, title="일부만 받아들여진 건", outcome="일부인용")

        item = client.get("/api/v1/public/feed?content_kind=TRIBUNAL").json()["items"][0]

        assert item["outcome"] == "일부인용"

    def test_policy_has_no_outcome(self, client, db, make_source, make_raw_version):
        """법령에는 결론이라는 것이 없다. 빈 문자열이 아니라 null 이다."""
        self.publish(
            db, make_source, make_raw_version, title="소득세법", kind=ContentKind.POLICY
        )

        item = client.get("/api/v1/public/feed").json()["items"][0]

        assert item["outcome"] is None

    def test_unknown_outcome_matches_nothing(self, client, db, make_source, make_raw_version):
        """모르는 값이 와도 조용히 전체를 돌려주지 않는다."""
        self.publish(db, make_source, make_raw_version, title="기각 건", outcome="기각")

        body = client.get("/api/v1/public/feed?content_kind=TRIBUNAL&outcome=승소").json()

        assert body["total"] == 0
