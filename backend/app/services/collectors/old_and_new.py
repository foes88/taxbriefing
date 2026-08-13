"""신구법 비교 (법제처 DRF `oldAndNew`).

**실무자가 가장 먼저 묻는 것.**

"이 조문이 정확히 어떻게 바뀌었나." 개정이유는 왜 바꿨는지를 말하고,
개정문은 "제3항 중 '30일'을 '60일'로 한다" 처럼 지시문으로 말한다.
둘 다 조문 전문을 옆에 놓고 읽어야 이해된다.

법제처가 그 대조표를 이미 만들어 준다. 구조문과 신조문을 같은 번호로
짝지어 주고, 바뀐 부분을 `<P>` 로 감싸 놓았다. 우리가 diff 를 돌릴
필요도, 모델에게 "무엇이 바뀌었는지 써 봐라" 라고 시킬 필요도 없다.

**짝이 어긋나면 엉뚱한 조문을 나란히 놓게 된다.** 세법 5종 15건으로
확인했다 — 구/신 개수와 번호가 전부 1:1 로 맞았다 (조세특례제한법은
502행). 그래도 코드에서 다시 확인하고, 어긋나면 버린다.

식별은 추측하지 않는다. 응답의 `신구법ID` 가 우리가 이미 갖고 있는
`law_id` 와 같은 값이고, `공포번호` 도 그대로 맞는다. 법령명 문자열을
비교할 이유가 없다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
TARGET = "oldAndNew"

#: 응답에 나오는 태그는 이 하나뿐이다 (3개 법령 156행에서 확인).
#: 바뀐 부분을 감싼다.
_CHANGED = re.compile(r"<P>(.*?)</P>", re.DOTALL)
_TAG = re.compile(r"</?P>")

#: "(현행과 같음)", "(생  략)" 처럼 내용이 없는 행. 화면에 낼 것이 없다.
_PLACEHOLDER = re.compile(r"^\s*[\d가-힣.\s∼~,·]{0,40}\(\s*(현행과\s*같음|생\s*략)\s*\)\s*$")  # noqa: RUF001

#: 한 콘텐츠에 담을 최대 조문 수. 조세특례제한법 개정 한 건이 277행이라
#: 전부 담으면 본문이 수백 KB 가 된다. 자를 때는 몇 개를 잘랐는지 같이
#: 남긴다 — **말없이 자르면 "이게 전부" 로 읽힌다.**
MAX_ROWS = 40


class OldAndNewError(Exception):
    """신구법 API 호출 실패."""


@dataclass(frozen=True)
class ComparisonItem:
    """검색 결과 한 줄."""

    mst: str
    law_id: str
    law_name: str
    promulgation_no: str
    effective_date: str
    revision_type: str


@dataclass(frozen=True)
class DiffRow:
    """구/신 한 쌍.

    `old`·`new` 는 조각 목록이다. `{"text": ..., "changed": true}` 인
    조각이 법제처가 표시한 변경 부분이다.

    태그를 그대로 내려보내지 않고 조각으로 나누는 이유 — 화면에서
    HTML 을 그대로 심으면 원문에 태그가 섞여 들어왔을 때 그게 실행된다.
    조각이면 글자로만 다룬다.
    """

    no: str
    old: list[dict[str, Any]]
    new: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {"no": self.no, "old": self.old, "new": self.new}


def split_segments(content: str) -> list[dict[str, Any]]:
    """`<P>` 로 감싼 곳을 변경 조각으로 가른다. 글자는 건드리지 않는다."""
    out: list[dict[str, Any]] = []
    cursor = 0
    for mark in _CHANGED.finditer(content):
        if mark.start() > cursor:
            out.append({"text": content[cursor : mark.start()], "changed": False})
        out.append({"text": mark.group(1), "changed": True})
        cursor = mark.end()
    if cursor < len(content):
        out.append({"text": content[cursor:], "changed": False})
    return [seg for seg in out if seg["text"]]


def is_placeholder(content: str) -> bool:
    """`2. ~ 4. (현행과 같음)` 처럼 내용 없는 행인가.

    변경 표시가 붙어 있어도 마찬가지다. 법제처가 "(생 략)" 을 `<P>` 로
    감싸 보내는 경우가 있는데, 그건 조문이 바뀌었다는 뜻이 아니라
    표기가 바뀐 것이다. 그래서 태그를 떼고 본다.
    """
    return bool(_PLACEHOLDER.match(_TAG.sub("", content).strip()))


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """목록을 꺼낸다. 1건일 때 배열 대신 객체가 오는 것을 흡수한다."""
    value = payload.get(key)
    if isinstance(value, dict):
        inner = value.get("조문")
        if isinstance(inner, dict):
            return [inner]
        if isinstance(inner, list):
            return inner
    return []


class OldAndNewClient:
    """신구법 비교 조회."""

    name = "law.go.kr:oldAndNew"
    version = "1.0.0"

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 40.0) -> None:
        self.oc = get_settings().law_api_oc
        self._client = client
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.oc)

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.get(url, params={"OC": self.oc, "type": "JSON", **params})
        except httpx.HTTPError as exc:
            raise OldAndNewError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise OldAndNewError(f"HTTP {response.status_code}")
        body = response.text.strip()
        if not body.startswith("{"):
            raise OldAndNewError(f"JSON 이 아닙니다 ({body[:60]!r})")
        return response.json()

    def search(self, law_name: str, *, display: int = 20) -> list[ComparisonItem]:
        """법령명으로 신구법 대조표를 찾는다."""
        payload = self._get(
            SEARCH_URL,
            {"target": TARGET, "query": law_name, "display": display, "sort": "ddes"},
        )
        block = payload.get("OldAndNewLawSearch") or {}
        rows = block.get("oldAndNew") or []
        if isinstance(rows, dict):
            rows = [rows]

        out: list[ComparisonItem] = []
        for row in rows:
            mst = str(row.get("신구법일련번호") or "").strip()
            if not mst:
                continue
            out.append(
                ComparisonItem(
                    mst=mst,
                    law_id=str(row.get("신구법ID") or "").strip(),
                    law_name=str(row.get("신구법명") or "").strip(),
                    promulgation_no=str(row.get("공포번호") or "").strip(),
                    effective_date=str(row.get("시행일자") or "").strip(),
                    revision_type=str(row.get("제개정구분명") or "").strip(),
                )
            )
        return out

    def diff(self, mst: str) -> tuple[list[DiffRow], int]:
        """대조표 본문. `(보여줄 행, 잘라낸 행 수)`.

        바뀐 것이 없는 행은 버린다. 개정문에 손대지 않은 조문까지 나열하면
        정작 바뀐 조문이 묻힌다.
        """
        payload = self._get(SERVICE_URL, {"target": TARGET, "MST": mst})
        service = payload.get("OldAndNewService") or {}
        olds = _rows(service, "구조문목록")
        news = _rows(service, "신조문목록")

        if len(olds) != len(news):
            # 짝이 안 맞으면 어느 쪽이 어느 쪽인지 알 수 없다. 억지로
            # 붙이면 엉뚱한 조문을 "이렇게 바뀐다" 고 보여주게 된다.
            raise OldAndNewError(f"구/신 조문 수가 다릅니다 ({len(olds)} vs {len(news)})")

        rows: list[DiffRow] = []
        for old, new in zip(olds, news, strict=True):
            if str(old.get("no")) != str(new.get("no")):
                raise OldAndNewError(f"조문 번호가 어긋납니다 ({old.get('no')} vs {new.get('no')})")

            old_text = str(old.get("content") or "")
            new_text = str(new.get("content") or "")

            # 법제처가 변경 표시를 붙인 행만 남긴다.
            if "<P>" not in old_text and "<P>" not in new_text:
                continue
            if is_placeholder(old_text) and is_placeholder(new_text):
                continue

            rows.append(
                DiffRow(
                    no=str(old.get("no") or ""),
                    old=split_segments(old_text),
                    new=split_segments(new_text),
                )
            )

        dropped = max(0, len(rows) - MAX_ROWS)
        return rows[:MAX_ROWS], dropped
