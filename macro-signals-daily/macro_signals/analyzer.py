from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


SIGNAL_LEXICON = {
    "inflation": {
        "positive": {
            "inflation rises",
            "inflation accelerates",
            "sticky prices",
            "hot cpi",
            "price pressures",
            "oil jumps",
            "wage pressures",
        },
        "negative": {
            "inflation cools",
            "disinflation",
            "prices eased",
            "cooling inflation",
            "softer prices",
        },
    },
    "growth": {
        "positive": {
            "growth accelerates",
            "consumer demand",
            "strong demand",
            "hiring picks up",
            "expansion",
            "resilient spending",
        },
        "negative": {
            "growth slows",
            "weaker growth",
            "demand slows",
            "retail spending softened",
            "softer survey data",
            "recession risk",
            "labor market softens",
        },
    },
    "policy": {
        "positive": {
            "restrictive",
            "hawkish",
            "rates may stay high",
            "delay easing",
            "cautious",
        },
        "negative": {
            "dovish",
            "easing",
            "rate cuts",
            "policy support",
            "patience",
        },
    },
    "liquidity": {
        "positive": {
            "funding stress",
            "tight liquidity",
            "credit stress",
            "spreads widened",
        },
        "negative": {
            "liquidity improved",
            "stress fades",
            "spreads narrowed",
            "funding conditions improve",
            "stabilized",
        },
    },
    "risk": {
        "positive": {
            "risk concerns",
            "markets turned cautious",
            "geopolitical tensions",
            "defensive positioning",
            "supply disruption",
        },
        "negative": {
            "risk appetite",
            "optimism",
            "stocks rally",
            "sentiment improves",
        },
    },
}


THEME_KEYWORDS = {
    "inflation": {"inflation", "prices", "cpi", "oil", "wage"},
    "growth": {"growth", "demand", "spending", "labor", "hiring", "recession"},
