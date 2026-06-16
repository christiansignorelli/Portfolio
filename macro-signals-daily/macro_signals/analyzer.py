from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
from typing import Any


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
    sentiment_label: str
    sentiment_confidence: float
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


class FinBERTError(RuntimeError):
    """Raised when FinBERT sentiment analysis cannot complete."""


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


def prepare_finbert_text(document: dict[str, Any]) -> str:
    title = str(document.get("title", "")).strip()
    body = str(document.get("body", "")).strip()
    if not title and not body:
        return ""
    if not body:
        return title
    if not title:
        return body[:1500]
    return f"{title}. {body[:1500]}".strip()


def extract_date(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.date().isoformat()


def detect_themes(text: str) -> list[str]:
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            themes.append(theme)
    return themes or ["uncategorized"]


@lru_cache(maxsize=1)
def get_finbert_pipeline() -> Any:
    try:
        from transformers import pipeline
        import torch  # noqa: F401
        import safetensors  # noqa: F401
    except ImportError as exc:
        raise FinBERTError(
            "Missing dependencies for FinBERT sentiment analysis. "
            "Install transformers, torch, and safetensors."
        ) from exc

    try:
        return pipeline(
            task="sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1,
        )
    except OSError as exc:
        raise FinBERTError(
            "FinBERT model download failure. Confirm network access and that "
            "ProsusAI/finbert is available from Hugging Face."
        ) from exc
    except Exception as exc:
        raise FinBERTError(
            "FinBERT model load failure. Confirm the installed transformers, "
            "torch, and safetensors versions are compatible."
        ) from exc


def confidence_bucket(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.65:
        return "medium"
    return "low"


def sentiment_score_from_label(label: str, confidence: float) -> int:
    normalized_label = label.lower()
    if normalized_label == "positive":
        return 2 if confidence >= 0.85 else 1
    if normalized_label == "negative":
        return -2 if confidence >= 0.85 else -1
    if normalized_label == "neutral":
        return 0
    raise FinBERTError(
        "Inference failure: FinBERT returned an unknown sentiment label "
        f"{label!r}."
    )


def score_sentiment(text: str) -> tuple[int, str, float]:
    if not isinstance(text, str) or not text.strip():
        raise FinBERTError(
            "Invalid input for FinBERT sentiment analysis: text must be a "
            "non-empty string."
        )

    try:
        result = get_finbert_pipeline()(
            text,
            truncation=True,
            max_length=512,
        )
    except FinBERTError:
        raise
    except ValueError as exc:
        raise FinBERTError(
            "Invalid input for FinBERT sentiment analysis: the supplied text "
            "could not be processed."
        ) from exc
    except Exception as exc:
        raise FinBERTError(
            "Inference failure: FinBERT could not score the supplied text."
        ) from exc

    prediction = result[0] if isinstance(result, list) and result else result
    if not isinstance(prediction, dict):
        raise FinBERTError(
            "Inference failure: FinBERT returned an unexpected result format."
        )

    try:
        label = str(prediction["label"]).lower()
        confidence = float(prediction["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FinBERTError(
            "Inference failure: FinBERT returned a result without a usable "
            "label and confidence."
        ) from exc

    return sentiment_score_from_label(label, confidence), label, confidence


def build_summary_label(sentiment_label: str) -> str:
    return f"{sentiment_label}-financial-sentiment"


def analyze_document(document: dict[str, Any]) -> DocumentSignal:
    theme_text = normalize_text(document)
    themes = detect_themes(theme_text)
    sentiment_score, sentiment_label, sentiment_confidence = score_sentiment(
        prepare_finbert_text(document)
    )
    scores = {
        theme: sentiment_score if theme in themes else 0
        for theme in THEME_KEYWORDS
    }

    return DocumentSignal(
        doc_id=document["id"],
        date=extract_date(document["published_at"]),
        source=document.get("source", "unknown"),
        feed_url=document.get("feed_url", ""),
        title=document.get("title", ""),
        themes=themes,
        scores=scores,
        confidence=confidence_bucket(sentiment_confidence),
        sentiment_label=sentiment_label,
        sentiment_confidence=sentiment_confidence,
        summary_label=build_summary_label(sentiment_label),
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
    _ = theme
    if score > 0:
        return "positive financial sentiment"
    if score < 0:
        return "negative financial sentiment"
    return "neutral financial sentiment"


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
    positive_themes = [
        theme
        for theme, score in scores.items()
        if score > 0 and daily_data["theme_counts"].get(theme, 0) > 0
    ]
    negative_themes = [
        theme
        for theme, score in scores.items()
        if score < 0 and daily_data["theme_counts"].get(theme, 0) > 0
    ]
    sentiment_parts: list[str] = []

    if positive_themes:
        sentiment_parts.append(
            "positive financial sentiment around "
            + ", ".join(positive_themes[:3])
        )
    if negative_themes:
        sentiment_parts.append(
            "negative financial sentiment around "
            + ", ".join(negative_themes[:3])
        )

    visible_themes = [
        theme
        for theme, count in daily_data["theme_counts"].most_common()
        if theme != "uncategorized" and count > 0
    ]

    if not daily_data["documents"]:
        return (
            "Macro read: no qualifying macro headlines were available from the examined feeds."
        )

    if not sentiment_parts:
        if visible_themes:
            theme_text = ", ".join(visible_themes[:3])
            return (
                "Macro read: no strong daily signal. "
                f"The examined feeds mentioned {theme_text}, but FinBERT read the "
                "financial tone as neutral or mixed."
            )
        return (
            "Macro read: no strong daily signal. "
            "The examined feeds did not provide enough macro language for a "
            "sentiment interpretation."
        )

    return f"Macro read: {', '.join(sentiment_parts)}."


def build_market_map(market_data: list[MarketSnapshot]) -> dict[str, MarketSnapshot]:
    return {snapshot.symbol: snapshot for snapshot in market_data}


def summarize_market(snapshot: MarketSnapshot) -> str:
    sign_1d = "+" if snapshot.return_1d > 0 else ""
    sign_5d = "+" if snapshot.return_5d > 0 else ""
    return f"{snapshot.symbol} {sign_1d}{snapshot.return_1d:.2f}% 1d, {sign_5d}{snapshot.return_5d:.2f}% 5d"


def build_market_checks(
    daily_scores: dict[str, int], market_map: dict[str, MarketSnapshot]
) -> list[MarketCheck]:
    _ = daily_scores
    _ = market_map
    return []


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
            "Market check: market data is shown as context. Directional proxy "
            "confirmation is not run because FinBERT measures financial tone, "
            "not whether macro variables are rising or falling.",
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
    themes = ", ".join(signal.themes) if signal.themes else "none"
    return (
        f"- {signal.title}\n"
        f"  source={signal.source} | finbert_label={signal.sentiment_label} | "
        f"finbert_confidence={signal.sentiment_confidence:.3f} | "
        f"confidence={signal.confidence} | summary={signal.summary_label} | "
        f"macro_score={signal.macro_score}\n"
        f"  themes={themes}\n"
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
                            "sentiment_label": signal.sentiment_label,
                            "sentiment_confidence": signal.sentiment_confidence,
                            "summary_label": signal.summary_label,
                            "macro_score": signal.macro_score,
                            "macro_buckets": signal.macro_buckets,
                            "themes": signal.themes,
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
                    "sentiment_label": signal.sentiment_label,
                    "sentiment_confidence": signal.sentiment_confidence,
                    "summary_label": signal.summary_label,
                    "macro_score": signal.macro_score,
                    "macro_buckets": signal.macro_buckets,
                    "themes": signal.themes,
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
                themes = ", ".join(signal["themes"]) or "none"
                score = pick_bucket_score(str(bucket_view["name"]), signal["scores"])
                extra = (
                    f" | FinBERT={signal['sentiment_label']} "
                    f"({float(signal['sentiment_confidence']):.3f})"
                    f" | score={score}"
                    f" | themes={themes}"
                )
                if signal["macro_score"] and debug:
                    extra += f" | macro_score={signal['macro_score']}"
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
                    themes=signal["themes"],
                    scores=signal["scores"],
                    confidence=signal["confidence"],
                    sentiment_label=signal["sentiment_label"],
                    sentiment_confidence=signal["sentiment_confidence"],
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
