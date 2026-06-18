from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


THEME_KEYWORDS = {
    "inflation": {"inflation", "prices", "cpi", "oil", "wage"},
    "growth": {"growth", "demand", "spending", "labor", "hiring", "recession"},
    "policy": {"fed", "ecb", "rates", "policymakers", "central bank"},
    "liquidity": {"liquidity", "funding", "credit", "spreads", "bank"},
    "risk": {"risk", "geopolitical", "tensions", "cautious", "defensive"},
}

MIN_UNIQUE_DOCUMENTS = 3
MARKET_MOVE_THRESHOLD = 0.20
NEWS_SENTIMENT_POSITIVE_THRESHOLD = 0.20
NEWS_SENTIMENT_NEGATIVE_THRESHOLD = -0.20
MARKET_REGIME_POSITIVE_THRESHOLD = 0.25
MARKET_REGIME_NEGATIVE_THRESHOLD = -0.25
MARKET_REGIME_WEIGHTS = {
    "SPY": 0.40,
    "HYG": 0.35,
    "TLT": 0.15,
    "GLD": 0.10,
}
PRIMARY_MARKET_SIGNALS = {"SPY", "HYG"}
MARKET_SNAPSHOT_ORDER = ("SPY", "TLT", "UUP", "USO", "HYG", "GLD")
NEWS_LABEL_TO_DIRECTION = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
CONFIRMATION_LABELS = {
    "confirmed": "Confirmed",
    "divergent": "Divergent",
    "unconfirmed": "Unconfirmed",
    "market_led": "Market-led",
    "neutral": "Neutral",
    "insufficient_data": "Insufficient data",
}


@dataclass
class DocumentSignal:
    doc_id: str
    date: str
    source: str
    feed_url: str
    url: str
    title: str
    unique_key: str
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


def normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def build_document_unique_key(
    title: str,
    url: str,
    doc_id: str,
) -> str:
    normalized_title = normalize_identifier(title)
    normalized_url = normalize_identifier(url)
    if normalized_title or normalized_url:
        return f"{normalized_title}|{normalized_url}"
    return normalize_identifier(doc_id)


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
    title = str(document.get("title", ""))
    url = str(document.get("url", ""))
    doc_id = str(document.get("id", ""))

    return DocumentSignal(
        doc_id=doc_id,
        date=extract_date(document["published_at"]),
        source=document.get("source", "unknown"),
        feed_url=document.get("feed_url", ""),
        url=url,
        title=title,
        unique_key=build_document_unique_key(title, url, doc_id),
        themes=themes,
        scores=scores,
        confidence=confidence_bucket(sentiment_confidence),
        sentiment_label=sentiment_label,
        sentiment_confidence=sentiment_confidence,
        summary_label=build_summary_label(sentiment_label),
        macro_score=int(document.get("macro_score", 0) or 0),
        macro_buckets=list(document.get("macro_buckets", []) or []),
    )


def merge_document_signals(
    left: DocumentSignal,
    right: DocumentSignal,
) -> DocumentSignal:
    merged_scores = dict(left.scores)
    for theme, score in right.scores.items():
        if abs(score) > abs(merged_scores.get(theme, 0)):
            merged_scores[theme] = score

    merged_themes = sorted(set(left.themes) | set(right.themes))
    merged_buckets = sorted(set(left.macro_buckets) | set(right.macro_buckets))
    preferred = left
    if right.sentiment_confidence > left.sentiment_confidence:
        preferred = right

    return replace(
        preferred,
        unique_key=left.unique_key,
        themes=merged_themes or ["uncategorized"],
        scores=merged_scores,
        macro_score=max(left.macro_score, right.macro_score),
        macro_buckets=merged_buckets,
        source=preferred.source or left.source or right.source,
        feed_url=preferred.feed_url or left.feed_url or right.feed_url,
        url=preferred.url or left.url or right.url,
        title=preferred.title or left.title or right.title,
    )


