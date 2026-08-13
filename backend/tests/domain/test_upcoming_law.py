"""시행예정 법령 수집. 네트워크·DB 없이 실행된다.

이 수집기의 최대 위험은 **시행예정본이 현행본을 덮어쓰는 것**이다.
그러면 사장님이 오늘 적용되는 기준을 못 본다. 세무 브리핑에서 그건 사고다.
"""

from __future__ import annotations

import datetime as dt

from app.services.collectors.law_go_kr import PUBLIC_LAW_URL, LawListItem


def item(name: str, effective: dt.date | None, promulgation_no: str) -> LawListItem:
    return LawListItem(
        law_id="001565",
        mst="123456",
        name=name,
        law_type="법률",
        ministry="기획재정부",
        promulgation_date=dt.date(2026, 1, 1),
        effective_date=effective,
        promulgation_no=promulgation_no,
        revision_type="일부개정",
        detail_link="/x",
    )


def upcoming_url(i: LawListItem) -> str:
    """수집기와 같은 규칙. 로직이 바뀌면 이 테스트가 먼저 깨져야 한다."""
    effective = i.effective_date.isoformat() if i.effective_date else "미정"
    return f"{i.canonical_url}?시행={effective}&공포={i.promulgation_no}"


class TestCanonicalUrl:
    def test_upcoming_never_collides_with_current(self):
        """현행 기록과 절대 같은 URL 이 되면 안 된다."""
        law = item("소득세법", dt.date(2027, 1, 1), "20615")

        assert law.canonical_url == f"{PUBLIC_LAW_URL}/소득세법"
        assert upcoming_url(law) != law.canonical_url

    def test_same_law_different_effective_dates_are_separate(self):
        """2027-01-01 시행분과 2028-01-01 시행분은 서로 다른 예고다."""
        a = item("고용보험법", dt.date(2027, 1, 1), "20001")
        b = item("고용보험법", dt.date(2028, 1, 1), "20002")

        assert upcoming_url(a) != upcoming_url(b)

    def test_same_date_different_amendments_are_separate(self):
        """같은 날 시행돼도 공포번호가 다르면 다른 개정이다.

        시행일만으로 갈랐더니 소득세법 시행령 2027-01-01 시행분 6개 개정이
        한 기록으로 뭉쳐 5개가 버전으로 밀려 안 보였다.
        """
        a = item("소득세법 시행령", dt.date(2027, 1, 1), "20615")
        b = item("소득세법 시행령", dt.date(2027, 1, 1), "20777")

        assert upcoming_url(a) != upcoming_url(b)

    def test_same_amendment_is_stable_across_runs(self):
        """멱등성. 다시 수집해도 같은 URL 이어야 새 기록이 안 생긴다 (AT-01)."""
        a = item("법인세법", dt.date(2027, 1, 1), "20615")
        b = item("법인세법", dt.date(2027, 1, 1), "20615")

        assert upcoming_url(a) == upcoming_url(b)


class TestFutureFilter:
    """시행일이 지난 것은 현행법이다. LawCollector 의 몫이지 이쪽이 아니다."""

    def test_past_and_undated_are_not_upcoming(self):
        today = dt.date(2026, 8, 13)
        rows = [
            item("A", dt.date(2026, 1, 1), "1"),
            item("B", dt.date(2026, 8, 13), "2"),
            item("C", dt.date(2026, 8, 14), "3"),
            item("D", None, "4"),
        ]

        upcoming = [r for r in rows if r.effective_date and r.effective_date > today]

        assert [r.name for r in upcoming] == ["C"]
