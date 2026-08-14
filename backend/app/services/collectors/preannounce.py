"""입법예고 수집기 (국민참여입법센터 `rest/ogLmPp`).

**이 서비스가 파는 것이 여기서 시작된다.**

지금까지 우리가 잡는 가장 이른 신호는 "공포" 다. 이미 확정된 것이라
알아도 준비할 시간이 짧다. 입법예고는 그보다 앞이다 — 정부가 "이렇게
바꾸려 한다" 고 내놓고 의견을 받는 40일이다.

세무사무소 직원이 남보다 앞서는 지점이 여기다. 공포된 뒤에 아는 사람과
예고 단계에서 아는 사람은 고객에게 할 말이 다르다.

**부처 코드로 거른다.**

낱말로 거르면 "부가가치세" 가 제목에 없는 세법 개정을 놓친다. 이 API 는
소관부처를 파라미터로 받으므로 서버가 걸러 준다 — 국세청·기획재정부·
행정안전부(지방세) 셋이면 사업자에게 걸리는 세법은 대부분 들어온다.

**본문은 첨부파일이다.**

목록이 주는 것은 제목·부처·공고번호·예고기간·파일 링크다. 본문은 한글
파일로 붙어 있고 우리는 그걸 열지 않는다. 그래서 여기서도 모델에게
요지를 쓰라고 시키지 않는다 — 제목과 기간까지만 말하고 원문으로 보낸다.

상세 API(`입법예고 상세 정보`)를 따로 신청해 두었다. 승인되면 제개정
사유와 주요 내용 요지가 오므로 그때 붙인다.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
LIST_URL = "https://www.lawmaking.go.kr/rest/ogLmPp.xml"

#: 사업자에게 걸리는 세법의 소관부처.
#:
#: 낱말이 아니라 부처로 거르는 이유 — "부가가치세" 가 제목에 없는 세법
#: 개정이 많다. 「조세특례제한법 시행령 일부개정령안」 같은 것이다.
#: 부처로 거르면 서버가 걸러 주고 우리가 놓칠 일이 없다.
AGENCIES: tuple[tuple[str, str], ...] = (
    ("1210000", "국세청"),
    ("1051000", "기획재정부"),
    # 지방세는 행정안전부 소관이다. 사장님에게는 국세와 같은 고지서다.
    ("1741000", "행정안전부"),
)

#: 예고 상태. 진행 중인 것이 먼저다 — 의견을 낼 수 있는 기간이 남아 있다.
ONGOING = "0"

#: 사람이 여는 화면. 목록은 일련번호만 주므로 여기서 만든다.
PUBLIC_URL = "https://opinion.lawmaking.go.kr/gcom/ogLmPp"


class PreannounceError(Exception):
    """입법예고 API 호출 실패."""


@dataclass(frozen=True)
class PreannounceItem:
    serial: str
    title: str
    law_type: str
    agency: str
    notice_no: str
    noticed_at: dt.date | None
    opens_at: dt.date | None
    closes_at: dt.date | None
    file_url: str

    @property
    def canonical_url(self) -> str:
        return f"{PUBLIC_URL}/{self.serial}"


def _parse_date(value: str | None) -> dt.date | None:
    """`2026.08.14.` → date. 형식이 다르면 None — 추측하지 않는다 (§9.4 V2).

    이 API 는 마침표로 끊고 끝에도 마침표를 붙인다. 법제처 심판례가
    점 구분이라 의결일이 전부 빈 적이 있어서, 여기서는 처음부터 받는다.
    """
    text = (value or "").strip().replace(".", "").replace("-", "").replace(" ", "")
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    return (found.text or "").strip() if found is not None else ""


def parse_list(xml: str) -> list[PreannounceItem]:
    """목록 XML 을 항목으로 가른다.

    승인 전에는 `<result><retMsg>401</retMsg></result>` 가 온다.
    그때 빈 목록을 돌려주면 "오늘은 예고가 없나 보다" 로 읽힌다.
    그건 사실이 아니므로 예외로 올린다.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PreannounceError(f"XML 을 파싱할 수 없습니다: {exc}") from exc

    message = _text(root, "retMsg")
    if message:
        raise PreannounceError(
            f"입법예고 API 가 거절했습니다 (retMsg={message}). "
            "국민참여입법센터 정보공개 신청이 승인됐는지, OC 가 맞는지 확인하세요."
        )

    out: list[PreannounceItem] = []
    # 항목 태그 이름이 문서에 없다. 일련번호를 가진 노드를 항목으로 본다 —
    # 이름을 하나로 못 박으면 그 이름이 바뀌는 날 조용히 0건이 된다.
    for node in root.iter():
        serial = _text(node, "ogLmPpSeq")
        title = _text(node, "lsNm")
        if not (serial and title):
            continue
        out.append(
            PreannounceItem(
                serial=serial,
                title=title,
                law_type=_text(node, "lsClsNm"),
                agency=_text(node, "asndOfiNm"),
                notice_no=_text(node, "pntcNo"),
                noticed_at=_parse_date(_text(node, "pntcDt")),
                opens_at=_parse_date(_text(node, "stYd")),
                closes_at=_parse_date(_text(node, "edYd")),
                file_url=_text(node, "FileDownLink"),
            )
        )
    return out


