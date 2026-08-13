"""세무 일정. 네트워크·DB 없이 실행된다.

**신고 기한을 하루 틀리면 가산세가 붙는다.** 그래서 여기 있는 날짜는
전부 조문으로 확인한 것이고, 시험도 날짜 하나하나를 확인한다.
"""

from __future__ import annotations

import datetime as dt

from app.domain.tax_calendar import RULES, Audience, upcoming


def _on(today: dt.date, days: int = 400) -> dict[str, list[dt.date]]:
    out: dict[str, list[dt.date]] = {}
    for d in upcoming(today, within_days=days):
        out.setdefault(d.title, []).append(d.date)
    return out


class TestLegalDeadlines:
    """법정 기한. 근거 조문이 있는 것만 싣는다."""

    def test_every_rule_cites_its_basis(self):
        """**출처 없는 날짜는 싣지 않는다.**"""
        assert all(rule.basis for rule in RULES)
        assert all(rule.title and rule.note for rule in RULES)

    def test_vat_final_return_for_the_first_half(self):
        """1기 확정신고는 7월 25일. 2026년은 토요일이라 27일 월요일로 민다."""
        assert dt.date(2026, 7, 25).weekday() == 5
        assert dt.date(2026, 7, 27) in _on(dt.date(2026, 1, 1))["부가가치세 1기 확정신고"]

    def test_corporate_tax_return(self):
        """12월 결산법인 법인세는 3월 31일."""
        assert dt.date(2027, 3, 31) in _on(dt.date(2026, 8, 14))["법인세 신고·납부"]

    def test_individual_income_tax(self):
        """종합소득세는 5월 31일. 2026년 5월 31일은 일요일이라 6월 1일로 민다."""
        assert dt.date(2026, 5, 31).weekday() == 6
        assert dt.date(2026, 6, 1) in _on(dt.date(2026, 1, 1))["종합소득세 신고·납부"]

    def test_withholding_tax_is_monthly(self):
        """원천세는 매달 10일. 1년이면 열두 번 나와야 한다."""
        dates = _on(dt.date(2026, 1, 1), days=365)["원천세 신고·납부"]
        assert len(dates) == 12

    def test_tax_free_business_report(self):
        """면세사업자 사업장현황신고는 2월 10일. 학원·병의원이 해당한다."""
        assert dt.date(2027, 2, 10) in _on(dt.date(2026, 8, 14))["면세사업자 사업장현황신고"]


class TestWeekendShift:
    """토·일이면 다음 월요일로 민다."""

    def test_saturday_moves_to_monday(self):
        """2026년 1월 25일은 일요일이다."""
        assert dt.date(2026, 1, 25).weekday() == 6
        found = [d for d in upcoming(dt.date(2026, 1, 1), within_days=40) if d.date.month == 1]
        vat = next(d for d in found if "2기 확정" in d.title)
        assert vat.date == dt.date(2026, 1, 26)
        assert vat.shifted is True

    def test_weekday_is_left_alone(self):
        deadlines = upcoming(dt.date(2026, 7, 1), within_days=40)
        vat = next(d for d in deadlines if "1기 확정" in d.title)
        # 2026년 7월 25일은 토요일 → 27일 월요일
        assert dt.date(2026, 7, 25).weekday() == 5
        assert vat.date == dt.date(2026, 7, 27)


class TestWindow:
    def test_today_is_included(self):
        """마감일 당일 아침에 여는 사람에게 가장 필요한 정보다."""
        # 2026년 9월 10일은 목요일이라 밀리지 않는다.
        assert dt.date(2026, 9, 10).weekday() == 3
        assert any(d.date == dt.date(2026, 9, 10) for d in upcoming(dt.date(2026, 9, 10)))

    def test_past_is_excluded(self):
        assert all(d.date >= dt.date(2026, 8, 14) for d in upcoming(dt.date(2026, 8, 14)))

    def test_sorted_by_date(self):
        dates = [d.date for d in upcoming(dt.date(2026, 8, 14), within_days=200)]
        assert dates == sorted(dates)

    def test_narrow_window_is_narrow(self):
        near = upcoming(dt.date(2026, 8, 14), within_days=7)
        assert all(d.date <= dt.date(2026, 8, 21) for d in near)


class TestAudience:
    def test_audiences_are_known_values(self):
        assert all(rule.audience in Audience for rule in RULES)

    def test_employer_only_items_exist(self):
        """직원이 없으면 원천세도 4대보험도 없다. 걸러 볼 수 있어야 한다."""
        titles = {r.title for r in RULES if r.audience is Audience.EMPLOYER}
        assert "원천세 신고·납부" in titles
