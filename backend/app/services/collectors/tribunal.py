"""조세심판원 심판례 수집기.

**왜 이게 중요한가.**

법령은 "무엇이 바뀌었나"를 알려주지만, 심판례는 "그래서 실제로 어떻게
판단되나"를 알려준다. 세무사무소 직원이 남보다 앞서는 지점이 여기다 —
같은 조문을 읽어도 심판례를 아는 사람이 다른 답을 낸다.

**AI 가 지어낼 여지가 없다.**

법제처 API 가 이미 구조를 갈라서 준다.

    사건명 · 세목 · 처분청 · 재결청
    청구취지  — 납세자 주장
    이유      — 심판원 판단 근거
    재결요지  — 핵심
    주문      — 인용 / 기각 / 일부인용
    관련법령 · 참조결정

요약 모델에게 "쟁점을 뽑아라" 라고 시킬 필요가 없다. 원문에 이미 있다.
본문이 없는 출처(국세청 해석 목록, 판례 목록)에는 이 짓을 하지 않는다 —
제목만 주고 쟁점을 쓰라고 하면 그건 지어내는 것이다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
TARGET = "ttSpecialDecc"

#: 사업자에게 실제로 걸리는 세목. 전체 6,400여 건을 다 가져오지 않는다.
#: 상속·증여처럼 사무소 일상 업무와 거리가 먼 것은 넣지 않았다 —
#: 필요해지면 sources.settings["queries"] 로 덮어쓴다.
DEFAULT_QUERIES: tuple[str, ...] = (
    "부가가치세",
    "법인세",
    "종합소득세",
    "원천징수",
    "가산세",
    "세금계산서",
    "매입세액",
    "업무용승용차",
    "기업업무추진비",
    "가지급금",
)

#: 본문에서 뽑아 쓸 항목. 순서가 곧 화면에 보이는 순서다.
#: 사건 개요 → 무엇을 다퉜나 → 어떻게 판단했나 → 결론.
BODY_FIELDS: tuple[tuple[str, str], ...] = (
    ("사건명", "사건명"),
    ("세목", "세목"),
    ("처분청", "처분청"),
    ("재결청", "재결청"),
    ("청구취지", "청구인 주장"),
    ("재결요지", "판단 요지"),
    ("이유", "판단 이유"),
    ("주문", "주문"),
    ("관련법령", "관련 법령"),
    ("참조결정", "참조 결정"),
)


class TribunalError(Exception):
    """조세심판원 API 호출 실패."""


@dataclass(frozen=True)
class TribunalItem:
    serial: str
    case_name: str
    case_no: str
    decided_at: dt.date | None
    authority: str
    disposition_agency: str
    result: str
    detail_link: str

    @property
    def canonical_url(self) -> str:
        """심판례는 개정되지 않는다. 일련번호 하나로 영구 식별된다."""
        return f"https://www.law.go.kr/조세심판원/{self.serial}"


def _parse_date(value: Any) -> dt.date | None:
    """`20260813` → date. 형식이 다르면 None — 추측하지 않는다 (§9.4 V2)."""
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """응답에서 목록을 꺼낸다. 1건일 때 배열 대신 객체가 오는 경우를 흡수한다."""
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        for inner in value.values():
            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                return inner
            if isinstance(inner, dict) and "특별행정심판재결례일련번호" in inner:
                return [inner]
    return []


#: 주문에서 결론을 읽는다. 앞에 오는 것이 이긴다 —
#: "일부 인용" 은 "인용" 을 포함하므로 먼저 봐야 한다.
_OUTCOMES: tuple[tuple[str, str], ...] = (
    ("일부인용", "일부인용"),
    ("일부 인용", "일부인용"),
    ("경정한다", "일부인용"),
    ("취소한다", "인용"),
    ("인용한다", "인용"),
    ("기각한다", "기각"),
    ("각하한다", "각하"),
    ("재조사", "재조사"),
)


def read_outcome(detail: dict[str, Any]) -> str:
    """인용인가 기각인가.

    목록의 `재결구분명` 은 이 값이 아니다 — "조세" 처럼 분야가 들어온다.
    그걸 결론인 줄 알고 제목에 붙였더니 "…부가가치세 처분 (조세)" 가 됐다.
    아무것도 알려주지 않는 괄호였다.

    실제 결론은 주문에 문장으로 적혀 있다. 거기서 읽는다.
    못 읽으면 빈 문자열이다 — **추측하지 않는다.** 기각을 인용으로 잘못
    표시하면 사업자가 반대로 판단한다.
    """
    text = str(detail.get("주문") or "").replace(" ", "")
    for needle, label in _OUTCOMES:
        if needle.replace(" ", "") in text:
            return label
    return ""


def build_body(detail: dict[str, Any]) -> str:
    """본문을 사람이 읽는 순서로 조립한다.

    값이 없는 항목은 넣지 않는다. 빈 제목만 늘어놓으면 읽는 사람이
    "여기 뭔가 있어야 하는데 없나" 하고 멈춘다.
    """
    parts: list[str] = []
    for key, label in BODY_FIELDS:
        value = str(detail.get(key) or "").strip()
        if not value:
            continue
        parts.append(f"[{label}]\n{value}")
    return "\n\n".join(parts)


#: `build_body` 가 붙인 구획 표시를 되읽는 정규식.
_SECTION = re.compile(r"^\[([^\]\n]{1,20})\]\n", re.MULTILINE)


def parse_sections(text: str) -> dict[str, str]:
    """`build_body` 의 역함수. 저장된 원문을 다시 구획으로 가른다.

    수집할 때 이미 갈라 놓은 것을 왜 다시 파싱하는가 — 화면이 쓸 구조화
    본문은 수집이 아니라 초안 단계에서 만들고, 그때는 API 응답이 아니라
    저장된 원문만 있기 때문이다. 원문을 정본으로 두고 필요할 때 다시
    읽는 편이, 같은 내용을 두 군데 저장해 두고 어긋나기를 기다리는 것보다 낫다.
    """
    marks = list(_SECTION.finditer(text))
    out: dict[str, str] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        value = text[mark.end() : end].strip()
        if value:
            out[mark.group(1)] = value
    return out


class TaxTribunalCollector:
    """조세심판원 심판례."""

    name = "law.go.kr:tribunal"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 30.0) -> None:
        self.oc = get_settings().law_api_oc
        self._client = client
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.oc)

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 40,
    ) -> CollectStats:
        stats = CollectStats()

        if not self.configured:
            stats.fail(source.display_name, TribunalError("TAXBRIEFING_LAW_API_OC 가 없습니다."))
            return stats

        queries = tuple((source.settings or {}).get("queries") or DEFAULT_QUERIES)
        per_query = max(2, limit // max(1, len(queries)))
        seen: set[str] = set()

        for query in queries:
            try:
                items = self._search(query, per_query)
            except TribunalError as exc:
                stats.fail(f"tribunal:{query}", exc)
                continue

            for item in items:
                stats.discovered += 1

                # 같은 심판례가 여러 세목 검색에 걸린다. 한 번만 담는다.
                if item.serial in seen:
                    continue
                seen.add(item.serial)

                if since and item.decided_at and item.decided_at < since:
                    continue

                try:
                    self._ingest_one(db, source, item, query, stats)
                except Exception as exc:
                    stats.fail(f"{item.case_no or item.serial}", exc)

        return stats

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.get(url, params={"OC": self.oc, "type": "JSON", **params})
        except httpx.HTTPError as exc:
            raise TribunalError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise TribunalError(f"HTTP {response.status_code}")

        body = response.text.strip()
        if not body.startswith("{"):
            raise TribunalError(f"JSON 이 아닙니다 ({body[:60]!r})")
        return response.json()

    def _search(self, query: str, display: int) -> list[TribunalItem]:
        payload = self._get(
            SEARCH_URL, {"target": TARGET, "query": query, "display": display, "sort": "ddes"}
        )
        out: list[TribunalItem] = []
        for row in _rows(payload):
            serial = str(row.get("특별행정심판재결례일련번호", "")).strip()
            if not serial:
                continue
            out.append(
                TribunalItem(
                    serial=serial,
                    case_name=str(row.get("사건명", "")).strip(),
                    case_no=str(row.get("청구번호", "")).strip(),
                    decided_at=_parse_date(row.get("의결일자")),
                    authority=str(row.get("재결청", "")).strip(),
                    disposition_agency=str(row.get("처분청", "")).strip(),
                    result=str(row.get("재결구분명", "")).strip(),
                    detail_link=str(row.get("행정심판재결례상세링크", "")).strip(),
                )
            )
        return out

    def _fetch_detail(self, serial: str) -> dict[str, Any]:
        payload = self._get(SERVICE_URL, {"target": TARGET, "ID": serial})
        for value in payload.values():
            if isinstance(value, dict) and value:
                return value
        raise TribunalError(f"본문을 찾을 수 없습니다 (ID={serial})")

    def _ingest_one(
        self,
        db: Session,
        source: Source,
        item: TribunalItem,
        query: str,
        stats: CollectStats,
    ) -> None:
        detail = self._fetch_detail(item.serial)
        body = build_body(detail)
        if not body:
            raise TribunalError("본문이 비어 있습니다")

        title = item.case_name or detail.get("사건명") or f"조세심판 {item.case_no}"
        result = read_outcome(detail)

        ingested = ingest(
            db,
            source_id=source.id,
            canonical_url=item.canonical_url,
            title=f"{title} ({result})" if result else str(title),
            publisher=item.authority or "조세심판원",
            raw_body=body,
            published_at=(
                dt.datetime.combine(item.decided_at, dt.time(), tzinfo=dt.UTC)
                if item.decided_at
                else None
            ),
            source_item_id=item.case_no or item.serial,
            parser_version=f"tribunal/{ADAPTER_VERSION}",
        )

        ingested.version.doc_metadata = {
            "serial": item.serial,
            "case_no": item.case_no,
            "tax_type": str(detail.get("세목") or ""),
            "result": result,
            "authority": item.authority,
            "disposition_agency": item.disposition_agency,
            "decided_at": item.decided_at.isoformat() if item.decided_at else None,
            "related_laws": str(detail.get("관련법령") or ""),
            "matched_query": query,
            "detail_link": item.detail_link,
            # 심판례는 법령이 아니다. 정책 상태를 붙이면 안 된다 —
            # "시행 중" 같은 표시가 붙으면 제도 변경으로 오해한다.
            "content_kind": "TRIBUNAL_DECISION",
        }
        db.flush()
        stats.record(ingested.outcome)
