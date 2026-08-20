"""밖에서 받아 온 분류를 넣을 때. 네트워크 없이 실행된다.

여기서 지키는 것은 하나다 — **밖에서 온 값을 믿지 않는다.** 조용히
버리면 그 건은 "판단해보니 무관" 으로 남아 화면에서 사라진다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.classify_offline import _judgement_rules, _read_answer, _validate
from app.services.ai.classify import _taxonomy_block

MAP = {"A1": "11111111-1111-1111-1111-111111111111", "A2": "22222222-2222-2222-2222-222222222222"}


class TestValidate:
    def test_good_answer_passes(self):
        cleaned, bad, unknown = _validate({"A1": ["ALL"], "A2": ["FOOD"]}, MAP)
        assert cleaned == {"A1": ["ALL"], "A2": ["FOOD"]}
        assert not bad and not unknown

    def test_unknown_code_stops_everything(self):
        """조용히 버리지 않는다. 버리면 그 건이 화면에서 사라진다."""
        cleaned, bad, _ = _validate({"A1": ["ALL"], "A2": ["CAFE"]}, MAP)
        assert bad and "CAFE" in bad[0]
        assert "A2" not in cleaned

    def test_internal_is_refused(self):
        """INTERNAL 은 규칙만 붙이는 숨김 표시다.

        모델이 붙이면 진짜 세법이 사라진다 — 증권거래세율 인상이
        그렇게 사라진 적이 있다.
        """
        _, bad, _ = _validate({"A1": ["INTERNAL"]}, MAP)
        assert bad and "INTERNAL" in bad[0]

    def test_lowercase_is_accepted(self):
        """붙여 넣다 보면 소문자로 온다. 그것까지 거절할 이유는 없다."""
        cleaned, bad, _ = _validate({"A1": ["food"]}, MAP)
        assert cleaned == {"A1": ["FOOD"]}
        assert not bad

    def test_not_a_list_is_refused(self):
        _, bad, _ = _validate({"A1": "ALL"}, MAP)
        assert bad

    def test_empty_list_means_no_industry(self):
        """업종 없음도 판단이다. 빈 배열은 정상이다."""
        cleaned, bad, _ = _validate({"A1": []}, MAP)
        assert cleaned == {"A1": []}
        assert not bad

    def test_unknown_key_is_reported_not_applied(self):
        """순서가 밀리면 엉뚱한 법령에 엉뚱한 업종이 붙는다."""
        cleaned, _, unknown = _validate({"Z9": ["ALL"]}, MAP)
        assert unknown == ["Z9"]
        assert cleaned == {}


class TestReadAnswer:
    def _write(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path / "답.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_plain_json(self, tmp_path):
        assert _read_answer(self._write(tmp_path, '{"A1": ["ALL"]}')) == {"A1": ["ALL"]}

    def test_code_fence_is_stripped(self, tmp_path):
        text = '설명입니다.\n```json\n{"A1": ["ALL"]}\n```\n'
        assert _read_answer(self._write(tmp_path, text)) == {"A1": ["ALL"]}

    def test_surrounding_words_are_ignored(self, tmp_path):
        text = '분류 결과: {"A1": ["ALL"]} 이상입니다.'
        assert _read_answer(self._write(tmp_path, text)) == {"A1": ["ALL"]}

    def test_no_json_raises(self, tmp_path):
        with pytest.raises(SystemExit):
            _read_answer(self._write(tmp_path, "못 하겠습니다"))

    def test_truncated_json_says_so(self, tmp_path):
        """긴 답은 채팅창에서 잘려 온다.

        "JSON 을 못 찾았다" 고 하면 붙여 넣기를 잘못한 줄 알고 같은 것을
        또 붙인다. 끊긴 것이라고 말해야 다시 받는다.
        """
        with pytest.raises(SystemExit, match="중간에서 끊긴"):
            _read_answer(self._write(tmp_path, '{"A1": ['))

    def test_malformed_json_raises(self, tmp_path):
        with pytest.raises(json.JSONDecodeError):
            _read_answer(self._write(tmp_path, '{"A1": [,]}'))


class TestPrompt:
    def test_taxonomy_hides_the_internal_marker(self):
        """**분류가 한 번도 성공한 적이 없었다.**

        GUIDE 에 INTERNAL 설명이 없는데 분류표를 만들 때 Industry 전체를
        훑었다. 매번 KeyError 가 났고, 부르는 쪽이 그걸 "AI 실패" 로
        삼켜서 미분류가 278건까지 쌓였다.
        """
        assert "INTERNAL" not in _taxonomy_block()
        assert "FOOD" in _taxonomy_block()

    def test_batch_prompt_drops_the_single_item_format(self):
        """두 형식을 같이 주면 모델이 둘을 섞은 것을 내놓는다."""
        rules = _judgement_rules()
        assert '"industries"' not in rules
        assert "애매하면 넓게 잡는다" in rules
