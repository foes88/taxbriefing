"""모델에 보낼 원문 길이. 네트워크 없이 실행된다.

**한도를 넘는 호출은 기다려도 통과하지 않는다.**

무료 티어 분당 한도가 8,000 토큰인데 「법인세법 (2028 시행예정)」
원문이 121,331자였다. 그런데도 429 를 받고 90초씩 세 번 기다린 뒤
실패했다 — 한 건에 4분 30초를 버리고 아무것도 못 얻었다.
"""

from __future__ import annotations

from app.services.ai.runner import MAX_DOC_CHARS, clip


class TestClip:
    def test_short_text_is_untouched(self):
        """대부분은 짧다. 중앙값이 918자다."""
        text = "제1조(목적) 이 법은…"
        assert clip(text) == text

    def test_long_text_is_cut(self):
        assert len(clip("가" * 200_000)) <= MAX_DOC_CHARS + 200

    def test_truncation_is_told_to_the_model(self):
        """잘렸다고 알려주지 않으면 '이것이 개정의 전부' 라고 쓴다."""
        assert "앞부분만" in clip("가" * 200_000)

    def test_reason_section_survives(self):
        """제개정이유가 먼저 사라지면 안 된다 — 요약의 뼈대다.

        법령 원문은 서지정보 → 제개정이유 → 개정문 순인데, 서지정보가
        길면 앞에서 자를 때 정작 필요한 부분이 통째로 밀려난다.
        """
        text = "머리말 " * 3000 + "\n제개정이유\n영세사업자 부담을 덜기 위함\n" + "개정문 " * 3000
        out = clip(text)
        assert "제개정이유" in out
        assert "영세사업자 부담을 덜기 위함" in out

    def test_no_reason_section_falls_back_to_head(self):
        """구획이 없으면 앞에서 자른다. 없는 것을 찾다 빈손으로 오지 않는다."""
        out = clip("첫머리다. " + "본문 " * 5000)
        assert out.startswith("첫머리다.")

    def test_empty(self):
        assert clip("") == ""
