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
from sqlalchemy import select

from app.domain.enums import AuthorityGrade, ContentKind, WorkflowStatus
from app.services import content as content_service
from tests.conftest import requires_db


@requires_db
class TestOutcomeFilter:
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


@requires_db
class TestStatusByKind:
    """정책 상태는 종류를 가려서 붙인다.

    심판례에 "상태 확인 필요 · 확정 아님" 이 붙어 있었다. 확인이 필요한
    게 아니라 확인할 것이 없고, 확정이 아닌 게 아니라 이미 확정된
    결정이다. 세 줄 다 틀렸다.
    """

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

    def publish(self, db, make_source, make_raw_version, *, kind):
        version = make_raw_version(make_source(AuthorityGrade.A))
        content = content_service.create_content(
            db, title=f"{kind.value} 건", source_version_ids=[version.id]
        )
        content.workflow = WorkflowStatus.PUBLISHED
        content.content_kind = kind.value
        db.flush()
        return content

    def _item(self, client, kind):
        body = client.get(f"/api/v1/public/feed?content_kind={kind.value}").json()
        return body["items"][0]

    def test_tribunal_has_no_policy_status(self, client, db, make_source, make_raw_version):
        self.publish(db, make_source, make_raw_version, kind=ContentKind.TRIBUNAL)

        item = self._item(client, ContentKind.TRIBUNAL)

        assert item["status_label"] is None
        assert item["status_caveat"] is None
        assert item["is_confirmed"] is False

    def test_interpretation_has_no_policy_status(
        self, client, db, make_source, make_raw_version
    ):
        self.publish(db, make_source, make_raw_version, kind=ContentKind.INTERPRETATION)

        assert self._item(client, ContentKind.INTERPRETATION)["status_label"] is None

    def test_bill_keeps_its_status(self, client, db, make_source, make_raw_version):
        """법안에는 발의·통과라는 진행이 실제로 있다. 여기까지 지우면 안 된다."""
        self.publish(db, make_source, make_raw_version, kind=ContentKind.BILL)

        assert self._item(client, ContentKind.BILL)["status_label"] is not None

    def test_policy_keeps_its_status(self, client, db, make_source, make_raw_version):
        self.publish(db, make_source, make_raw_version, kind=ContentKind.POLICY)

        assert self._item(client, ContentKind.POLICY)["status_label"] is not None


@requires_db
class TestBulkDraftIdempotency:
    """같은 원문에서 콘텐츠가 두 번 만들어지면 안 된다.

    처음에는 **제목**으로 걸렀다. 국회 의안은 여러 의원이 각자 같은
    이름으로 발의해서 서로 다른 40개 법안이 11개로 뭉쳤다.

    그래서 **원문 버전**으로 바꿨더니 이번엔 반대로 하나가 둘이 됐다.
    법제처가 같은 법령을 다시 내려주며 본문이 조금 달라지면 새 버전이
    생기는데, 그때마다 콘텐츠가 하나 더 만들어졌다. 56묶음 57건이었다.

    원문 하나가 콘텐츠 하나다. 그게 실제 관계다.
    """

    def test_new_version_of_same_raw_does_not_create_a_second_content(
        self, db, make_source, make_raw_version
    ):
        import datetime as dt

        from app import bulk_draft
        from app.models.tables import RawContent

        source = make_source(AuthorityGrade.A)
        url = "https://www.law.go.kr/법령/소득세법 시행규칙"
        first = make_raw_version(source, url=url)
        raw = db.get(RawContent, first.raw_content_id)
        raw.published_at = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
        db.flush()

        stats = bulk_draft.run(
            db, months=None, year=None, limit=10, auto_approve=False,
            today=dt.date(2026, 8, 13),
        )
        assert stats["초안"] == 1

        # 같은 주소 = 같은 원문. 본문만 달라졌으니 새 버전이 생긴다.
        second = make_raw_version(source, url=url, body="본문이 조금 달라졌다")
        assert second.raw_content_id == raw.id
        assert second.id != first.id

        again = bulk_draft.run(
            db, months=None, year=None, limit=10, auto_approve=False,
            today=dt.date(2026, 8, 13),
        )
        assert again["초안"] == 0, "같은 원문에서 콘텐츠가 또 만들어졌다"


@requires_db
class TestBillStatusRefresh:
    """법안은 한 번 만들고 끝이 아니다.

    국회에서 심사가 진행되면 PROC_RESULT 가 바뀐다. "이미 있으면 건너뜀"
    만 하면 통과한 법안이 영원히 "발의" 로 남는다.

    통과 안 된 것이 "통과" 로 보이면 안 해도 될 준비를 하고, 통과한 것이
    "발의" 로 남으면 해야 할 준비를 놓친다. 뒤쪽이 더 나쁘다 — 모르는
    사이에 시행일이 온다.
    """

    def _collect_once(self, db, source, make_raw_version, *, url, proc_result, status):
        import datetime as dt

        from app import bulk_draft
        from app.models.tables import RawContent

        version = make_raw_version(source, url=url, title="소득세법 일부개정법률안")
        raw = db.get(RawContent, version.raw_content_id)
        raw.published_at = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)
        version.doc_metadata = {
            "content_kind": "BILL",
            "proposer": "홍길동의원 등 10인",
            "committee": "재정경제기획위원회",
            "proposed_at": "2026-08-01",
            "proc_result": proc_result,
            "legal_status": status,
        }
        db.flush()
        return bulk_draft.run(
            db, months=None, year=None, limit=10, auto_approve=False,
            today=dt.date(2026, 8, 14),
        )

    def test_passed_bill_stops_saying_proposed(self, db, make_source, make_raw_version):
        from app.domain.enums import LegalStatus
        from app.models.tables import TaxContent

        source = make_source(AuthorityGrade.A)
        url = "https://likms.assembly.go.kr/bill/2220444"

        first = self._collect_once(
            db, source, make_raw_version, url=url, proc_result="", status="BILL_PROPOSED"
        )
        assert first["초안"] == 1

        content = db.execute(select(TaxContent)).scalars().one()
        assert content.legal is LegalStatus.BILL_PROPOSED

        # 같은 법안을 다시 수집한다. 이번에는 본회의를 통과했다.
        again = self._collect_once(
            db, source, make_raw_version, url=url,
            proc_result="원안가결", status="ASSEMBLY_PASSED",
        )
        assert again["초안"] == 0, "같은 법안에서 콘텐츠가 또 만들어졌다"
        assert again["상태 갱신"] == 1

        db.refresh(content)
        assert content.legal is LegalStatus.ASSEMBLY_PASSED
        assert "발의" in (content.one_line_summary or "")

    def test_unchanged_status_is_left_alone(self, db, make_source, make_raw_version):
        """바뀐 게 없으면 건드리지 않는다.

        매번 updated_at 을 건드리면 목록 정렬(최신순)이 흔들려서, 아무
        일도 없던 법안이 오늘 뭔가 생긴 것처럼 맨 위로 올라온다.
        """
        source = make_source(AuthorityGrade.A)
        url = "https://likms.assembly.go.kr/bill/2220456"

        self._collect_once(
            db, source, make_raw_version, url=url, proc_result="", status="BILL_PROPOSED"
        )
        again = self._collect_once(
            db, source, make_raw_version, url=url, proc_result="", status="BILL_PROPOSED"
        )
        assert again["상태 갱신"] == 0
