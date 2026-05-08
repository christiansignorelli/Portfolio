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
    "policy": {"fed", "ecb", "rates", "policymakers", "central bank"},
    "liquidity": {"liquidity", "funding", "credit", "spreads", "bank"},
    "risk": {"risk", "geopolitical", "tensions", "cautious", "defensive"},
}


@dataclass
class DocumentSignal:
    doc_id: str
    date: str
    source: str
    feed_url: str
    title: str
    themes: list[str]
    scores: dict[str, int]
    confidence: str
    summary_label: str
    macro_score: int
    macro_buckets: list[str]


@dataclass
class BucketView:
    name: str
    score: int
    label: str
    documents: list[DocumentSignal]


@dataclass
class MarketSnapshot:
    symbol: str
    label: str
    as_of: str
    close: float
    return_1d: float
    return_5d: float


@dataclass
class MarketCheck:
    label: str
    expected: str
    confirmed: bool


def load_documents(path: str | Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_market_data(path: str | Path | None) -> list[MarketSnapshot]:
    if not path:
        return []

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    return [
        MarketSnapshot(
            symbol=item["symbol"],
            label=item["label"],
            as_of=item["as_of"],
            close=float(item["close"]),
            return_1d=float(item["return_1d"]),
            return_5d=float(item["return_5d"]),
        )
        for item in payload.get("snapshots", [])
    ]


def normalize_text(document: dict[str, Any]) -> str:
    return " ".join(
        str(document.get(field, "")).strip().lower()
        for field in ("title", "body")
    )


def extract_date(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.date().isoformat()


def detect_themes(text: str) -> list[str]:
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            themes.append(theme)
    return themes or ["uncategorized"]


def score_theme(text: str, theme: str) -> int:
    if theme not in SIGNAL_LEXICON:
        return 0

    score = 0
    for phrase in SIGNAL_LEXICON[theme]["positive"]:
        if phrase in text:
            score += 1
    for phrase in SIGNAL_LEXICON[theme]["negative"]:
        if phrase in text:
            score -= 1
    return max(-2, min(2, score))


def infer_confidence(themes: list[str], scores: dict[str, int]) -> str:
    non_zero = sum(1 for value in scores.values() if value != 0)
    if non_zero >= 3:
        return "high"
    if non_zero >= 1 or (themes and themes != ["uncategorized"]):
        return "medium"
    return "low"


def build_summary_label(scores: dict[str, int]) -> str:
    strongest = [
        (theme, abs(score), score)
        for theme, score in scores.items()
        if score != 0
    ]
    if not strongest:
        return "neutral-mixed"

    theme, _, score = max(strongest, key=lambda item: item[1])
    direction = "up" if score > 0 else "down"
    return f"{theme}-{direction}"


def analyze_document(document: dict[str, Any]) -> DocumentSignal:
    text = normalize_text(document)
    themes = detect_themes(text)
    scores = {
        theme: score_theme(text, theme)
        for theme in SIGNAL_LEXICON
    }

    return DocumentSignal(
        doc_id=document["id"],
        date=extract_date(document["published_at"]),
        source=document.get("source", "unknown"),
        feed_url=document.get("feed_url", ""),
        title=document.get("title", ""),
        themes=themes,
        scores=scores,
        confidence=infer_confidence(themes, scores),
        summary_label=build_summary_label(scores),
        macro_score=int(document.get("macro_score", 0) or 0),
        macro_buckets=list(document.get("macro_buckets", []) or []),
    )


def aggregate_by_date(signals: list[DocumentSignal]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for signal in signals:
        bucket = grouped.setdefault(
            signal.date,
            {
                "scores": defaultdict(int),
                "theme_counts": Counter(),
                "documents": [],
            },
        )
        for theme, score in signal.scores.items():
            bucket["scores"][theme] += score
        for theme in signal.themes:
            bucket["theme_counts"][theme] += 1
        bucket["documents"].append(signal)

    return grouped


def describe_score(theme: str, score: int) -> str:
    if theme == "policy":
        if score >= 2:
            return "hawkish"
        if score <= -2:
            return "dovish"
        if score > 0:
            return "mildly hawkish"
        if score < 0:
            return "mildly dovish"
        return "neutral"

    if theme == "liquidity":
        if score >= 2:
            return "tightening"
        if score <= -2:
            return "improving"
        if score > 0:
            return "slightly tighter"
        if score < 0:
            return "slightly improving"
        return "neutral"

    if theme == "risk":
        if score >= 2:
            return "risk-off"
        if score <= -2:
            return "risk-on"
        if score > 0:
            return "slightly risk-off"
        if score < 0:
            return "slightly risk-on"
        return "neutral"

    if score >= 2:
        return "rising"
    if score <= -2:
        return "falling"
    if score > 0:
        return "slightly up"
    if score < 0:
        return "slightly down"
    return "neutral"


def describe_bucket(bucket: str, score: int) -> str:
    bucket_map = {
        "policy": describe_score("policy", score),
        "inflation": describe_score("inflation", score),
        "labor": describe_score("growth", score),
        "rates": describe_score("growth", score),
        "growth": describe_score("growth", score),
        "energy": describe_score("inflation", score),
        "liquidity": describe_score("liquidity", score),
        "fx": describe_score("risk", score),
        "risk": describe_score("risk", score),
    }
    return bucket_map.get(bucket, "neutral")


def pick_bucket_score(bucket: str, scores: dict[str, int]) -> int:
    mapping = {
        "policy": "policy",
        "inflation": "inflation",
        "labor": "growth",
        "rates": "growth",
        "growth": "growth",
        "energy": "inflation",
        "liquidity": "liquidity",
        "fx": "risk",
        "risk": "risk",
    }
    return scores[mapping.get(bucket, "risk")]


def build_daily_brief(date: str, daily_data: dict[str, Any]) -> str:
    scores = daily_data["scores"]
    inflation = describe_score("inflation", scores["inflation"])
    growth = describe_score("growth", scores["growth"])
    policy = describe_score("policy", scores["policy"])
    liquidity = describe_score("liquidity", scores["liquidity"])
    risk = describe_score("risk", scores["risk"])

    top_theme = "none"
    if daily_data["theme_counts"]:
        top_theme = daily_data["theme_counts"].most_common(1)[0][0]

    return (
        f"{date}: inflation {inflation}, growth {growth}, policy {policy}, "
        f"liquidity {liquidity}, risk {risk}. Top theme: {top_theme}."
    )


def build_day_conclusion(daily_data: dict[str, Any]) -> str:
    scores = daily_data["scores"]
    signals: list[str] = []

    if scores["policy"] > 0:
        signals.append("hawkish policy tone")
    elif scores["policy"] < 0:
        signals.append("easing policy tone")

    if scores["inflation"] > 0:
        signals.append("inflation pressure")
    elif scores["inflation"] < 0:
        signals.append("cooling inflation")

    if scores["growth"] > 0:
        signals.append("firmer growth tone")
    elif scores["growth"] < 0:
        signals.append("softening growth tone")

    if scores["risk"] > 0:
        signals.append("defensive risk backdrop")
    elif scores["risk"] < 0:
        signals.append("risk appetite improving")

    if scores["liquidity"] > 0:
        signals.append("tighter liquidity conditions")
    elif scores["liquidity"] < 0:
        signals.append("liquidity conditions improving")

    visible_themes = [
        theme
        for theme, count in daily_data["theme_counts"].most_common()
        if theme != "uncategorized" and count > 0
    ]

    if not daily_data["documents"]:
        return (
            "Macro read: no qualifying macro headlines were available from the examined feeds."
        )

    if not signals:
        if visible_themes:
            theme_text = ", ".join(visible_themes[:3])
            return (
                "Macro read: no strong daily signal. "
                f"The examined feeds showed scattered or non-aligned language around {theme_text}, "
                "but not enough alignment to support a confident macro view."
            )
        return (
            "Macro read: no strong daily signal. "
            "The examined feeds did not provide enough aligned macro language to support a confident interpretation."
        )

    return f"Macro read: {', '.join(signals[:3])}."


def build_market_map(market_data: list[MarketSnapshot]) -> dict[str, MarketSnapshot]:
    return {snapshot.symbol: snapshot for snapshot in market_data}


def summarize_market(snapshot: MarketSnapshot) -> str:
    sign_1d = "+" if snapshot.return_1d > 0 else ""
    sign_5d = "+" if snapshot.return_5d > 0 else ""
    return f"{snapshot.symbol} {sign_1d}{snapshot.return_1d:.2f}% 1d, {sign_5d}{snapshot.return_5d:.2f}% 5d"


def build_market_checks(
    daily_scores: dict[str, int], market_map: dict[str, MarketSnapshot]
) -> list[MarketCheck]:
    checks: list[MarketCheck] = []

    tlt = market_map.get("TLT")
    spy = market_map.get("SPY")
    uso = market_map.get("USO")
    uup = market_map.get("UUP")
    hyg = market_map.get("HYG")

    if daily_scores["policy"] > 0:
        if tlt and uup:
            checks.append(
                MarketCheck(
                    label="hawkish policy",
                    expected="expects bonds weaker and dollar firmer",
                    confirmed=tlt.return_1d < 0 and uup.return_1d > 0,
                )
            )
    elif daily_scores["policy"] < 0:
        if tlt and uup:
            checks.append(
                MarketCheck(
                    label="easing policy",
                    expected="expects bonds stronger and dollar flat to weaker",
                    confirmed=tlt.return_1d > 0 and uup.return_1d <= 0,
                )
            )

    if daily_scores["inflation"] > 0:
        if uso and tlt:
            checks.append(
                MarketCheck(
                    label="inflation pressure",
                    expected="expects oil stronger and bonds weaker",
                    confirmed=uso.return_1d > 0 and tlt.return_1d < 0,
                )
            )
    elif daily_scores["inflation"] < 0:
        if tlt:
            checks.append(
                MarketCheck(
                    label="cooling inflation",
                    expected="expects bonds stronger",
                    confirmed=tlt.return_1d > 0,
                )
            )

    if daily_scores["growth"] < 0:
        if tlt and spy:
            checks.append(
                MarketCheck(
                    label="softening growth",
                    expected="expects bonds stronger and equities softer",
                    confirmed=tlt.return_1d > 0 and spy.return_1d <= 0,
                )
            )
    elif daily_scores["growth"] > 0:
        if spy and hyg:
            checks.append(
                MarketCheck(
                    label="firmer growth",
                    expected="expects equities and credit stronger",
                    confirmed=spy.return_1d > 0 and hyg.return_1d >= 0,
                )
            )

    if daily_scores["risk"] > 0:
        if spy and hyg:
            checks.append(
                MarketCheck(
                    label="risk-off",
                    expected="expects equities and high-yield credit weaker",
                    confirmed=spy.return_1d < 0 and hyg.return_1d < 0,
                )
            )
    elif daily_scores["risk"] < 0:
        if spy and hyg:
            checks.append(
                MarketCheck(
                    label="risk-on",
                    expected="expects equities and high-yield credit stronger",
                    confirmed=spy.return_1d > 0 and hyg.return_1d >= 0,
                )
            )

    return checks


def assess_market_confirmation(
    daily_scores: dict[str, int], market_map: dict[str, MarketSnapshot]
) -> tuple[str, list[MarketCheck]]:
    if not market_map:
        return (
            "Market check: no market data was available for this run.",
            [],
        )

    checks = build_market_checks(daily_scores, market_map)

    if not checks:
        return (
            "Market check: no clear macro narrative was strong enough to test against market proxies today.",
            [],
        )

    hits = sum(1 for check in checks if check.confirmed)
    total = len(checks)
    matched_labels = [check.label for check in checks if check.confirmed]

    if matched_labels:
        primary_label = matched_labels[0]
    else:
        primary_label = checks[0].label

    if hits == total:
        return (
            f"Market check: price action broadly confirms today's {primary_label} narrative.",
            checks,
        )
    if hits == 0:
        return (
            "Market check: price action is diverging from today's narrative.",
            checks,
        )
    return (
        f"Market check: mixed confirmation, with {hits} of {total} market checks aligned.",
        checks,
    )


def group_documents_by_bucket(documents: list[DocumentSignal]) -> dict[str, list[DocumentSignal]]:
    grouped: dict[str, list[DocumentSignal]] = defaultdict(list)
    for document in documents:
        buckets = document.macro_buckets or [
            theme for theme in document.themes if theme != "uncategorized"
        ]
        if not buckets:
            buckets = [document.summary_label.split("-", 1)[0]]
        for bucket in buckets:
            grouped[bucket].append(document)

    for bucket, docs in grouped.items():
        grouped[bucket] = sorted(
            docs,
            key=lambda doc: (doc.macro_score, doc.confidence == "high", doc.title),
            reverse=True,
        )

    return grouped


def build_bucket_views(
    documents: list[DocumentSignal], daily_scores: dict[str, int]
) -> list[BucketView]:
    bucket_groups = group_documents_by_bucket(documents)
    views: list[BucketView] = []

    for bucket, docs in bucket_groups.items():
        bucket_score = pick_bucket_score(bucket, daily_scores)
        views.append(
            BucketView(
                name=bucket,
                score=bucket_score,
                label=describe_bucket(bucket, bucket_score),
                documents=docs,
            )
        )

    views.sort(
        key=lambda view: (
            abs(view.score),
            len(view.documents),
            max((doc.macro_score for doc in view.documents), default=0),
        ),
        reverse=True,
    )
    return views


def select_priority_buckets(bucket_views: list[BucketView], limit: int = 4) -> list[BucketView]:
    priority = [view for view in bucket_views if abs(view.score) > 0]
    if len(priority) < limit:
        seen = {view.name for view in priority}
        for view in bucket_views:
            if view.name in seen:
                continue
            priority.append(view)
            if len(priority) >= limit:
                break
    return priority[:limit]


def format_debug_document(signal: DocumentSignal) -> str:
    scores = ", ".join(
        f"{theme}={score}"
        for theme, score in signal.scores.items()
        if score != 0
    ) or "all=0"
    buckets = ", ".join(signal.macro_buckets) if signal.macro_buckets else "none"
    return (
        f"- {signal.title}\n"
        f"  source={signal.source} | confidence={signal.confidence} | "
        f"summary={signal.summary_label} | macro_score={signal.macro_score}\n"
        f"  buckets={buckets}\n"
        f"  scores={scores}"
    )


def build_report_data(
    signals: list[DocumentSignal],
    market_data: list[MarketSnapshot] | None = None,
    debug: bool = False,
) -> list[dict[str, Any]]:
    grouped = aggregate_by_date(signals)
    market_map = build_market_map(market_data or [])
    reports: list[dict[str, Any]] = []

    for date in sorted(grouped):
        daily_data = grouped[date]
        bucket_views = build_bucket_views(daily_data["documents"], daily_data["scores"])
        selected_buckets = bucket_views if debug else select_priority_buckets(bucket_views)

        report_entry = {
            "date": date,
            "daily_brief": build_daily_brief(date, daily_data),
            "macro_read": build_day_conclusion(daily_data),
            "market_confirmation": None,
            "market_checks": [],
            "feed_sources": sorted(
                {
                    signal.feed_url
                    for signal in daily_data["documents"]
                    if signal.feed_url
                }
            ),
            "market_snapshot": [
                {
                    "symbol": symbol,
                    "label": market_map[symbol].label,
                    "return_1d": market_map[symbol].return_1d,
                    "return_5d": market_map[symbol].return_5d,
                    "close": market_map[symbol].close,
                }
                for symbol in ("SPY", "TLT", "UUP", "USO", "HYG", "GLD")
                if symbol in market_map
            ],
            "bucket_views": [
                {
                    "name": bucket_view.name,
                    "label": bucket_view.label,
                    "score": bucket_view.score,
                    "documents": [
                        {
                            "title": signal.title,
                            "source": signal.source,
                            "confidence": signal.confidence,
                            "summary_label": signal.summary_label,
                            "macro_score": signal.macro_score,
                            "macro_buckets": signal.macro_buckets,
                            "scores": signal.scores,
                        }
                        for signal in bucket_view.documents[:3]
                    ],
                }
                for bucket_view in selected_buckets
            ],
            "debug_documents": [
                {
                    "title": signal.title,
                    "source": signal.source,
                    "confidence": signal.confidence,
                    "summary_label": signal.summary_label,
                    "macro_score": signal.macro_score,
                    "macro_buckets": signal.macro_buckets,
                    "scores": signal.scores,
                }
                for signal in daily_data["documents"]
            ]
            if debug
            else [],
        }
        if market_map:
            market_confirmation, market_checks = assess_market_confirmation(
                daily_data["scores"], market_map
            )
            report_entry["market_confirmation"] = market_confirmation
            report_entry["market_checks"] = [
                {
                    "label": check.label,
                    "expected": check.expected,
                    "confirmed": check.confirmed,
                }
                for check in market_checks
            ]
        reports.append(report_entry)

    return reports


def render_report(
    signals: list[DocumentSignal],
    market_data: list[MarketSnapshot] | None = None,
    debug: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("MACRO SIGNALS REPORT")
    lines.append("")

    for report in build_report_data(signals, market_data=market_data, debug=debug):
        lines.append(report["daily_brief"])
        lines.append(report["macro_read"])
        if report["market_confirmation"]:
            lines.append(report["market_confirmation"])
            lines.append(
                "Market snapshot: "
                + "; ".join(
                    f"{item['symbol']} "
                    f"{'+' if item['return_1d'] > 0 else ''}{item['return_1d']:.2f}% 1d, "
                    f"{'+' if item['return_5d'] > 0 else ''}{item['return_5d']:.2f}% 5d"
                    for item in report["market_snapshot"]
                    if item["symbol"] in {"SPY", "TLT", "UUP", "USO", "HYG"}
                )
            )
        lines.append("")

        for bucket_view in report["bucket_views"]:
            lines.append(f"{bucket_view['name'].upper()} | {bucket_view['label']}")
            for signal in bucket_view["documents"]:
                extra = ""
                if signal["macro_score"] and debug:
                    extra = f" | macro_score={signal['macro_score']}"
                lines.append(f"- {signal['title']}{extra}")
            lines.append("")

        if debug:
            lines.append("Debug documents:")
            for signal in report["debug_documents"]:
                debug_signal = DocumentSignal(
                    doc_id="debug",
                    date=report["date"],
                    source=signal["source"],
                    feed_url="",
                    title=signal["title"],
                    themes=[],
                    scores=signal["scores"],
                    confidence=signal["confidence"],
                    summary_label=signal["summary_label"],
                    macro_score=signal["macro_score"],
                    macro_buckets=signal["macro_buckets"],
                )
                lines.append(format_debug_document(debug_signal))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_analysis(
    path: str | Path,
    market_path: str | Path | None = None,
    debug: bool = False,
) -> str:
    documents = load_documents(path)
    signals = [analyze_document(doc) for doc in documents]
    market_data = load_market_data(market_path)
    return render_report(signals, market_data=market_data, debug=debug)
