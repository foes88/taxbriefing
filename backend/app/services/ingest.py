"""원문 수집·정규화·버전 판정 (§3.5, §3.6, FR-SRC-004, FR-NRM-001, FR-NRM-004).

AT-01: 동일 게시물을 3회 수집해도 raw_content 는 1개이고 실행이력만 증가한다.
AT-02: 원문 본문이 변경되면 새 raw_content_version 과 diff 가 생성된다.
"""

from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import RawContent, RawContentVersion

PARSER_VERSION = "1.0.0"

# 정규화에서 제거할 반복 문구 (FR-NRM-001).
_BOILERPLATE = re.compile(
    r"^\s*(목록으로|이전글|다음글|인쇄하기|공유하기|첨부파일 다운로드|맨위로)\s*$",
    re.MULTILINE,
)
_MULTI_BLANK = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_text(raw: str) -> str:
    """본문 정규화. 문단 구조는 보존한다 (FR-NRM-001).

    해시가 정규화 결과 위에서 계산되므로, 여기서 공백 처리가 흔들리면
    같은 문서가 매번 '변경됨'으로 잡힌다.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _BOILERPLATE.sub("", text)
    text = _TRAILING_WS.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def content_hash(normalized: str) -> str:
    """정규화 본문 SHA-256 (§3.5)."""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    """URL 정규화. 추적 파라미터와 fragment 를 제거해 중복 판정을 안정시킨다."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid"}
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in tracking]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(sorted(query)),
            "",
        )
    )


class IngestOutcome(StrEnum):
    NEW = "NEW"
    """처음 보는 원문. raw_content 와 v1 을 만들었다."""

    CHANGED = "CHANGED"
    """기존 원문의 내용이 바뀌었다. 새 버전을 만들었다."""

    UNCHANGED = "UNCHANGED"
    """같은 내용. last_checked_at 만 갱신했다 (AT-01)."""

    REVERTED = "REVERTED"
    """과거 버전과 같은 내용으로 되돌아갔다 (§7.4 D-03). 새 버전을 만들지 않는다."""


@dataclass
class IngestResult:
    outcome: IngestOutcome
    raw_content: RawContent
    version: RawContentVersion
    diff: str | None = None

    @property
    def created_version(self) -> bool:
        return self.outcome in (IngestOutcome.NEW, IngestOutcome.CHANGED)


def _diff(before: str, after: str, *, from_label: str, to_label: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
            n=2,
        )
    )


def ingest(
    db: Session,
    *,
    source_id: UUID,
    canonical_url: str,
    title: str,
    publisher: str,
    raw_body: str,
    published_at: dt.datetime | None = None,
    source_item_id: str | None = None,
    raw_html: str | None = None,
    http_etag: str | None = None,
    http_last_modified: str | None = None,
    now: dt.datetime | None = None,
    parser_version: str = PARSER_VERSION,
) -> IngestResult:
    """원문 하나를 수집·저장한다. 멱등적이다.

    판정 순서 (§3.6):
      1차 동일성 — source_id + canonical_url 로 기존 raw_content 를 찾는다.
      2차 동일성 — 정규화 본문 해시로 신규/변경/동일을 가른다.
    """
    now = now or dt.datetime.now(dt.UTC)
    url = canonicalize_url(canonical_url)
    normalized = normalize_text(raw_body)
    digest = content_hash(normalized)

    existing = db.execute(
        select(RawContent).where(
            RawContent.source_id == source_id,
            RawContent.canonical_url == url,
        )
    ).scalar_one_or_none()

    if existing is None:
        raw = RawContent(
            source_id=source_id,
            source_item_id=source_item_id,
            canonical_url=url,
            title=title,
            publisher=publisher,
            published_at=published_at,
            first_collected_at=now,
            last_checked_at=now,
        )
        db.add(raw)
        db.flush()

        version = RawContentVersion(
            raw_content_id=raw.id,
            version_no=1,
            content_hash=digest,
            raw_html=raw_html,
            normalized_text=normalized,
            http_etag=http_etag,
            http_last_modified=http_last_modified,
            parser_version=parser_version,
            collected_at=now,
        )
        db.add(version)
        db.flush()

        raw.current_version_id = version.id
        db.flush()
        return IngestResult(IngestOutcome.NEW, raw, version)

    # 기존 원문이 있다. 재수집이므로 확인 시각은 항상 갱신한다 (AT-01).
    existing.last_checked_at = now
    if published_at is not None:
        existing.published_at = published_at
    if source_item_id and not existing.source_item_id:
        existing.source_item_id = source_item_id

    versions = db.execute(
        select(RawContentVersion)
        .where(RawContentVersion.raw_content_id == existing.id)
        .order_by(RawContentVersion.version_no)
    ).scalars().all()

    current = next((v for v in versions if v.id == existing.current_version_id), None)
    if current is not None and current.content_hash == digest:
        # 같은 내용. 새 버전을 만들지 않는다 — AT-01 의 핵심.
        current.http_etag = http_etag or current.http_etag
        current.http_last_modified = http_last_modified or current.http_last_modified
        db.flush()
        return IngestResult(IngestOutcome.UNCHANGED, existing, current)

    prior = next((v for v in versions if v.content_hash == digest), None)
    if prior is not None:
        # 과거 버전으로 되돌아갔다 (D-03). UNIQUE(raw_content_id, content_hash) 때문에
        # 새 행을 만들 수 없고, 만들 이유도 없다. 현재 버전 포인터만 옮긴다.
        existing.current_version_id = prior.id
        db.flush()
        return IngestResult(
            IngestOutcome.REVERTED,
            existing,
            prior,
            diff=_diff(
                current.normalized_text if current else "",
                normalized,
                from_label=f"v{current.version_no}" if current else "(none)",
                to_label=f"v{prior.version_no}",
            ),
        )

    next_no = max((v.version_no for v in versions), default=0) + 1
    version = RawContentVersion(
        raw_content_id=existing.id,
        version_no=next_no,
        content_hash=digest,
        raw_html=raw_html,
        normalized_text=normalized,
        http_etag=http_etag,
        http_last_modified=http_last_modified,
        parser_version=parser_version,
        collected_at=now,
    )
    db.add(version)
    db.flush()

    diff_text = _diff(
        current.normalized_text if current else "",
        normalized,
        from_label=f"v{current.version_no}" if current else "(none)",
        to_label=f"v{next_no}",
    )
    existing.current_version_id = version.id
    existing.title = title
    db.flush()

    return IngestResult(IngestOutcome.CHANGED, existing, version, diff=diff_text)


def version_diff(db: Session, *, from_version_id: UUID, to_version_id: UUID) -> str:
    """두 원문 버전의 diff (FR-NRM-004, AT-02)."""
    a = db.get(RawContentVersion, from_version_id)
    b = db.get(RawContentVersion, to_version_id)
    if a is None or b is None:
        raise ValueError("원문 버전을 찾을 수 없습니다.")
    return _diff(
        a.normalized_text, b.normalized_text,
        from_label=f"v{a.version_no}", to_label=f"v{b.version_no}",
    )
