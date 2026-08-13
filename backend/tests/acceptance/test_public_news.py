"""뉴스 탭 공개 API.

가장 중요한 검증: **공식 원문(A·B)이 뉴스 탭으로 새어나가지 않는가.**
반대 방향도 같이 본다 — 검수 안 된 보도가 정책 피드에 섞이지 않는가.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AuthorityGrade
from app.services.ingest import ingest
from tests.conftest import requires_db

NOW = dt.datetime.now(dt.UTC)


@requires_db
class TestPublicNews:
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

    def add_news(
        self,
        db,
        source,
        *,
        title: str = "세제개편안 발표",
        published_at: dt.datetime | None = NOW,
        summary: str = "요약 한 줄",
    ):
        result = ingest(
            db,
            source_id=source.id,
            canonical_url=f"https://news.example/{uuid.uuid4().hex[:8]}",
            title=title,
            publisher=source.display_name,
            raw_body=f"제목: {title}\n\n{summary}",
            published_at=published_at,
        )
        result.version.doc_metadata = {"summary": summary, "full_text_stored": False}
        db.flush()
        return result

    def test_lists_press_items(self, client, db, make_source):
        source = make_source(AuthorityGrade.D)
        self.add_news(db, source, title="부가세 우대 공제율 조정", summary="1.3%에서 1.2%로")

        body = client.get("/api/v1/public/news").json()

        assert body["total"] == 1
        item = body["items"][0]
        assert item["title"] == "부가세 우대 공제율 조정"
        assert item["summary"] == "1.3%에서 1.2%로"
        assert item["authority"] == "D"

    def test_official_sources_never_appear(self, client, db, make_source):
        """A·B 는 공식 원문이다. 검수 경로로만 나가야 하며 뉴스 탭에는 없다."""
        for grade in (AuthorityGrade.A, AuthorityGrade.B):
            self.add_news(db, make_source(grade), title=f"{grade.value}등급 원문")

        body = client.get("/api/v1/public/news").json()

        assert body["total"] == 0

    def test_undated_items_are_excluded(self, client, db, make_source):
        """날짜 없는 기사를 최신순 목록에 올리면 오래된 글을 오늘 소식으로 읽는다.

        제목에 세무 낱말을 넣는 이유 — 기본 목록은 세무 기사만 보여준다.
        여기서 보려는 것은 날짜 규칙이지 주제 규칙이 아니므로, 주제
        필터에 걸리지 않을 제목을 쓴다.
        """
        source = make_source(AuthorityGrade.C)
        self.add_news(db, source, title="부가세 신고 안내 — 날짜 있음", published_at=NOW)
        self.add_news(db, source, title="부가세 신고 안내 — 날짜 없음", published_at=None)

        body = client.get("/api/v1/public/news").json()

        assert [i["title"] for i in body["items"]] == ["부가세 신고 안내 — 날짜 있음"]

    def test_days_window_filters(self, client, db, make_source):
        source = make_source(AuthorityGrade.D)
        self.add_news(
            db, source, title="어제 나온 종합소득세 기사", published_at=NOW - dt.timedelta(days=1)
        )
        self.add_news(
            db,
            source,
            title="작년에 나온 종합소득세 기사",
            published_at=NOW - dt.timedelta(days=300),
        )

        recent = client.get("/api/v1/public/news?days=7").json()
        wide = client.get("/api/v1/public/news?days=365").json()

        assert [i["title"] for i in recent["items"]] == [
            "어제 나온 종합소득세 기사"
        ]
        assert wide["total"] == 2

    def test_sorted_newest_first(self, client, db, make_source):
        source = make_source(AuthorityGrade.D)
        self.add_news(db, source, title="오래된 법인세 기사", published_at=NOW - dt.timedelta(days=5))
        self.add_news(db, source, title="최신 법인세 기사", published_at=NOW - dt.timedelta(hours=1))

        body = client.get("/api/v1/public/news").json()

        assert [i["title"] for i in body["items"]] == ["최신 법인세 기사", "오래된 법인세 기사"]

    def test_query_filters_by_title(self, client, db, make_source):
        source = make_source(AuthorityGrade.D)
        self.add_news(db, source, title="종합소득세 신고 안내")
        self.add_news(db, source, title="법인세 개편 논의")

        body = client.get("/api/v1/public/news?q=법인세").json()

        assert [i["title"] for i in body["items"]] == ["법인세 개편 논의"]

    def test_caveat_is_served_by_api(self, client):
        """문안의 정본은 서버에 있다. 화면에서 조용히 지워지면 안 되는 문구다."""
        body = client.get("/api/v1/public/news").json()

        assert "공식 원문으로 확인되지 않았" in body["caveat"]

    def test_press_items_never_reach_policy_feed(self, client, db, make_source):
        """뉴스는 검수를 거치지 않았으므로 정책 피드에 있어서는 안 된다."""
        self.add_news(db, make_source(AuthorityGrade.D), title="보도 기사")

        body = client.get("/api/v1/public/feed").json()

        assert all(i["title"] != "보도 기사" for i in body["items"])

    def test_off_topic_news_is_hidden_by_default(self, client, db, make_source):
        """세무 낱말이 없는 제목은 기본 목록에서 뺀다.

        세무 전문지 RSS 라도 기업 홍보와 지역 행사가 섞여 들어온다.
        112건 중 39건이 그랬다. 셋 중 하나가 "게임소통학교 성료" 면
        며칠 만에 이 탭을 안 열게 된다.
        """
        source = make_source(AuthorityGrade.C)
        self.add_news(db, source, title="국세청, 종합소득세 신고 안내")
        self.add_news(db, source, title="ㅇㅇ은행, 창립기념일 맞아 적금 출시")

        body = client.get("/api/v1/public/news").json()

        assert [i["title"] for i in body["items"]] == ["국세청, 종합소득세 신고 안내"]
        assert body["total"] == 1

    def test_all_topics_shows_everything(self, client, db, make_source):
        """거른다는 사실을 숨기지 않는다. 되돌릴 수 있어야 한다."""
        source = make_source(AuthorityGrade.C)
        self.add_news(db, source, title="국세청, 종합소득세 신고 안내")
        self.add_news(db, source, title="ㅇㅇ은행, 창립기념일 맞아 적금 출시")

        body = client.get("/api/v1/public/news?all_topics=true").json()

        assert body["total"] == 2
