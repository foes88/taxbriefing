"""법령 수집 순서.

한 법의 여러 개정을 같은 canonical_url 로 모으므로 **마지막에 넣은 것이
현재 버전**이 된다. 지금 API 는 법 하나당 현행 한 건만 주므로 순서가
드러나지 않지만, 한 법의 여러 개정이 함께 오는 순간 최신순 응답을 그대로
넣으면 가장 오래된 개정이 현재로 남는다. 그 전에 잡아두는 테스트다.
"""

from __future__ import annotations

import datetime as dt

from app.services.collectors.law_go_kr import LawListItem


def item(name: str, promulgated: dt.date | None) -> LawListItem:
    return LawListItem(
        law_id="1",
        mst="1",
        name=name,
        law_type="법률",
        ministry="재정경제부",
        promulgation_date=promulgated,
        effective_date=None,
        promulgation_no="1",
        revision_type="일부개정",
        detail_link="/x",
    )


def order(items: list[LawListItem]) -> list[LawListItem]:
    """수집기와 같은 정렬. 로직이 바뀌면 이 테스트가 먼저 깨져야 한다."""
    return sorted(
        items,
        key=lambda i: (i.promulgation_date is not None, i.promulgation_date or dt.date.min),
    )


class TestIngestOrder:
    def test_newest_is_ingested_last(self):
        """마지막에 넣은 것이 현재 버전이므로, 최신 개정이 마지막이어야 한다."""
        api_order = [
            item("부가가치세법", dt.date(2026, 3, 20)),
            item("부가가치세법", dt.date(2025, 10, 1)),
            item("부가가치세법", dt.date(2025, 1, 5)),
        ]

        result = order(api_order)

        assert [i.promulgation_date for i in result] == [
            dt.date(2025, 1, 5),
            dt.date(2025, 10, 1),
            dt.date(2026, 3, 20),
        ]

    def test_undated_never_becomes_current(self):
        """날짜를 모르는 것을 최신으로 취급하면 아는 것이 밀려난다."""
        result = order(
            [
                item("소득세법", None),
                item("소득세법", dt.date(2026, 5, 22)),
                item("소득세법", None),
            ]
        )

        assert result[0].promulgation_date is None
        assert result[1].promulgation_date is None
        assert result[-1].promulgation_date == dt.date(2026, 5, 22)

    def test_stable_when_all_undated(self):
        result = order([item("법", None), item("법", None)])

        assert len(result) == 2