def dedupe_signals(signals: list[DocumentSignal]) -> list[DocumentSignal]:
    unique_by_key: dict[str, DocumentSignal] = {}
    for signal in signals:
        existing = unique_by_key.get(signal.unique_key)
        if existing is None:
            unique_by_key[signal.unique_key] = signal
        else:
            unique_by_key[signal.unique_key] = merge_document_signals(existing, signal)

    return sorted(
        unique_by_key.values(),
        key=lambda signal: (signal.macro_score, signal.sentiment_confidence, signal.title),
        reverse=True,
    )


def aggregate_by_date(signals: list[DocumentSignal]) -> dict[str, dict[str, Any]]:
    grouped_raw: dict[str, list[DocumentSignal]] = defaultdict(list)
    for signal in signals:
        grouped_raw[signal.date].append(signal)

    grouped: dict[str, dict[str, Any]] = {}
    for date, day_signals in grouped_raw.items():
        unique_documents = dedupe_signals(day_signals)
        daily_scores: defaultdict[str, int] = defaultdict(int)
        theme_counts: Counter[str] = Counter()

        for signal in unique_documents:
            for theme, score in signal.scores.items():
                daily_scores[theme] += score
            for theme in signal.themes:
                theme_counts[theme] += 1

        grouped[date] = {
            "scores": daily_scores,
            "theme_counts": theme_counts,
            "documents": unique_documents,
        }

    return grouped


def describe_score(theme: str, score: int) -> str:
    _ = theme
    if score > 0:
        return "positive news sentiment"
    if score < 0:
        return "negative news sentiment"
    return "neutral news sentiment"


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
    return bucket_map.get(bucket, "neutral news sentiment")


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
    return scores.get(mapping.get(bucket, "risk"), 0)


def build_daily_brief(date: str, daily_data: dict[str, Any]) -> str:
    news_sentiment = aggregate_news_sentiment(daily_data["documents"])
    top_theme = "none"
    if daily_data["theme_counts"]:
        top_theme = daily_data["theme_counts"].most_common(1)[0][0]

    if news_sentiment["label"] == "insufficient_data":
        return (
            f"{date}: {news_sentiment['unique_documents']} unique articles were analyzed. "
            f"Top theme: {top_theme}. There was not enough coverage for a reliable daily sentiment read."
        )

    return (
        f"{date}: {news_sentiment['unique_documents']} unique articles were analyzed. "
        f"News sentiment was {news_sentiment['label'].replace('_', ' ')}. Top theme: {top_theme}."
    )


def build_day_conclusion(daily_data: dict[str, Any]) -> str:
    documents = daily_data["documents"]
    if not documents:
        return "Macro read: no qualifying macro headlines were available from the examined feeds."

    news_sentiment = aggregate_news_sentiment(documents)
    visible_themes = [
        theme
        for theme, count in daily_data["theme_counts"].most_common()
        if theme != "uncategorized" and count > 0
    ]
    theme_text = ", ".join(visible_themes[:3]) if visible_themes else "macro topics"

    if news_sentiment["label"] == "insufficient_data":
        return (
            "Macro read: there was not enough unique coverage to form a reliable daily "
            "news sentiment signal."
        )
    if news_sentiment["label"] == "neutral":
        return (
            f"Macro read: coverage across {theme_text} was broadly neutral or mixed."
        )

    return (
        f"Macro read: {theme_text.title()} coverage showed a predominantly "
        f"{news_sentiment['label']} tone."
    )


def build_market_map(market_data: list[MarketSnapshot]) -> dict[str, MarketSnapshot]:
    return {snapshot.symbol: snapshot for snapshot in market_data}