def build_body(item: PreannounceItem) -> str:
    """저장할 본문. 가진 것만 적는다."""
    lines = [f"[입법예고명]\n{item.title}"]
    if item.agency:
        lines.append(f"[소관부처]\n{item.agency}")
    if item.law_type:
        lines.append(f"[법령종류]\n{item.law_type}")
    if item.notice_no:
        lines.append(f"[공고번호]\n{item.notice_no}")
    if item.opens_at and item.closes_at:
        lines.append(f"[의견 제출 기간]\n{item.opens_at.isoformat()} ~ {item.closes_at.isoformat()}")
    lines.append(
        "[안내]\n아직 확정된 개정이 아닙니다. 정부가 이렇게 바꾸겠다고 내놓고 "
        "의견을 받는 단계이며, 이 기간에 내용이 달라지거나 무산될 수 있습니다. "
        "본문은 첨부된 원문에서 확인하세요."
    )
    return "\n\n".join(lines)


class PreannounceCollector:
    """입법예고."""

    name = "lawmaking.go.kr:preannounce"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 40.0) -> None:
        self.oc = get_settings().lawmaking_oc
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
        limit: int = 60,
    ) -> CollectStats:
        stats = CollectStats()

        if not self.configured:
            stats.fail(
                source.display_name,
                PreannounceError(
                    "TAXBRIEFING_LAWMAKING_OC 가 없습니다. "
                    "국민참여입법센터 정보공개 신청 후 승인받은 ID(@ 앞부분)를 넣으세요."
                ),
            )
            return stats

        picked = (source.settings or {}).get("agencies")
        agencies = tuple(a for a in AGENCIES if picked is None or a[0] in picked)
        seen: set[str] = set()

        for code, name in agencies:
            try:
                items = self._search(code)
            except PreannounceError as exc:
                stats.fail(f"{name}({code})", exc)
                continue

            for item in items:
                stats.discovered += 1
                if item.serial in seen:
                    continue
                seen.add(item.serial)

                # 공고일 기준으로 자른다. 예고는 기간이 짧아 오래된 것을
                # 다시 담을 이유가 없다.
                if since and item.noticed_at and item.noticed_at < since:
                    continue
                if len(seen) > limit:
                    break

                try:
                    self._ingest_one(db, source, item, stats)
                except Exception as exc:
                    stats.fail(item.notice_no or item.serial, exc)

        return stats

    def _search(self, agency_code: str) -> list[PreannounceItem]:
        client = self._client or httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": "TaxBriefing/1.0 (+tax briefing aggregator)"},
        )
        owns = self._client is None
        try:
            response = client.get(
                LIST_URL,
                params={"OC": self.oc, "cptOfiOrgCd": agency_code, "diff": ONGOING},
            )
        except httpx.HTTPError as exc:
            raise PreannounceError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise PreannounceError(f"HTTP {response.status_code}")
        return parse_list(response.text)

    def _ingest_one(
        self,
        db: Session,
        source: Source,
        item: PreannounceItem,
        stats: CollectStats,
    ) -> None:
        ingested = ingest(
            db,
            source_id=source.id,
            canonical_url=item.canonical_url,
            title=item.title[:500],
            publisher=item.agency or "법제처",
            raw_body=build_body(item),
            published_at=(
                dt.datetime.combine(item.noticed_at, dt.time(), tzinfo=dt.UTC)
                if item.noticed_at
                else None
            ),
            source_item_id=item.notice_no or item.serial,
            parser_version=f"preannounce/{ADAPTER_VERSION}",
        )

        ingested.version.doc_metadata = {
            "serial": item.serial,
            "notice_no": item.notice_no,
            "agency": item.agency,
            "law_type": item.law_type,
            "noticed_at": item.noticed_at.isoformat() if item.noticed_at else None,
            "opens_at": item.opens_at.isoformat() if item.opens_at else None,
            # 의견 제출 마감. 화면이 이 날짜로 D-day 를 센다 —
            # 이 기간이 지나면 의견을 낼 수 없다.
            "closes_at": item.closes_at.isoformat() if item.closes_at else None,
            "file_url": item.file_url,
            # 아직 법이 아니다. 공포도 시행도 안 됐다.
            "content_kind": "POLICY",
            "legal_status": "PREANNOUNCED",
            "full_text_stored": False,
        }
        db.flush()
        stats.record(ingested.outcome)


__all__ = [
    "AGENCIES",
    "PreannounceCollector",
    "PreannounceError",
    "PreannounceItem",
    "build_body",
    "parse_list",
]
