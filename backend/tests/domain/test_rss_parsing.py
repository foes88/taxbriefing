"""RSS/Atom 파싱 단위 테스트. 네트워크·DB 없이 실행된다."""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.collectors.rss import MAX_SUMMARY_CHARS, RssError, parse_feed

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>\xec\x84\xb8\xec\xa0\x95\xec\x9d\xbc\xeb\xb3\xb4</title>
    <item>
      <title>\xea\xb0\x80\xea\xb3\xb5\xea\xb1\xb0\xeb\x9e\x98 \xed\x98\x90\xec\x9d\x98</title>
      <link>https://example.test/news/1</link>
      <pubDate>Wed, 06 Aug 2026 09:30:00 +0900</pubDate>
      <description>&lt;p&gt;\xeb\xb3\xb8\xeb\xac\xb8
        \xec\x95\x9e\xeb\xb6\x80\xeb\xb6\x84&lt;/p&gt;</description>
    </item>
    <item>
      <title>\xeb\x91\x90 \xeb\xb2\x88\xec\xa7\xb8</title>
      <link>https://example.test/news/2</link>
    </item>
  </channel>
</rss>"""

ATOM_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom entry</title>
    <link href="https://example.test/atom/1"/>
    <updated>2026-08-06T00:30:00Z</updated>
    <summary>summary text</summary>
  </entry>
</feed>"""


class TestParseFeed:
    def test_parses_rss_items(self):
        items = parse_feed(RSS_SAMPLE)
        assert len(items) == 2
        assert items[0].link == "https://example.test/news/1"
        assert items[0].title == "가공거래 혐의"

    def test_strips_html_from_summary(self):
        """피드 요약에 태그가 섞여 온다. 그대로 저장하면 화면에 태그가 보인다."""
        items = parse_feed(RSS_SAMPLE)
        assert "<p>" not in items[0].summary
        assert items[0].summary == "본문 앞부분"

    def test_parses_rfc822_date_as_utc(self):
        items = parse_feed(RSS_SAMPLE)
        assert items[0].published_at == dt.datetime(2026, 8, 6, 0, 30, tzinfo=dt.UTC)

    def test_missing_date_is_none_not_guessed(self):
        """틀린 날짜는 없는 날짜보다 나쁘다 (§9.4 V2)."""
        items = parse_feed(RSS_SAMPLE)
        assert items[1].published_at is None

    def test_parses_atom(self):
        items = parse_feed(ATOM_SAMPLE)
        assert len(items) == 1
        assert items[0].link == "https://example.test/atom/1"
        assert items[0].published_at == dt.datetime(2026, 8, 6, 0, 30, tzinfo=dt.UTC)

    def test_item_without_link_is_dropped(self):
        feed = b"""<?xml version="1.0"?><rss><channel>
            <item><title>no link</title></item>
        </channel></rss>"""
        assert parse_feed(feed) == []

    def test_summary_is_truncated(self):
        long = "가" * 900
        feed = f"""<?xml version="1.0" encoding="UTF-8"?><rss><channel>
            <item><title>t</title><link>https://e.test/1</link>
            <description>{long}</description></item>
        </channel></rss>""".encode()
        assert len(parse_feed(feed)[0].summary) <= MAX_SUMMARY_CHARS

    def test_broken_xml_raises(self):
        with pytest.raises(RssError):
            parse_feed(b"<rss><channel>")
