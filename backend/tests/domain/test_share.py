"""사장님에게 보낼 짧은 글. 네트워크 없이 실행된다.

여기서 지키는 것은 하나다 — **없는 말을 만들지 않는다.** 이 글은 우리
화면보다 멀리 간다. 세무사무소를 떠나 사장님 카톡으로 들어가고,
거기서 우리는 정정할 방법이 없다.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

from app.domain.share import DISCLAIMER, MAX_LEAD, build_share_text

BODY = {
    "affected_users": [
        "체납자",
        "민사집행법 제246조의2에 따른 생계비계좌에 예치된 예금 등",
    ],
    "required_actions": [
        {"text": "생계비계좌에 해당하는 예금 보유 여부를 확인하세요", "locator": "제41조"}
    ],
}

LONG_SUMMARY = (
    "재생에너지전기저장판매사업자·송전제약발생지역전기공급사업자·분산에너지사업자를 "
    "부대비용 세금계산서 발급 대상에 추가하고, 현금매출명세서에 미디어콘텐츠창작업 "
    "항목을 신설하며, 사업자등록 신청서에 투자조합 여부란을 새로 두었다."
)


def _build(**kw):
    base = dict(
        title="국세징수법 (일부개정)",
        summary="생계비계좌에 예치된 예금은 압류할 수 없도록 명시했습니다.",
        body=BODY,
        effective_date=dt.date(2026, 6, 2),
        source_url="https://www.law.go.kr/법령/국세징수법",
    )
    base.update(kw)
    return build_share_text(**base)


class TestWhatItSays:
    def test_starts_with_the_title(self):
        assert _build().startswith("국세징수법 (일부개정)")

    def test_carries_the_link(self):
        """자른 것은 원문이 받는다. 링크가 없으면 자르는 것이 손실이 된다."""
        assert "원문 https://www.law.go.kr/법령/국세징수법" in _build()

    def test_always_carries_the_disclaimer(self):
        assert DISCLAIMER in _build()

    def test_dates_are_written_the_way_people_say_them(self):
        assert "· 시행: 2026년 6월 2일" in _build()

    def test_takes_the_first_action_only(self):
        assert "· 할 일: 생계비계좌에 해당하는 예금 보유 여부를 확인하세요" in _build()


class TestCutting:
    def test_only_the_first_sentence(self):
        """요약은 250자까지 쓸 수 있다. 실무자에게는 맞고 사장님에게는 아니다."""
        out = _build(summary="첫 문장입니다. 둘째 문장입니다.")
        assert "첫 문장입니다." in out
        assert "둘째 문장입니다" not in out

    def test_a_long_first_sentence_is_cut_at_a_comma(self):
        """글자 수로만 자르면 「현금매출명세서에 미디」 처럼 말이 끊긴다."""
        out = _build(summary=LONG_SUMMARY)
        lead = out.split("\n")[2]
        assert len(lead) <= MAX_LEAD + 2
        assert lead.endswith("…")
        assert "미디" not in lead or "미디어콘텐츠창작업" in lead


class TestWhatItLeavesOut:
    def test_a_missing_field_leaves_no_line(self):
        """모르는 값을 「확인 필요」 로 채우지 않는다.

        받는 사람은 무엇을 확인하라는 건지 모른 채 불안해지기만 한다.
        """
        out = _build(effective_date=None, body={})
        assert "시행" not in out
        assert "대상" not in out
        assert "할 일" not in out
        assert "확인 필요" not in out

    def test_long_targets_are_dropped(self):
        """대상 자리에 사람이 아닌 것이 온다.

        「민사집행법 제246조의2에 따른 생계비계좌에 예치된 예금 등」은
        대상이 아니라 압류가 금지되는 재산이다.
        """
        out = _build()
        assert "· 대상: 체납자" in out
        assert "민사집행법" not in out

    def test_no_targets_means_no_line(self):
        out = _build(body={"affected_users": ["아주 길고 긴 설명이 붙은 대상이라 대상 자리에 못 쓰는 것"]})
        assert "대상" not in out


class TestPreannounced:
    """예고는 「바뀐다」 가 아니라 「바꾸겠다고 한다」 다."""

    def test_says_it_is_not_settled(self):
        out = _build(
            title="부가가치세법 일부개정법률안",
            preannounced=True,
            comment_deadline=dt.date(2026, 8, 20),
            effective_date=None,
        )
        assert "아직 확정된 개정이 아닙니다" in out
        assert "· 의견 마감: 2026년 8월 20일" in out

    def test_no_effective_date_and_no_actions(self):
        """시행일은 아직 없고, 확정 안 된 것에 할 일을 시키지 않는다."""
        out = _build(
            preannounced=True,
            comment_deadline=dt.date(2026, 8, 20),
            effective_date=dt.date(2027, 1, 1),
        )
        assert "시행" not in out
        assert "할 일" not in out


class TestOwnerDigest:
    """아침에 따로 나가는 두 번째 메시지. 이것만 전달하면 된다."""

    def _cards(self, n: int):
        from app.domain.enums import LegalStatus, RiskLevel
        from app.services.render.telegram import BriefingCard

        return [
            BriefingCard(
                title=f"법 {i}",
                legal_status=LegalStatus.PROMULGATED,
                risk_level=RiskLevel.HIGH,
                share_text=f"법 {i}\n\n무엇이 바뀝니다.",
            )
            for i in range(n)
        ]

    def test_disclaimer_appears_once(self):
        """건마다 붙이면 세 건짜리 메시지에 같은 문장이 세 번 나온다."""
        from app.services.render.telegram import render_owner_digest

        out = render_owner_digest(self._cards(3), today=dt.date(2026, 8, 20))
        assert out.count(DISCLAIMER) == 1

    def test_says_how_many_were_left_out(self):
        """조용히 세 건만 보내면 오늘 나온 게 이게 전부라고 읽는다."""
        from app.services.render.telegram import render_owner_digest

        out = render_owner_digest(self._cards(6), today=dt.date(2026, 8, 20))
        assert "이 밖에 3건이 더 있습니다" in out

    def test_no_risk_prefix(self):
        """[중요] 는 실무자가 순서를 정하라고 있는 것이지, 겁을 주라고 있는 게 아니다."""
        from app.services.render.telegram import render_owner_digest

        out = render_owner_digest(self._cards(2), today=dt.date(2026, 8, 20))
        assert "[중요]" not in out
        assert "[긴급]" not in out

    def test_nothing_to_send_is_empty(self):
        """보낼 게 없으면 빈 문자열이다. 빈 껍데기 메시지를 보내지 않는다."""
        from app.services.render.telegram import render_owner_digest

        assert render_owner_digest([], today=dt.date(2026, 8, 20)) == ""


class TestDeadlinePlan:
    """카톡으로 돌릴 「이번 달 챙기실 것」.

    업종별로 못 만든다 — 콘텐츠 325건 중 278건이 업종 미분류이고
    「요식·음식점」 으로 잡힌 것은 0건이다. 골라낼 것이 없는데 골라낸
    척하면 빈 안내가 나간다. 마감 일정은 음식점이든 학원이든 똑같이
    걸리고, 날짜가 법에 정해져 있어 지어낼 여지가 없다.
    """

    DEADLINES: ClassVar[list[dict]] = [
        {"date": "2026-08-31", "title": "법인세 중간예납", "audience_label": "법인"},
        {"date": "2026-09-10", "title": "원천세 신고·납부", "audience_label": "직원 있는 사업장"},
    ]
    TODAY: ClassVar[dt.date] = dt.date(2026, 8, 20)

    def _build(self, **kw):
        from app.domain.share import build_deadline_text

        base = {"today": self.TODAY, "deadlines": self.DEADLINES}
        base.update(kw)
        return build_deadline_text(**base)

    def test_counts_the_days_from_today(self):
        assert "8월 31일 (11일 뒤) 법인세 중간예납" in self._build()

    def test_today_and_tomorrow_are_said_in_words(self):
        rows = [{"date": "2026-08-20", "title": "가", "audience_label": "법인"},
                {"date": "2026-08-21", "title": "나", "audience_label": "법인"}]
        out = self._build(deadlines=rows)
        assert "(오늘) 가" in out
        assert "(내일) 나" in out

    def test_who_it_applies_to_is_written_not_filtered(self):
        """거르지 않는다.

        「나는 법인이 아니니까 이건 아니구나」 를 사장님이 직접 확인하는
        편이, 우리가 잘못 걸러서 하나를 빠뜨리는 것보다 낫다.
        """
        out = self._build()
        assert "대상: 법인" in out
        assert "대상: 직원 있는 사업장" in out

    def test_revision_suffix_is_stripped_from_law_names(self):
        """제목을 그대로 쓰면 같은 날짜가 두 번 나온다.

            · 고용보험법 (일부개정, 2026-09-18 시행예정) — 2026년 9월 18일 시행
        """
        out = self._build(
            changes=[
                {
                    "title": "고용보험법 (일부개정, 2026-09-18 시행예정)",
                    "effective_date": "2026-09-18",
                }
            ]
        )
        assert "· 고용보험법 — 2026년 9월 18일 시행" in out
        assert "시행예정)" not in out

    def test_always_says_it_may_differ(self):
        """과세유형·결산월·반기납부에 따라 기한이 다르다. 그걸 안 적으면 거짓이다."""
        assert "담당자에게 확인하세요" in self._build()

    def test_nothing_to_say_is_empty(self):
        """빈 껍데기를 만들지 않는다."""
        assert self._build(deadlines=[], changes=[]) == ""