def aggregate_news_sentiment(documents: list[DocumentSignal]) -> dict[str, Any]:
    unique_documents = dedupe_signals(documents)
    total = len(unique_documents)

    if total == 0:
        return {
            "label": "insufficient_data",
            "score": 0.0,
            "display_score": 0.0,
            "unique_documents": 0,
            "positive_pct": 0.0,
            "neutral_pct": 0.0,
            "negative_pct": 0.0,
            "average_confidence": 0.0,
        }

    sentiment_values = [
        NEWS_LABEL_TO_DIRECTION.get(document.sentiment_label, 0.0)
        for document in unique_documents
    ]
    counts = Counter(document.sentiment_label for document in unique_documents)
    average_confidence = sum(
        document.sentiment_confidence for document in unique_documents
    ) / total
    score = sum(sentiment_values) / total

    if total < MIN_UNIQUE_DOCUMENTS:
        label = "insufficient_data"
    elif score >= NEWS_SENTIMENT_POSITIVE_THRESHOLD:
        label = "positive"
    elif score <= NEWS_SENTIMENT_NEGATIVE_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return {
        "label": label,
        "score": score,
        "display_score": round(score, 2),
        "unique_documents": total,
        "positive_pct": round((counts.get("positive", 0) / total) * 100.0, 1),
        "neutral_pct": round((counts.get("neutral", 0) / total) * 100.0, 1),
        "negative_pct": round((counts.get("negative", 0) / total) * 100.0, 1),
        "average_confidence": round(average_confidence, 3),
    }


def classify_market_regime(market_data: list[MarketSnapshot]) -> dict[str, Any]:
    market_map = build_market_map(market_data)
    available_symbols = [
        symbol for symbol in MARKET_REGIME_WEIGHTS
        if symbol in market_map
    ]
    contributions = {symbol: None for symbol in MARKET_REGIME_WEIGHTS}

    if not PRIMARY_MARKET_SIGNALS.issubset(set(available_symbols)):
        missing = sorted(PRIMARY_MARKET_SIGNALS - set(available_symbols))
        return {
            "label": "insufficient_data",
            "score": 0.0,
            "signals_used": 0,
            "signals_available": len(available_symbols),
            "contributions": contributions,
            "explanation": (
                "Market confirmation needs both SPY and HYG as the primary risk proxies."
            ),
            "data_quality_status": "missing_primary_signals",
            "available_tickers": available_symbols,
            "missing_tickers": missing,
        }

    if len(available_symbols) < 2:
        return {
            "label": "insufficient_data",
            "score": 0.0,
            "signals_used": 0,
            "signals_available": len(available_symbols),
            "contributions": contributions,
            "explanation": "There were not enough usable market proxies to classify the day.",
            "data_quality_status": "insufficient_signals",
            "available_tickers": available_symbols,
            "missing_tickers": sorted(
                set(MARKET_REGIME_WEIGHTS) - set(available_symbols)
            ),
        }

    weight_total = sum(MARKET_REGIME_WEIGHTS[symbol] for symbol in available_symbols)
    normalized_weights = {
        symbol: MARKET_REGIME_WEIGHTS[symbol] / weight_total
        for symbol in available_symbols
    }

    valid_signal_count = 0
    score = 0.0
    for symbol in available_symbols:
        snapshot = market_map[symbol]
        move = snapshot.return_1d
        contribution = 0.0
        if move > MARKET_MOVE_THRESHOLD:
            contribution = 1.0 if symbol in {"SPY", "HYG"} else -1.0
        elif move < -MARKET_MOVE_THRESHOLD:
            contribution = -1.0 if symbol in {"SPY", "HYG"} else 1.0

        weighted_contribution = normalized_weights[symbol] * contribution
        contributions[symbol] = round(weighted_contribution, 4)
        score += weighted_contribution
        valid_signal_count += 1

    missing_tickers = sorted(set(MARKET_REGIME_WEIGHTS) - set(available_symbols))
    if valid_signal_count < 2:
        return {
            "label": "insufficient_data",
            "score": 0.0,
            "signals_used": valid_signal_count,
            "signals_available": len(available_symbols),
            "contributions": contributions,
            "explanation": "There were not enough usable market proxies to classify the day.",
            "data_quality_status": "insufficient_signals",
            "available_tickers": available_symbols,
            "missing_tickers": missing_tickers,
        }

    if score >= MARKET_REGIME_POSITIVE_THRESHOLD:
        label = "risk_on"
        explanation = "Primary market proxies showed a broadly risk-on response."
    elif score <= MARKET_REGIME_NEGATIVE_THRESHOLD:
        label = "risk_off"
        explanation = "Primary market proxies showed a broadly risk-off response."
    else:
        label = "mixed"
        explanation = "The major market proxies gave a mixed risk signal."

    data_quality_status = "complete" if not missing_tickers else "partial"
    return {
        "label": label,
        "score": score,
        "signals_used": valid_signal_count,
        "signals_available": len(available_symbols),
        "contributions": contributions,
        "explanation": explanation,
        "data_quality_status": data_quality_status,
        "available_tickers": available_symbols,
        "missing_tickers": missing_tickers,
    }


