from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


DEFAULT_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.marketwatch.com/rss/topstories",
]

MACRO_BUCKETS = {
    "policy": {
        "primary": {"fed", "federal reserve", "ecb", "boj", "central bank"},
        "secondary": {"rates", "rate", "cuts", "hike", "hikes", "easing", "tightening", "hawkish", "dovish"},
    },
    "inflation": {
        "primary": {"inflation", "cpi", "pce", "prices", "price pressures"},
        "secondary": {"sticky", "cooling", "hot", "disinflation", "consumer prices", "core inflation"},
    },
    "labor": {
        "primary": {"jobs", "job", "labor", "labour", "payrolls", "employment", "unemployment"},
        "secondary": {"wages", "hiring", "claims", "jobless", "worker", "labor market"},
    },
    "rates": {
        "primary": {"treasury", "treasuries", "yield", "yields", "bond", "bonds"},
        "secondary": {"curve", "duration", "long-end", "10-year", "2-year", "real yields"},
    },
    "growth": {
        "primary": {"economy", "economic", "growth", "recession", "gdp", "demand"},
        "secondary": {"slowdown", "soft landing", "consumer spending", "business activity", "manufacturing"},
    },
    "energy": {
        "primary": {"oil", "crude", "opec", "gas", "energy"},
        "secondary": {"supply", "production", "barrel", "geopolitical", "iran", "shipping"},
    },
    "liquidity": {
        "primary": {"liquidity", "credit", "funding", "spreads", "banking", "banks"},
        "secondary": {"stress", "default", "refinancing", "funding markets", "credit markets"},
    },
    "fx": {
        "primary": {"dollar", "usd", "yen", "euro", "fx", "currency"},
        "secondary": {"safe haven", "devaluation", "exchange rate", "foreign exchange"},
    },
}

LOW_SIGNAL_TERMS = {
    "microsoft",
    "oracle",
    "robinhood",
    "starbucks",
    "crypto",
    "ai boom",
    "trial",
    "earnings",
    "stock pick",
    "stock-picking",
    "investors should",
    "what investors",
    "buying crypto",
    "younger customers",
}


@dataclass
class FeedItem:
    id: str
    source: str
    feed_url: str
    published_at: str
    title: str
    body: str
    url: str
    macro_score: int = 0
    macro_buckets: list[str] | None = None


def fetch_url(url: str, timeout: int = 20) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "MacroSignalsAnalyzer/0.1 (+local rss fetcher)"
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_datetime(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def strip_tag(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def first_text(element: ET.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in element.iter():
        if strip_tag(child.tag) in wanted and child.text:
            text = child.text.strip()
            if text:
                return text
    return ""


def parse_feed(xml_bytes: bytes, feed_url: str) -> list[FeedItem]:
    root = ET.fromstring(xml_bytes)
    source = urlparse(feed_url).netloc
    items: list[FeedItem] = []

    for element in root.iter():
        tag = strip_tag(element.tag)
        if tag not in {"item", "entry"}:
            continue

        title = first_text(element, {"title"})
        body = first_text(element, {"description", "summary", "content"})
        link = first_text(element, {"link", "id"})
        published_at = parse_datetime(
            first_text(element, {"pubDate", "published", "updated"})
        )

        if not title:
            continue

        safe_ts = published_at.replace(":", "-")
        item_id = f"{source}-{safe_ts}-{len(items) + 1}"
        items.append(
            FeedItem(
                id=item_id,
                source=source,
                feed_url=feed_url,
                published_at=published_at,
                title=title,
                body=body,
                url=link,
            )
        )

    return items


def dedupe_items(items: list[FeedItem]) -> list[FeedItem]:
    seen: set[tuple[str, str]] = set()
    unique: list[FeedItem] = []

    for item in items:
        key = (item.source, item.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def count_matches(text: str, phrases: set[str]) -> int:
    return sum(1 for phrase in phrases if phrase in text)


def score_item(item: FeedItem) -> tuple[int, list[str]]:
    title_text = item.title.lower()
    body_text = item.body.lower()
    full_text = f"{title_text} {body_text}"

    score = 0
    matched_buckets: list[str] = []

    for bucket, config in MACRO_BUCKETS.items():
        title_primary = count_matches(title_text, config["primary"])
        title_secondary = count_matches(title_text, config["secondary"])
        body_primary = count_matches(body_text, config["primary"])
        body_secondary = count_matches(body_text, config["secondary"])

        bucket_score = 0
        if title_primary:
            bucket_score += 3
        if title_primary and (title_secondary or body_secondary):
            bucket_score += 2
        if title_primary >= 2:
            bucket_score += 1
        if body_primary and title_secondary:
            bucket_score += 1
        if body_primary >= 2:
            bucket_score += 1
        if title_secondary >= 2:
            bucket_score += 1

        if bucket_score > 0:
            matched_buckets.append(bucket)
            score += bucket_score

    for term in LOW_SIGNAL_TERMS:
        if term in full_text:
            score -= 2

    if "marketwatch" in item.source and score < 4:
        score -= 1

    return score, matched_buckets


def filter_items(items: list[FeedItem], keywords: list[str] | None) -> list[FeedItem]:
    if keywords is None:
        return items

    if not keywords:
        scored = []
        for item in items:
            score, matched_buckets = score_item(item)
            item.macro_score = score
            item.macro_buckets = matched_buckets
            if score >= 4 and matched_buckets:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    wanted = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
    if not wanted:
        return items

    filtered: list[FeedItem] = []
    for item in items:
        haystack = f"{item.title} {item.body}".lower()
        if any(keyword in haystack for keyword in wanted):
            score, matched_buckets = score_item(item)
            item.macro_score = score
            item.macro_buckets = matched_buckets
            filtered.append(item)
    return filtered


def save_items(items: list[FeedItem], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = [
        {
            "id": item.id,
            "source": item.source,
            "feed_url": item.feed_url,
            "published_at": item.published_at,
            "title": item.title,
            "body": item.body,
            "url": item.url,
            "macro_score": item.macro_score,
            "macro_buckets": item.macro_buckets or [],
        }
        for item in items
    ]
    output.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    return output


def fetch_feeds(feeds: list[str]) -> tuple[list[FeedItem], list[str]]:
    all_items: list[FeedItem] = []
    errors: list[str] = []

    for feed in feeds:
        try:
            xml_bytes = fetch_url(feed)
            all_items.extend(parse_feed(xml_bytes, feed))
        except (URLError, TimeoutError, ET.ParseError) as exc:
            errors.append(f"{feed}: {exc}")

    return dedupe_items(all_items), errors


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Fetch RSS news for the analyzer.")
    parser.add_argument(
        "--output",
        default=str(project_root / "data" / "latest_news.json"),
        help="Where to save the fetched items.",
    )
    parser.add_argument(
        "--feed",
        action="append",
        dest="feeds",
        help="Add a custom RSS feed URL. Can be used multiple times.",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        dest="keywords",
        help="Add a custom keyword filter. Can be used multiple times.",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Disable the default macro relevance filter.",
    )
    args = parser.parse_args()

    feeds = args.feeds or DEFAULT_FEEDS
    keywords = None if args.no_filter else (args.keywords or [])
    items, errors = fetch_feeds(feeds)
    items = filter_items(items, keywords)
    output_path = save_items(items, args.output)

    print(f"Saved {len(items)} items to {output_path}")
    if errors:
        print("")
        print("Feeds with errors:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
