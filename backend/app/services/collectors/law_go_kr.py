"""국가법령정보 공동활용 OPEN API 수집 어댑터 (A등급, 부록 A).

이 어댑터가 제품에서 가장 중요하다. **시행일·공포일을 추론이 아니라 필드로** 가져오므로,
§9.4 V2(근거 없는 날짜 금지)와 AT-05를 데이터 레벨에서 만족시킨다.
AI가 "아마 내년 1월 1일 시행일 것"이라고 추측할 여지 자체가 없어진다.

인증: 발급키가 아니라 신청 시 직접 지정한 `OC` 식별자를 쿼리에 붙인다.
      URL에 노출되므로 프론트엔드에서 호출하지 않는다 (§12.1).

실측 확인 2026-08-06:
  lawSearch.do?target=law&sort=ddes  → 공포일 최신순 목록
  lawService.do?target=law&MST=...   → 기본정보/제개정이유/개정문/조문(변경여부 포함)
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
from app.domain.admin_rule import is_internal_rule
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
PUBLIC_LAW_URL = "https://www.law.go.kr/법령"
PUBLIC_ADMRUL_URL = "https://www.law.go.kr/행정규칙"

#: 세법.
TAX_LAWS: tuple[str, ...] = (
    "소득세법",
    "법인세법",
    "부가가치세법",
    "국세기본법",
    "국세징수법",
    "조세특례제한법",
    "상속세 및 증여세법",
    "종합부동산세법",
    "지방세법",
    "지방세특례제한법",
    "개별소비세법",
    "인지세법",
    "증권거래세법",
)

#: 4대보험.
#:
#: 세법만 모으면 "학원 원장님이 4대보험 물어보는데" 를 검색해도 0건이 나온다.
#: 실제로 그랬다. 사장님에게 4대보험은 세금과 같은 고지서로 오는 부담이고,
#: 상담에서 세금과 따로 오지 않는다. 소관부처가 다르다는 건 우리 사정이지
#: 사장님 사정이 아니다.
#:
#: 요율은 각 보험법이 아니라 보험료징수법과 그 시행령에 있다. 그래서 넣는다.
INSURANCE_LAWS: tuple[str, ...] = (
    "국민연금법",
    "국민건강보험법",
    "고용보험법",
    "산업재해보상보험법",
    "고용보험 및 산업재해보상보험의 보험료징수 등에 관한 법률",
)

#: MVP 수집 대상. 부록 A 원칙에 따라 하드코딩하지 않고
#: sources.settings["queries"] 로 덮어쓸 수 있다.
DEFAULT_TAX_QUERIES: tuple[str, ...] = TAX_LAWS + INSURANCE_LAWS

#: 행정규칙(고시·훈령·예규) 수집 대상 기관.
DEFAULT_ADMRUL_QUERIES: tuple[str, ...] = ("국세청", "재정경제부")


class LawApiError(Exception):
    """법령 API 호출 실패."""


@dataclass(frozen=True)
class LawListItem:
    """목록 조회 한 건. 여기 있는 날짜는 전부 원문 필드다."""

    law_id: str
    mst: str
    name: str
    law_type: str
    ministry: str
    promulgation_date: dt.date | None
    effective_date: dt.date | None
    promulgation_no: str
    revision_type: str
    detail_link: str

    @property
    def canonical_url(self) -> str:
        """법령의 안정적 식별 URL.

        개정될 때마다 MST 는 바뀌지만 법령 자체는 같은 것이다.
        따라서 canonical_url 은 법령명 기준으로 두고, 개정은 **버전**으로 쌓는다.
        이렇게 해야 "소득세법이 3번 개정됐다"가 raw_content 1건 + version 3개가 된다 (AT-02).
        """
        return f"{PUBLIC_LAW_URL}/{self.name}"


def _parse_date(value: str | None) -> dt.date | None:
    """`20260701` → date. 값이 없거나 형식이 다르면 None.

    **추측하지 않는다.** 파싱 실패는 null 이며, 그게 §9.4 V2 가 요구하는 동작이다.
    """
    if not value:
        return None
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _to_list_item(row: dict[str, Any]) -> LawListItem:
    """목록 한 행을 파싱한다.

    target=law 와 target=eflaw 의 필드 구성이 같아서 둘이 공유한다.
    """
    return LawListItem(
        law_id=str(row.get("법령ID", "")),
        mst=str(row.get("법령일련번호", "")),
        name=str(row.get("법령명한글", "")).strip(),
        law_type=str(row.get("법령구분명", "")),
        ministry=str(row.get("소관부처명", "")),
        promulgation_date=_parse_date(row.get("공포일자")),
        effective_date=_parse_date(row.get("시행일자")),
        promulgation_no=str(row.get("공포번호", "")),
        revision_type=str(row.get("제개정구분명", "")),
        detail_link=str(row.get("법령상세링크", "")),
    )


def _as_list(value: Any) -> list[Any]:
    """API 가 결과 1건일 때 배열 대신 객체를 주는 경우를 흡수한다."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class LawGoKrClient:
    """법령 API 클라이언트."""

    def __init__(
        self,
        oc: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.oc = oc or settings.law_api_oc
        self.base_url = (base_url or settings.law_api_base_url).rstrip("/")
        self._timeout = timeout
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.oc)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.oc:
            raise LawApiError(
                "TAXBRIEFING_LAW_API_OC 가 설정되지 않았습니다. "
                "open.law.go.kr 에서 신청한 OC 값을 넣으세요."
            )

        query = {"OC": self.oc, "type": "JSON", **params}
        client = self._client or httpx.Client(timeout=self._timeout, follow_redirects=True)
        owns = self._client is None
        try:
            response = client.get(f"{self.base_url}/{path}", params=query)
        except httpx.HTTPError as exc:
            raise LawApiError(f"법령 API 호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise LawApiError(f"법령 API HTTP {response.status_code}")

        # 잘못된 target 이나 인증 실패 시 JSON 대신 HTML 로그인 페이지가 온다.
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise LawApiError(
                f"법령 API 가 JSON 이 아닌 응답을 반환했습니다 "
                f"(content-type={content_type.split(';')[0]}). "
                "OC 값 또는 target 파라미터를 확인하세요."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise LawApiError(f"법령 API 응답을 파싱할 수 없습니다: {exc}") from exc

    def search_laws(
        self, query: str, *, display: int = 20, sort: str = "ddes"
    ) -> list[LawListItem]:
        """법령 목록 조회. `sort=ddes` 는 공포일자 내림차순(최신 우선)."""
        payload = self._get(
            "lawSearch.do",
            {"target": "law", "query": query, "display": display, "sort": sort},
        )
        envelope = payload.get("LawSearch", {})
        if envelope.get("resultCode") not in (None, "00"):
            raise LawApiError(f"법령 API 오류: {envelope.get('resultMsg')}")

        return [_to_list_item(row) for row in _as_list(envelope.get("law"))]

    def get_law(self, mst: str) -> dict[str, Any]:
        """법령 본문 조회. 기본정보·제개정이유·개정문·조문을 담고 있다."""
        payload = self._get("lawService.do", {"target": "law", "MST": mst})
        law = payload.get("법령")
        if not law:
            raise LawApiError(f"법령 본문을 찾을 수 없습니다 (MST={mst})")
        return law

    def search_upcoming_laws(self, query: str, *, display: int = 20) -> list[LawListItem]:
        """**아직 시행되지 않은** 법령 (target=eflaw).

        `target=law` 는 지금 효력이 있는 법만 준다. 그래서 수집한 145건이
        전부 EFFECTIVE 였고, "시행 예정" 이라는 상태가 화면에 존재하지 않았다.

        eflaw 는 공포는 됐지만 시행일이 아직 오지 않은 것까지 준다.
        세무사무소가 "곧 이렇게 바뀝니다" 를 미리 말할 수 있는 근거가 이것이다.
        필드 구성은 target=law 와 같아서 파서를 그대로 쓴다.
        """
        # **시행일 내림차순**(efdes)이다.
        #
        # 처음에 efasc(오름차순)로 뒀더니 108건을 조회하고 0건을 저장했다.
        # eflaw 는 그 법의 시행일 이력을 전부 주는데, 오름차순이면 법당
        # 가져오는 몇 건이 전부 옛날 시행분이라 미래 필터에서 다 걸러졌다.
        # 우리가 원하는 것은 앞으로 올 것이므로 뒤에서부터 가져온다.
        payload = self._get(
            "lawSearch.do",
            {"target": "eflaw", "query": query, "display": display, "sort": "efdes"},
        )
        envelope = payload.get("LawSearch", {})
        if envelope.get("resultCode") not in (None, "00"):
            raise LawApiError(f"법령 API 오류: {envelope.get('resultMsg')}")
        return [_to_list_item(row) for row in _as_list(envelope.get("law"))]

    def search_admrul(self, query: str, *, display: int = 20) -> list[dict[str, Any]]:
        """행정규칙(고시·훈령·예규) 목록. 국세청 고시가 여기 있다."""
        payload = self._get(
            "lawSearch.do", {"target": "admrul", "query": query, "display": display}
        )
        envelope = payload.get("AdmRulSearch", {})
        if envelope.get("resultCode") not in (None, "00"):
            raise LawApiError(f"행정규칙 API 오류: {envelope.get('resultMsg')}")
        return _as_list(envelope.get("admrul"))


def build_normalized_text(item: LawListItem, law: dict[str, Any]) -> str:
    """AI 분석과 검수자 대조에 쓸 정규화 본문을 만든다.

    조문 106개를 통째로 넣지 않는다. **변경된 조문만** 담는다.
    개정에서 중요한 건 무엇이 달라졌는가이고, 전문을 넣으면
    AI 가 관련 없는 조문을 근거로 인용하기 시작한다.
    """
    basic = law.get("기본정보", {}) or {}
    lines: list[str] = [
        f"법령명: {item.name}",
        f"법종구분: {item.law_type or basic.get('법종구분', '')}",
        f"소관부처: {item.ministry or basic.get('소관부처', '')}",
        f"제개정구분: {item.revision_type or basic.get('제개정구분', '')}",
        f"공포일자: {item.promulgation_date.isoformat() if item.promulgation_date else '확인 필요'}",
        f"공포번호: {item.promulgation_no}",
        f"시행일자: {item.effective_date.isoformat() if item.effective_date else '확인 필요'}",
        "",
    ]

    reason = _flatten_text(law.get("제개정이유"))
    if reason:
        lines += ["[제개정이유]", reason, ""]

    revision = _flatten_text(law.get("개정문"))
    if revision:
        lines += ["[개정문]", revision, ""]

    changed = _changed_articles(law)
    if changed:
        lines.append(f"[변경 조문 {len(changed)}건]")
        for article in changed:
            no = article.get("조문번호", "")
            eff = _parse_date(article.get("조문시행일자"))
            head = f"제{no}조"
            if eff:
                head += f" (조문시행일 {eff.isoformat()})"
            lines += [head, _flatten_text(article.get("조문내용")), ""]
    else:
        lines += ["[변경 조문] 변경 표시된 조문이 없습니다.", ""]

    return "\n".join(lines).strip()


#: 법령 API 개정문에는 별표·서식 이미지가 <img> 태그로 섞여 온다.
#: 그대로 두면 AI 입력 토큰만 잡아먹고 판단에는 보탬이 되지 않는다.
_HTML_TAG = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"\n{3,}")


def _strip_html(text: str) -> str:
    """태그를 걷어내되 이미지가 있었다는 사실은 남긴다.

    별표·서식이 이미지로만 제공되는 경우가 있어, 아예 지우면 검수자가
    "왜 내용이 없지?" 하고 원문을 다시 찾아야 한다.
    """
    image_count = len(re.findall(r"<img\b", text, re.I))
    cleaned = _HTML_TAG.sub("", text)
    cleaned = _BLANK_RUN.sub("\n\n", cleaned).strip()
    if image_count:
        cleaned += f"\n(별표·서식 이미지 {image_count}건은 원문 링크에서 확인)"
    return cleaned


def _flatten_text(value: Any) -> str:
    """API 가 문자열·배열·중첩배열을 섞어서 준다. 전부 평문으로 편다."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _strip_html(value) if "<" in value else value.strip()
    if isinstance(value, list):
        return "\n".join(part for part in (_flatten_text(v) for v in value) if part)
    if isinstance(value, dict):
        return "\n".join(part for part in (_flatten_text(v) for v in value.values()) if part)
    return str(value)


def _changed_articles(law: dict[str, Any]) -> list[dict[str, Any]]:
    articles = _as_list((law.get("조문") or {}).get("조문단위"))
    return [a for a in articles if str(a.get("조문변경여부", "")).upper() == "Y"]


class LawCollector:
    """세법 개정 수집기."""

    name = "law.go.kr:law"
    version = ADAPTER_VERSION

    def __init__(self, client: LawGoKrClient | None = None) -> None:
        self.client = client or LawGoKrClient()

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats:
        stats = CollectStats()
        queries = tuple(source.settings.get("queries") or DEFAULT_TAX_QUERIES)
        per_query = max(1, limit // max(1, len(queries)))

        for query in queries:
            try:
                items = self.client.search_laws(query, display=per_query, sort="ddes")
            except LawApiError as exc:
                stats.fail(f"search:{query}", exc)
                continue

            # **오래된 것부터 넣는다.**
            #
            # 한 법의 여러 개정을 같은 canonical_url 로 모으므로(개정은 새 기록이
            # 아니라 새 버전이다), 마지막에 넣은 것이 현재 버전이 된다.
            # 지금은 API 가 법 하나당 현행 한 건만 주므로 순서가 문제되지 않지만,
            # 검색어나 파라미터가 바뀌어 한 법의 여러 개정이 함께 오면 최신순
            # 응답을 그대로 넣는 순간 가장 오래된 개정이 현재로 남는다.
            #
            # 날짜 없는 항목은 맨 앞에 넣어 현재 버전이 되지 않게 한다.
            # 날짜를 모르는 것을 최신으로 취급하면 아는 것이 밀려난다.
            ordered = sorted(
                items,
                key=lambda i: (i.promulgation_date is not None, i.promulgation_date or dt.date.min),
            )

            for item in ordered:
                stats.discovered += 1

                # 공포일이 기준일보다 오래된 것은 건너뛴다. 이미 수집했거나 관심 밖이다.
                if since and item.promulgation_date and item.promulgation_date < since:
                    continue
                if not item.mst:
                    continue

                try:
                    self._ingest_one(db, source, item, stats)
                except Exception as exc:
                    stats.fail(f"{item.name}(MST={item.mst})", exc)

        return stats

    def _ingest_one(
        self, db: Session, source: Source, item: LawListItem, stats: CollectStats
    ) -> None:
        law = self.client.get_law(item.mst)
        text = build_normalized_text(item, law)

        result = ingest(
            db,
            source_id=source.id,
            canonical_url=item.canonical_url,
            title=f"{item.name} ({item.revision_type})" if item.revision_type else item.name,
            publisher=item.ministry or "법제처",
            raw_body=text,
            published_at=_as_datetime(item.promulgation_date),
            source_item_id=f"{item.law_id}:{item.promulgation_no}",
            parser_version=f"law_go_kr/{ADAPTER_VERSION}",
        )

        # 날짜는 어댑터가 원문 필드에서 그대로 가져온 것이다. 추론이 아니다.
        result.version.doc_metadata = {
            "law_id": item.law_id,
            "mst": item.mst,
            "promulgation_date": item.promulgation_date.isoformat()
            if item.promulgation_date
            else None,
            "effective_date": item.effective_date.isoformat()
            if item.effective_date
            else None,
            "promulgation_no": item.promulgation_no,
            "revision_type": item.revision_type,
            "law_type": item.law_type,
            "ministry": item.ministry,
            "detail_link": item.detail_link,
            "changed_article_count": len(_changed_articles(law)),
            "source_field_dates": True,
        }
        db.flush()
        stats.record(result.outcome)


class UpcomingLawCollector:
    """시행예정 법령 수집기 (target=eflaw).

    **왜 별도 기록으로 두는가.**

    LawCollector 는 한 법의 여러 개정을 같은 canonical_url 로 모아 버전으로
    쌓는다. 개정은 새 기록이 아니라 새 버전이라는 원칙이다 (AT-02).

    그런데 시행예정 개정은 다르다. 현행법과 **동시에 존재해야 한다.**

        소득세법 (현행, 2026-07-01 시행)     ← 지금 적용되는 것
        소득세법 (시행예정, 2027-01-01)      ← 앞으로 바뀔 것

    같은 URL 로 넣으면 시행예정본이 현행본을 덮어써서, 사장님이 오늘 적용되는
    기준을 못 보게 된다. 세무 브리핑에서 그건 사고다.
    그래서 시행일을 URL 에 넣어 시행일마다 별개 기록으로 둔다.

    시행일이 지나면 LawCollector 가 같은 내용을 현행으로 다시 수집한다.
    중복처럼 보이지만 둘은 다른 것이다 — 하나는 "예고", 하나는 "현행"이고,
    사용자가 그 시점에 알아야 할 것도 다르다.
    """

    name = "law.go.kr:eflaw"
    version = ADAPTER_VERSION

    def __init__(self, client: LawGoKrClient | None = None) -> None:
        self.client = client or LawGoKrClient()

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats:
        """`since` 는 쓰지 않는다 — 이 수집기는 **미래**만 본다."""
        del since

        stats = CollectStats()
        queries = tuple(source.settings.get("queries") or DEFAULT_TAX_QUERIES)
        per_query = max(1, limit // max(1, len(queries)))
        today = dt.datetime.now(dt.UTC).date()

        for query in queries:
            try:
                items = self.client.search_upcoming_laws(query, display=per_query)
            except LawApiError as exc:
                stats.fail(f"eflaw:{query}", exc)
                continue

            for item in items:
                stats.discovered += 1

                # 시행일이 지났으면 그건 현행법이다. LawCollector 의 몫이다.
                if not item.effective_date or item.effective_date <= today:
                    continue
                if not item.mst:
                    continue

                try:
                    self._ingest_one(db, source, item, stats)
                except Exception as exc:
                    stats.fail(f"{item.name}(시행 {item.effective_date})", exc)

        return stats

    def _ingest_one(
        self, db: Session, source: Source, item: LawListItem, stats: CollectStats
    ) -> None:
        law = self.client.get_law(item.mst)
        text = build_normalized_text(item, law)
        effective = item.effective_date.isoformat() if item.effective_date else "미정"

        result = ingest(
            db,
            source_id=source.id,
            # **시행일 + 공포번호**로 가른다.
            #
            # 처음엔 시행일만 넣었더니 소득세법 시행령 2027-01-01 시행분 6개
            # 개정이 한 기록으로 뭉쳐 5개가 버전으로 밀려 안 보였다.
            # 같은 날 시행되더라도 공포번호가 다르면 서로 다른 개정이고,
            # 사장님이 봐야 할 내용도 다르다.
            canonical_url=(
                f"{item.canonical_url}?시행={effective}&공포={item.promulgation_no}"
            ),
            title=f"{item.name} ({item.revision_type}, {effective} 시행예정)".replace(
                " (, ", " ("
            ),
            publisher=item.ministry or "법제처",
            raw_body=text,
            published_at=_as_datetime(item.promulgation_date),
            source_item_id=f"{item.law_id}:{item.promulgation_no}:{effective}",
            parser_version=f"law_go_kr_eflaw/{ADAPTER_VERSION}",
        )

        result.version.doc_metadata = {
            "law_id": item.law_id,
            "mst": item.mst,
            "promulgation_date": item.promulgation_date.isoformat()
            if item.promulgation_date
            else None,
            "effective_date": effective,
            "promulgation_no": item.promulgation_no,
            "revision_type": item.revision_type,
            "law_type": item.law_type,
            "ministry": item.ministry,
            "detail_link": item.detail_link,
            "changed_article_count": len(_changed_articles(law)),
            "source_field_dates": True,
            # 공포는 됐으나 시행 전이다. 이 값이 콘텐츠의 legal_status 를 정한다.
            "policy_stage": "PROMULGATED_PENDING",
        }
        db.flush()
        stats.record(result.outcome)


class AdmRulCollector:
    """행정규칙(고시·훈령·예규) 수집기. 국세청 고시가 여기 들어온다."""

    name = "law.go.kr:admrul"
    version = ADAPTER_VERSION

    def __init__(self, client: LawGoKrClient | None = None) -> None:
        self.client = client or LawGoKrClient()

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats:
        stats = CollectStats()
        queries = tuple(source.settings.get("admrul_queries") or DEFAULT_ADMRUL_QUERIES)
        per_query = max(1, limit // max(1, len(queries)))
        # 자른 것은 세어 둔다. 몇 건이 왜 빠졌는지 남지 않으면
        # 다음에 뭔가 안 보일 때 어디를 볼지 알 수 없다.
        skipped: list[str] = []

        for query in queries:
            try:
                rows = self.client.search_admrul(query, display=per_query)
            except LawApiError as exc:
                stats.fail(f"admrul:{query}", exc)
                continue

            for row in rows:
                stats.discovered += 1
                issued = _parse_date(row.get("발령일자"))
                if since and issued and issued < since:
                    continue

                name = str(row.get("행정규칙명", "")).strip()
                if not name:
                    continue

                # 부처 내부 운영 규칙은 담지 않는다. 「국세청당직근무규정」은
                # 사장님이 알 이유가 없고, 요약 토큰만 먹는다.
                if is_internal_rule(name):
                    skipped.append(name)
                    continue

                try:
                    kind = str(row.get("행정규칙종류", ""))
                    ministry = str(row.get("소관부처명", ""))
                    text = "\n".join(
                        [
                            f"행정규칙명: {name}",
                            f"종류: {kind}",
                            f"소관부처: {ministry}",
                            f"발령일자: {issued.isoformat() if issued else '확인 필요'}",
                            f"현행연혁: {row.get('현행연혁구분', '')}",
                        ]
                    )
                    result = ingest(
                        db,
                        source_id=source.id,
                        canonical_url=f"{PUBLIC_ADMRUL_URL}/{name}",
                        title=f"{name} ({kind})" if kind else name,
                        publisher=ministry or "법제처",
                        raw_body=text,
                        published_at=_as_datetime(issued),
                        source_item_id=str(row.get("행정규칙ID", "") or name),
                        parser_version=f"law_go_kr_admrul/{ADAPTER_VERSION}",
                    )
                    result.version.doc_metadata = {
                        "rule_kind": kind,
                        "ministry": ministry,
                        "issued_date": issued.isoformat() if issued else None,
                        "detail_link": str(row.get("행정규칙상세링크", "")),
                        "source_field_dates": True,
                    }
                    db.flush()
                    stats.record(result.outcome)
                except Exception as exc:
                    stats.fail(name, exc)

        if skipped:
            logger.info(
                "admrul.internal_skipped", count=len(skipped), sample=skipped[:5]
            )

        return stats


def _as_datetime(value: dt.date | None) -> dt.datetime | None:
    if value is None:
        return None
    return dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)