def compare_sentiment_with_market(
    news_sentiment: dict[str, Any],
    market_regime: dict[str, Any],
) -> dict[str, str]:
    news_label = str(news_sentiment.get("label", "insufficient_data"))
    market_label = str(market_regime.get("label", "insufficient_data"))

    if "insufficient_data" in {news_label, market_label}:
        status = "insufficient_data"
        explanation = (
            "There was not enough reliable news or market data to evaluate confirmation."
        )
    elif news_label == "positive" and market_label == "risk_on":
        status = "confirmed"
        explanation = (
            "News sentiment and the market’s risk response moved in the same direction."
        )
    elif news_label == "negative" and market_label == "risk_off":
        status = "confirmed"
        explanation = (
            "News sentiment and the market’s risk response moved in the same direction."
        )
    elif news_label == "positive" and market_label == "risk_off":
        status = "divergent"
        explanation = (
            "News sentiment and the market reaction diverged. The market may have been "
            "responding to other catalysts or information already priced in."
        )
    elif news_label == "negative" and market_label == "risk_on":
        status = "divergent"
        explanation = (
            "News sentiment and the market reaction diverged. The market may have been "
            "responding to other catalysts or information already priced in."
        )
    elif news_label in {"positive", "negative"} and market_label == "mixed":
        status = "unconfirmed"
        explanation = (
            "News sentiment had a directional bias, but the broader market response was mixed."
        )
    elif news_label == "neutral" and market_label in {"risk_on", "risk_off"}:
        status = "market_led"
        explanation = (
            "News sentiment was neutral, while markets showed a clearer directional response."
        )
    else:
        status = "neutral"
        explanation = (
            "Both news sentiment and the broader market response were broadly neutral."
        )

    return {
        "status": status,
        "label": CONFIRMATION_LABELS[status],
        "explanation": explanation,
        "news_label": news_label,
        "market_label": market_label,
    }


def group_documents_by_bucket(documents: list[DocumentSignal]) -> dict[str, list[DocumentSignal]]:
    grouped: dict[str, list[DocumentSignal]] = defaultdict(list)
    for document in dedupe_signals(documents):
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


