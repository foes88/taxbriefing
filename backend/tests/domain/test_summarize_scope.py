"""AI 요약을 돌릴 대상.

무료 티어의 분당 토큰은 정작 필요한 개정에 써야 하고, 그보다 먼저
**모델이 쓰면 안 되는 글**이 있다.
"""

from __future__ import annotations

from app.domain.enums import ContentKind
from app.summarize import KINDS_WITHOUT_AI, _already_summarized


class TestKindsWithoutAi:
    """심판례·해석례는 요약하지 않는다.

    원문이 이미 [청구인 주장] / [판단 요지] / [판단 이유] 로 갈려 있어
    모델이 다시 쓸 것이 없다. 그런데도 돌렸더니 화자가 바뀌었다.

        사업자는 해당 부가가치세·가산세를 계속 부담해야 합니다.

    그 청구법인 얘기지 읽는 사람 얘기가 아니다.
    """

    def test_tribunal_is_excluded(self):
        assert ContentKind.TRIBUNAL.value in KINDS_WITHOUT_AI

    def test_interpretation_is_excluded(self):
        assert ContentKind.INTERPRETATION.value in KINDS_WITHOUT_AI

    def test_policy_is_included(self):
        """법령은 요약해야 한다. 여기까지 빼면 화면에 법령명만 남는다."""
        assert ContentKind.POLICY.value not in KINDS_WITHOUT_AI

    def test_bill_is_included(self):
        assert ContentKind.BILL.value not in KINDS_WITHOUT_AI


class TestAlreadySummarized:
    def test_empty_changes_still_counts_as_done(self):
        """빈 changes 는 실패가 아니라 정상적인 결과다.

        자구 정리나 인용 조문 번호만 바뀐 개정이 여기 해당한다. 예전에는
        이런 건이 영원히 "아직 안 함" 으로 남아 한 배치 24건 중 22건이
        재처리였다.
        """
        assert _already_summarized({"_ai": True, "changes": []})

    def test_not_run_yet(self):
        assert not _already_summarized({"changes": ["뭔가 있음"]})

    def test_tribunal_body_alone_is_not_a_summary(self):
        """대조표나 심판례 구조가 있다고 요약을 돌린 것은 아니다."""
        assert not _already_summarized({"tribunal": {"sections": [{"label": "주문"}]}})
