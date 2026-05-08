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