def serialize_document(signal: DocumentSignal) -> dict[str, Any]:
    return {
        "doc_id": signal.doc_id,
        "title": signal.title,
        "source": signal.source,
        "url": signal.url,
        "confidence": signal.confidence,
        "sentiment_label": signal.sentiment_label,
        "sentiment_confidence": signal.sentiment_confidence,
        "summary_label": signal.summary_label,
        "macro_score": signal.macro_score,
        "macro_buckets": signal.macro_buckets,
        "themes": signal.themes,
        "scores": signal.scores,
    }


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
    market_data = market_data or []
    market_map = build_market_map(market_data)
    market_regime = classify_market_regime(market_data) if market_data else {
        "label": "insufficient_data",
        "score": 0.0,
        "signals_used": 0,
        "signals_available": 0,
        "contributions": {symbol: None for symbol in MARKET_REGIME_WEIGHTS},
        "explanation": "There was not enough reliable news or market data to evaluate confirmation.",
        "data_quality_status": "missing_market_data",
        "available_tickers": [],
        "missing_tickers": sorted(MARKET_REGIME_WEIGHTS),
    }
    reports: list[dict[str, Any]] = []

    for date in sorted(grouped):
        daily_data = grouped[date]
        unique_documents = dedupe_signals(daily_data["documents"])
        news_sentiment = aggregate_news_sentiment(unique_documents)
        confirmation = compare_sentiment_with_market(news_sentiment, market_regime)
        bucket_views = build_bucket_views(unique_documents, daily_data["scores"])
        selected_buckets = bucket_views if debug else select_priority_buckets(bucket_views)

        report_entry = {
            "date": date,
            "daily_brief": build_daily_brief(date, daily_data),
            "macro_read": build_day_conclusion(daily_data),
            "market_confirmation": confirmation["explanation"],
            "market_checks": [],
            "feed_sources": sorted(
                {
                    signal.feed_url
                    for signal in unique_documents
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
                for symbol in MARKET_SNAPSHOT_ORDER
                if symbol in market_map
            ],
            "news_sentiment": news_sentiment,
            "market_regime": {
                "label": market_regime["label"],
                "score": round(float(market_regime["score"]), 2),
                "signals_used": market_regime["signals_used"],
                "signals_available": market_regime["signals_available"],
                "contributions": market_regime["contributions"],
                "explanation": market_regime["explanation"],
                "data_quality_status": market_regime["data_quality_status"],
            },
            "confirmation": confirmation,
            "analyzed_coverage": [
                serialize_document(signal)
                for signal in unique_documents
            ],
            "bucket_views": [
                {
                    "name": bucket_view.name,
                    "label": bucket_view.label,
                    "score": bucket_view.score,
                    "documents": [
                        serialize_document(signal)
                        for signal in bucket_view.documents[:3]
                    ],
                }
                for bucket_view in selected_buckets
            ],
            "debug_documents": [
                serialize_document(signal)
                for signal in unique_documents
            ] if debug else [],
        }
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
        lines.append(
            f"News sentiment: {report['news_sentiment']['label']} "
            f"({report['news_sentiment']['display_score']:+.2f})"
        )
        lines.append(
            f"Market response: {report['market_regime']['label']} "
            f"({float(report['market_regime']['score']):+.2f})"
        )
        lines.append(
            f"Confirmation: {report['confirmation']['label']} - "
            f"{report['confirmation']['explanation']}"
        )
        if report["market_snapshot"]:
            lines.append(
                "Market snapshot: "
                + "; ".join(
                    f"{item['symbol']} "
                    f"{'+' if item['return_1d'] > 0 else ''}{item['return_1d']:.2f}% 1d, "
                    f"{'+' if item['return_5d'] > 0 else ''}{item['return_5d']:.2f}% 5d"
                    for item in report["market_snapshot"]
                )
            )
        lines.append("")

        for bucket_view in report["bucket_views"]:
            lines.append(f"{bucket_view['name'].upper()} | {bucket_view['label']}")
            for signal in bucket_view["documents"]:
                themes = ", ".join(signal["themes"]) or "none"
                extra = (
                    f" | sentiment={signal['sentiment_label']} "
                    f"({float(signal['sentiment_confidence']):.3f})"
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
                    doc_id=signal["doc_id"],
                    date=report["date"],
                    source=signal["source"],
                    feed_url="",
                    url=signal["url"],
                    title=signal["title"],
                    unique_key=build_document_unique_key(
                        signal["title"], signal["url"], signal["doc_id"]
                    ),
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
