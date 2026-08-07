"""업종 분류 정규화. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

from app.domain.industry import GUIDE, LABEL, Industry, label, normalize


class TestNormalize:
    def test_keeps_known_codes(self):
        assert normalize(["FOOD", "EDU"]) == ["FOOD", "EDU"]

    def test_drops_invented_codes(self):
        """모델이 지어낸 업종을 화면에 띄우느니 없는 게 낫다."""
        assert normalize(["FOOD", "요식업", "FOOD_SERVICE", "치킨집"]) == ["FOOD"]

    def test_accepts_lowercase(self):
        assert normalize(["food", " Edu "]) == ["FOOD", "EDU"]

    def test_deduplicates(self):
        assert normalize(["FOOD", "FOOD"]) == ["FOOD"]

    def test_all_absorbs_the_rest(self):
        """'전 업종 공통 + 요식업'은 요식업만이라는 뜻인지 알 수 없다."""
        assert normalize(["FOOD", "ALL", "EDU"]) == ["ALL"]

    def test_non_list_is_empty(self):
        assert normalize("FOOD") == []
        assert normalize(None) == []

    def test_empty_stays_empty(self):
        """사업자와 무관한 개정은 빈 배열이 정답이다. 억지로 채우지 않는다."""
        assert normalize([]) == []


class TestLabel:
    def test_known_code_becomes_korean(self):
        assert label("FOOD") == "요식·음식점"

    def test_unknown_code_passes_through(self):
        """분류표가 늘어나도 옛 데이터가 화면에서 사라지면 안 된다."""
        assert label("FUTURE_CODE") == "FUTURE_CODE"


class TestTaxonomy:
    def test_every_code_has_label_and_guide(self):
        """설명이 없으면 모델이 경계를 못 긋는다. 이름이 없으면 화면에 코드가 뜬다."""
        for item in Industry:
            assert LABEL[item].strip()
            assert GUIDE[item].strip()
