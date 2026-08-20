"""검수 기록은 사실이어야 한다. 네트워크 없이 실행된다.

이 기록은 나중에 "이 건 누가 확인했나" 를 되짚는 **유일한 근거**다.
거기서 거짓이 나오면 나머지 기록도 못 믿게 된다.

실제로 이렇게 남아 있었다.

    303건  "법령 API 서지정보(공포일·시행일·제개정구분) 대조 확인"

전부 배치가 자동으로 승인한 것이다. 사람이 원문을 열어 본 적이 없다.
"""

from __future__ import annotations

from app.bulk_draft import AUTO_REVIEW_NOTE


class TestAutoReviewNote:
    def test_says_no_human_checked(self):
        """가장 중요한 한 문장. 이게 없으면 사람이 본 것으로 읽힌다."""
        assert "사람이 원문과 대조하지 않았습니다" in AUTO_REVIEW_NOTE

    def test_does_not_claim_a_check(self):
        """「대조 확인」 은 클릭 한 번을 검수로 바꿔 적는 말이다."""
        assert "대조 확인" not in AUTO_REVIEW_NOTE
        assert "확인 완료" not in AUTO_REVIEW_NOTE

    def test_says_what_it_did_use(self):
        """무엇을 근거로 통과시켰는지는 정확히 적는다.

        "사람이 안 봤다" 만 적으면 아무 근거 없이 올린 것처럼 읽힌다.
        실제로는 API 응답 필드를 그대로 옮겼고, 그건 지어낸 값이 아니다.
        """
        assert "공포일" in AUTO_REVIEW_NOTE
        assert "시행일" in AUTO_REVIEW_NOTE
