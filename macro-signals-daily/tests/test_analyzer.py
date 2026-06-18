from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from generate_site import generate_site, render_site  # noqa: E402
from macro_signals import analyzer  # noqa: E402


class FakePipeline:
    def __init__(self, outputs: list[tuple[str, float]]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, object]] = []

    def __call__(self, text: str, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append({"text": text, **kwargs})
        label, score = self.outputs.pop(0)
        return [{"label": label, "score": score}]


def install_fake_pipeline(monkeypatch: pytest.MonkeyPatch, outputs: list[tuple[str, float]]) -> FakePipeline:
    fake = FakePipeline(outputs)
    monkeypatch.setattr(analyzer, "get_finbert_pipeline", lambda: fake)
    return fake


def make_document(
    doc_id: str,
    title: str,
    *,
    url: str | None = None,
    body: str = "",
    published_at: str = "2026-06-16T12:00:00+00:00",
    source: str = "Example",
    feed_url: str = "https://example.com/rss",
    macro_score: int = 5,
    macro_buckets: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": doc_id,
        "source": source,
        "feed_url": feed_url,
        "published_at": published_at,
        "title": title,
        "body": body,
        "url": url or f"https://example.com/{doc_id}",
        "macro_score": macro_score,
        "macro_buckets": macro_buckets or ["policy"],
    }


def make_snapshot(symbol: str, return_1d: float) -> analyzer.MarketSnapshot:
    labels = {
        "SPY": "US equities",
        "HYG": "High yield credit",
        "TLT": "Long-duration Treasuries",
        "GLD": "Gold",
        "UUP": "US dollar proxy",
        "USO": "Oil proxy",
    }
    return analyzer.MarketSnapshot(
        symbol=symbol,
        label=labels[symbol],
        as_of="2026-06-16",
        close=100.0,
        return_1d=return_1d,
        return_5d=0.0,
    )


def make_signal(
    label: str,
    confidence: float,
    *,
    doc_id: str,
    title: str,
    url: str | None = None,
    published_at: str = "2026-06-16T12:00:00+00:00",
    macro_buckets: list[str] | None = None,
) -> analyzer.DocumentSignal:
    score = analyzer.sentiment_score_from_label(label, confidence)
    return analyzer.DocumentSignal(
        doc_id=doc_id,
        date=analyzer.extract_date(published_at),
        source="Example",
        feed_url="https://example.com/rss",
        url=url or f"https://example.com/{doc_id}",
        title=title,
        unique_key=analyzer.build_document_unique_key(title, url or f"https://example.com/{doc_id}", doc_id),
        themes=["policy"],
        scores={
            "inflation": 0,
            "growth": 0,
            "policy": score,
            "liquidity": 0,
            "risk": 0,
        },
        confidence=analyzer.confidence_bucket(confidence),
        sentiment_label=label,
        sentiment_confidence=confidence,
        summary_label=analyzer.build_summary_label(label),
        macro_score=5,
        macro_buckets=macro_buckets or ["policy"],
    )


def test_score_sentiment_converts_positive_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_pipeline(monkeypatch, [("positive", 0.91)])

    score, label, confidence = analyzer.score_sentiment("Bank earnings improved.")

    assert score == 2
    assert label == "positive"
    assert confidence == 0.91
    assert fake.calls[0]["truncation"] is True
    assert fake.calls[0]["max_length"] == 512


def test_score_sentiment_converts_lower_confidence_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_pipeline(monkeypatch, [("negative", 0.72)])

    score, label, confidence = analyzer.score_sentiment("Credit losses widened.")

    assert score == -1
    assert label == "negative"
    assert confidence == 0.72


def test_score_sentiment_converts_neutral_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_pipeline(monkeypatch, [("neutral", 0.99)])

    score, label, confidence = analyzer.score_sentiment("Markets were little changed.")

    assert score == 0
    assert label == "neutral"
    assert confidence == 0.99


def test_score_sentiment_rejects_empty_input() -> None:
    with pytest.raises(analyzer.FinBERTError, match="Invalid input"):
        analyzer.score_sentiment("   ")


def test_analyze_document_scores_only_detected_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_pipeline(monkeypatch, [("positive", 0.88)])
    document = make_document(
        "doc-1",
        "Fed watches inflation as prices remain firm",
        body="Central bank officials discussed CPI and policy risks.",
    )

    signal = analyzer.analyze_document(document)

    assert signal.sentiment_label == "positive"
    assert signal.sentiment_confidence == 0.88
    assert signal.scores["inflation"] == 2
    assert signal.scores["policy"] == 2
    assert signal.scores["growth"] == 0


@pytest.mark.parametrize(
    ("news_label", "market_moves", "expected_status"),
    [
        ("positive", {"SPY": 0.8, "HYG": 0.7, "TLT": -0.4, "GLD": -0.3}, "confirmed"),
        ("negative", {"SPY": -0.9, "HYG": -0.8, "TLT": 0.5, "GLD": 0.4}, "confirmed"),
        ("positive", {"SPY": -0.8, "HYG": -0.7, "TLT": 0.4, "GLD": 0.3}, "divergent"),
        ("negative", {"SPY": 0.9, "HYG": 0.8, "TLT": -0.4, "GLD": -0.3}, "divergent"),
        ("positive", {"SPY": 0.7, "HYG": -0.7, "TLT": 0.1, "GLD": -0.1}, "unconfirmed"),
        ("neutral", {"SPY": 0.8, "HYG": 0.6, "TLT": -0.3, "GLD": -0.2}, "market_led"),
        ("neutral", {"SPY": 0.7, "HYG": -0.7, "TLT": 0.1, "GLD": -0.1}, "neutral"),
    ],
)
def test_compare_sentiment_with_market_states(
    news_label: str,
    market_moves: dict[str, float],
    expected_status: str,
) -> None:
    market_data = [make_snapshot(symbol, move) for symbol, move in market_moves.items()]
    market_regime = analyzer.classify_market_regime(market_data)

    result = analyzer.compare_sentiment_with_market({"label": news_label}, market_regime)

    assert result["status"] == expected_status


def test_missing_spy_or_hyg_returns_insufficient_data() -> None:
    market_regime = analyzer.classify_market_regime(
        [make_snapshot("SPY", 0.8), make_snapshot("TLT", -0.3), make_snapshot("GLD", -0.2)]
    )

    assert market_regime["label"] == "insufficient_data"
    assert market_regime["data_quality_status"] == "missing_primary_signals"


def test_market_moves_inside_threshold_are_neutral() -> None:
    market_regime = analyzer.classify_market_regime(
        [
            make_snapshot("SPY", 0.19),
            make_snapshot("HYG", -0.19),
            make_snapshot("TLT", 0.15),
            make_snapshot("GLD", -0.10),
        ]
    )

    assert market_regime["label"] == "mixed"
    assert market_regime["score"] == pytest.approx(0.0)
    assert market_regime["contributions"]["SPY"] == pytest.approx(0.0)
    assert market_regime["contributions"]["HYG"] == pytest.approx(0.0)


def test_weights_are_renormalized_when_optional_market_data_missing() -> None:
    market_regime = analyzer.classify_market_regime(
        [make_snapshot("SPY", 0.8), make_snapshot("HYG", 0.7)]
    )

    assert market_regime["label"] == "risk_on"
    assert market_regime["contributions"]["SPY"] == pytest.approx(0.5333, abs=1e-4)
    assert market_regime["contributions"]["HYG"] == pytest.approx(0.4667, abs=1e-4)
    assert market_regime["score"] == pytest.approx(1.0)


def test_duplicate_headlines_are_counted_once_in_aggregate_sentiment() -> None:
    duplicate_url = "https://example.com/shared-story"
    signals = [
        make_signal("negative", 0.84, doc_id="doc-1", title="Dollar slips on Fed focus", url=duplicate_url, macro_buckets=["policy"]),
        make_signal("negative", 0.82, doc_id="doc-2", title="Dollar slips on Fed focus", url=duplicate_url, macro_buckets=["fx"]),
        make_signal("positive", 0.87, doc_id="doc-3", title="Growth stabilizes", url="https://example.com/growth"),
        make_signal("neutral", 0.77, doc_id="doc-4", title="Inflation holds steady", url="https://example.com/inflation"),
    ]

    sentiment = analyzer.aggregate_news_sentiment(signals)

    assert sentiment["unique_documents"] == 3
    assert sentiment["negative_pct"] == pytest.approx(33.3, abs=0.1)


def test_generated_html_contains_exactly_one_finbert_and_no_internal_scores() -> None:
    signals = [
        make_signal("negative", 0.84, doc_id="doc-1", title="Policy pressure builds"),
        make_signal("negative", 0.82, doc_id="doc-2", title="Credit spreads widen"),
        make_signal("neutral", 0.77, doc_id="doc-3", title="Inflation data steady"),
    ]
    reports = analyzer.build_report_data(
        signals,
        market_data=[
            make_snapshot("SPY", -0.6),
            make_snapshot("HYG", -0.5),
            make_snapshot("TLT", 0.3),
            make_snapshot("GLD", 0.2),
        ],
    )

    html = render_site(reports)

    assert html.count("FinBERT") == 1
    assert "score -1" not in html
    assert "score 0" not in html


def test_report_remains_valid_when_no_qualifying_headlines_available(tmp_path: Path) -> None:
    news_path = tmp_path / "news.json"
    market_path = tmp_path / "market.json"
    output_dir = tmp_path / "site"
    news_path.write_text("[]", encoding="utf-8")
    market_path.write_text(json.dumps({"as_of": "2026-06-16", "snapshots": []}), encoding="utf-8")

    index_path = generate_site(news_path, market_path, output_dir)
    report_payload = json.loads((output_dir / "report-data.json").read_text(encoding="utf-8"))
    html = index_path.read_text(encoding="utf-8")

    assert report_payload == []
    assert "Waiting for Data" in html
    assert html.count("FinBERT") == 1


def test_report_remains_valid_when_optional_market_proxy_is_missing() -> None:
    signals = [
        make_signal("positive", 0.91, doc_id="doc-1", title="Policy support improves"),
        make_signal("positive", 0.86, doc_id="doc-2", title="Credit tone improves"),
        make_signal("neutral", 0.75, doc_id="doc-3", title="Inflation remains steady"),
    ]
    reports = analyzer.build_report_data(
        signals,
        market_data=[
            make_snapshot("SPY", 0.8),
            make_snapshot("HYG", 0.5),
            make_snapshot("TLT", -0.3),
        ],
    )

    assert len(reports) == 1
    report = reports[0]
    assert report["market_regime"]["label"] == "risk_on"
    assert report["market_regime"]["data_quality_status"] == "partial"
    assert len(report["market_snapshot"]) == 3


def test_generate_site_outputs_valid_json_and_confirmation_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    news_path = tmp_path / "news.json"
    market_path = tmp_path / "market.json"
    output_dir = tmp_path / "site"
    news_documents = [
        make_document("doc-1", "Fed signals support"),
        make_document("doc-2", "Credit markets steady"),
        make_document("doc-3", "Growth outlook firms"),
    ]
    news_path.write_text(json.dumps(news_documents), encoding="utf-8")
    market_payload = {
        "as_of": "2026-06-16",
        "snapshots": [
            {
                "symbol": "SPY",
                "label": "US equities",
                "as_of": "2026-06-16",
                "close": 100.0,
                "return_1d": 0.8,
                "return_5d": 0.0,
            },
            {
                "symbol": "HYG",
                "label": "High yield credit",
                "as_of": "2026-06-16",
                "close": 100.0,
                "return_1d": 0.6,
                "return_5d": 0.0,
            },
        ],
    }
    market_path.write_text(json.dumps(market_payload), encoding="utf-8")
    install_fake_pipeline(
        monkeypatch,
        [("positive", 0.9), ("positive", 0.86), ("neutral", 0.79)],
    )

    generate_site(news_path, market_path, output_dir)
    payload = json.loads((output_dir / "report-data.json").read_text(encoding="utf-8"))

    assert isinstance(payload, list)
    assert payload[0]["confirmation"]["status"] == "confirmed"
    assert payload[0]["news_sentiment"]["unique_documents"] == 3
