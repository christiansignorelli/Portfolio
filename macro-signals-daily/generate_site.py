from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

from fetch_news import DEFAULT_FEEDS
from macro_signals.analyzer import (
    analyze_document,
    build_report_data,
    load_documents,
    load_market_data,
)


SITE_TITLE = "Macro Signals Daily"
SITE_TAGLINE = "Daily macro wrap-up from public news coverage and market context"

CSS = """
:root {
  --bg: #f5efe5;
  --panel: #fffaf2;
  --panel-strong: #f1e8d9;
  --ink: #1f2933;
  --muted: #5d6b78;
  --line: #dacfbf;
  --accent: #204d74;
  --good: #1f6b44;
  --bad: #8f2f2d;
  --soft: #8a6a2d;
  --shadow: 0 14px 34px rgba(31, 41, 51, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(32, 77, 116, 0.12), transparent 35%),
    linear-gradient(180deg, #fbf8f1 0%, var(--bg) 100%);
}
.page {
  width: min(1120px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 30px 0 72px;
}
.hero, .card, .market-card, .story-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: var(--shadow);
}
.hero { padding: 28px; }
.card, .story-card { padding: 20px; }
.market-card { padding: 16px; }
.eyebrow, .kicker {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  color: var(--muted);
}
h1 { margin: 0; font-size: clamp(34px, 6vw, 64px); line-height: 0.95; }
h2 { margin: 0 0 12px; font-size: 24px; }
h3 { margin: 0 0 10px; font-size: 18px; }
.tagline, .subtle, .source, .footer, details p, details li {
  color: var(--muted);
}
.tagline {
  margin: 14px 0 0;
  max-width: 720px;
  font-size: 18px;
}
.section { margin-top: 28px; }
.meta-row, .signal-grid, .market-grid, .coverage-grid {
  display: grid;
  gap: 16px;
}
.meta-row { margin-top: 22px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.signal-grid { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.market-grid { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.coverage-grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.value {
  font-size: 28px;
  line-height: 1.05;
  margin: 0 0 8px;
}
.summary-line {
  font-size: 15px;
  color: var(--ink);
  margin-top: 6px;
}
.status-pill, .tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
}
.status-pill {
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 12px;
  background: var(--panel-strong);
}
.tag {
  margin: 6px 8px 0 0;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--accent);
  background: rgba(32, 77, 116, 0.08);
}
.status-confirmed { color: var(--good); background: rgba(31, 107, 68, 0.12); }
.status-divergent { color: var(--bad); background: rgba(143, 47, 45, 0.12); }
.status-unconfirmed, .status-market-led, .status-neutral, .status-insufficient-data {
  color: var(--soft);
  background: rgba(138, 106, 45, 0.12);
}
.story-card ul, .source-list {
  margin: 12px 0 0;
  padding-left: 18px;
}
.source-list li + li { margin-top: 8px; }
.source-list a {
  color: #114c9b;
  text-decoration: none;
}
.source-list a:hover { text-decoration: underline; }
.story-title {
  font-size: 18px;
  line-height: 1.25;
  margin-bottom: 8px;
}
.footer {
  margin-top: 36px;
  font-size: 13px;
}
details {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
summary {
  cursor: pointer;
  color: var(--accent);
  font-weight: 700;
}
@media (max-width: 720px) {
  .page {
    width: min(100vw - 20px, 1120px);
    padding-top: 16px;
  }
}
"""


def format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_sentiment_label(label: str) -> str:
    return {
        "positive": "Positive",
        "negative": "Negative",
        "neutral": "Neutral",
        "insufficient_data": "Insufficient data",
    }.get(label, label.replace("_", " ").title())


def format_market_label(label: str) -> str:
    return {
        "risk_on": "Risk-on",
        "risk_off": "Risk-off",
        "mixed": "Mixed",
        "insufficient_data": "Insufficient data",
    }.get(label, label.replace("_", " ").title())


def format_status_class(status: str) -> str:
    return "status-" + status.replace("_", "-")


def build_market_cards(market_snapshot: list[dict[str, object]]) -> str:
    if not market_snapshot:
        return "<p class='subtle'>No market data available.</p>"

    cards = []
    for item in market_snapshot:
        cards.append(
            """
            <div class="market-card">
              <div class="kicker">{symbol}</div>
              <div class="value">{return_1d}</div>
              <div class="subtle">{label}</div>
              <div class="subtle">5d {return_5d}</div>
            </div>
            """.format(
                symbol=escape(str(item["symbol"])),
                return_1d=escape(format_pct(float(item["return_1d"]))),
                label=escape(str(item["label"])),
                return_5d=escape(format_pct(float(item["return_5d"]))),
            )
        )
    return '<div class="market-grid">' + "".join(cards) + "</div>"


def build_feed_sources(report: dict[str, object]) -> str:
    feeds = sorted(set(DEFAULT_FEEDS) | set(report.get("feed_sources", [])))
    if not feeds:
        return "<p class='subtle'>No feed metadata was available for this run.</p>"

    items = []
    for feed in feeds:
        safe_url = escape(str(feed))
        items.append(
            f'<li><a href="{safe_url}" target="_blank" rel="noreferrer">{safe_url}</a></li>'
        )
    return '<ul class="source-list">' + "".join(items) + "</ul>"


def build_confirmation_card(report: dict[str, object]) -> str:
    confirmation = dict(report.get("confirmation", {}))
    news_sentiment = dict(report.get("news_sentiment", {}))
    market_regime = dict(report.get("market_regime", {}))
    status = str(confirmation.get("status", "insufficient_data"))

    return """
    <div class="card">
      <div class="kicker">News–Market Confirmation</div>
      <div class="status-pill {status_class}">{status_label}</div>
      <div class="summary-line">News sentiment: {news_label}</div>
      <div class="summary-line">Market response: {market_label}</div>
      <p class="subtle">{explanation}</p>
      <details>
        <summary>How confirmation works</summary>
        <p>
          It compares the aggregated tone of unique news documents with a basket of
          risk-on and risk-off proxies. SPY and HYG carry the most weight, while TLT
          and GLD act as lighter defensive signals.
        </p>
      </details>
    </div>
    """.format(
        status_class=escape(format_status_class(status)),
        status_label=escape(str(confirmation.get("label", "Insufficient data")).upper()),
        news_label=escape(format_sentiment_label(str(news_sentiment.get("label", "insufficient_data")))),
        market_label=escape(format_market_label(str(market_regime.get("label", "insufficient_data")))),
        explanation=escape(str(confirmation.get("explanation", ""))),
    )


def build_news_sentiment_card(report: dict[str, object]) -> str:
    sentiment = dict(report.get("news_sentiment", {}))
    confidence_pct = round(float(sentiment.get("average_confidence", 0.0)) * 100)
    return """
    <div class="card">
      <div class="kicker">News Sentiment</div>
      <div class="value">{label}</div>
      <div class="subtle">{documents} unique documents analyzed</div>
      <div class="summary-line">Positive {positive_pct}% · Neutral {neutral_pct}% · Negative {negative_pct}%</div>
      <div class="summary-line">Average confidence: {confidence_pct}%</div>
    </div>
    """.format(
        label=escape(format_sentiment_label(str(sentiment.get("label", "insufficient_data")))),
        documents=int(sentiment.get("unique_documents", 0)),
        positive_pct=float(sentiment.get("positive_pct", 0.0)),
        neutral_pct=float(sentiment.get("neutral_pct", 0.0)),
        negative_pct=float(sentiment.get("negative_pct", 0.0)),
        confidence_pct=confidence_pct,
    )


def build_market_regime_card(report: dict[str, object]) -> str:
    regime = dict(report.get("market_regime", {}))
    return """
    <div class="card">
      <div class="kicker">Market Response</div>
      <div class="value">{label}</div>
      <div class="subtle">Score {score:+.2f} · {signals_used} signals used</div>
      <p class="subtle">{explanation}</p>
    </div>
    """.format(
        label=escape(format_market_label(str(regime.get("label", "insufficient_data")))),
        score=float(regime.get("score", 0.0)),
        signals_used=int(regime.get("signals_used", 0)),
        explanation=escape(str(regime.get("explanation", ""))),
    )


def build_coverage_cards(report: dict[str, object]) -> str:
    coverage = list(report.get("analyzed_coverage", []))
    if not coverage:
        return "<p class='subtle'>No qualifying headlines were available for this report.</p>"

    cards = []
    for item in coverage:
        confidence_pct = round(float(item.get("sentiment_confidence", 0.0)) * 100)
        tags = "".join(
            f'<span class="tag">{escape(str(theme).title())}</span>'
            for theme in item.get("themes", [])
        )
        cards.append(
            """
            <article class="story-card">
              <div class="story-title">{title}</div>
              <div class="source">{source}</div>
              <div class="summary-line">Sentiment: {sentiment} · {confidence}% confidence</div>
              <div>{tags}</div>
            </article>
            """.format(
                title=escape(str(item.get("title", ""))),
                source=escape(str(item.get("source", "unknown"))),
                sentiment=escape(format_sentiment_label(str(item.get("sentiment_label", "neutral")))),
                confidence=confidence_pct,
                tags=tags or '<span class="tag">Uncategorized</span>',
            )
        )
    return '<div class="coverage-grid">' + "".join(cards) + "</div>"


def build_methodology_card() -> str:
    return """
    <div class="card">
      <div class="kicker">Methodology</div>
      <p class="subtle">
        This report is generated from a rules-based workflow that combines public financial
        news with daily market proxy moves. The goal is to summarize the day in a transparent,
        low-cost, and methodologically cautious way.
      </p>
      <p class="subtle">
        1. News collection: The system gathers headlines and summaries from a small set of
        public financial RSS feeds. Only macro-relevant coverage is kept for analysis.
      </p>
      <p class="subtle">
        2. Theme detection: Each article is tagged with one or more macro themes such as
        policy, inflation, growth, liquidity, FX, energy, or risk. Theme tags help organize
        the coverage, but they do not determine the final daily sentiment on their own.
      </p>
      <p class="subtle">
        3. News sentiment classification: News sentiment is classified with FinBERT, a
        financial-language model that labels text as positive, neutral, or negative. The
        model measures financial tone; it does not directly determine whether individual
        macroeconomic variables are rising or falling.
      </p>
      <p class="subtle">
        4. Daily sentiment aggregation: The daily result is based on unique documents only.
        If the same article appears under more than one theme, it is still counted once in
        the daily sentiment score. Individual labels are converted into a simple numerical
        scale and averaged to produce the aggregated daily news sentiment.
      </p>
      <p class="subtle">
        5. Market response classification: The market side is evaluated using a small basket
        of daily risk proxies. SPY and HYG are the primary signals, while TLT and GLD are
        treated as secondary defensive signals. UUP and USO are shown as context, but they
        are not used to determine the main regime because their interpretation is more
        conditional.
      </p>
      <p class="subtle">
        6. News-market confirmation: The confirmation step compares aggregated news sentiment
        with the market’s broader risk-on, risk-off, or mixed response. A match suggests
        that both moved in the same general direction. A mismatch does not mean the model
        failed: markets may be reacting to other catalysts, delayed repricing, incomplete
        information, or news that was already priced in.
      </p>
      <p class="subtle">
        7. Interpretation limits: This framework is designed for transparency, not false
        precision. It does not claim causality, predictive power, or trading accuracy. It is
        a structured daily read on how financial news tone and market behavior related to
        each other on a given day.
      </p>
    </div>
    """


def build_report_section(report: dict[str, object], featured: bool = False) -> str:
    report_id = escape(str(report["date"]))
    title = "Latest Report" if featured else f"Archive Report | {report_id}"
    return """
    <section class="section" id="report-{report_id}">
      <div class="card">
        <div class="kicker">{title}</div>
        <h2>{date}</h2>
        <p>{daily_brief}</p>
      </div>

      <div class="signal-grid">
        <div class="card">
          <div class="kicker">Macro Read</div>
          <div class="value">{macro_read}</div>
          <div class="subtle">Daily read from the news coverage examined by the pipeline</div>
        </div>
        {news_sentiment_card}
        {confirmation_card}
      </div>

      <div class="section">
        <h2>Market Snapshot</h2>
        {market_cards}
      </div>

      <div class="section">
        <h2>Market Context</h2>
        {market_regime_card}
      </div>

      <div class="section">
        <h2>Analyzed Coverage</h2>
        <p class="subtle">Each article appears once here, even if it touches more than one theme.</p>
        {coverage_cards}
      </div>

      <div class="section">
        <h2>RSS Feeds Examined</h2>
        <p class="subtle">These are the public RSS feed URLs configured for the pipeline. Not every feed contributes a headline every day.</p>
        {feed_sources}
      </div>

      <div class="section">
        <h2>Method Notes</h2>
        {methodology_card}
      </div>
    </section>
    """.format(
        report_id=report_id,
        title=escape(title),
        date=escape(str(report["date"])),
        daily_brief=escape(str(report["daily_brief"])),
        macro_read=escape(str(report["macro_read"]).replace("Macro read: ", "")),
        news_sentiment_card=build_news_sentiment_card(report),
        confirmation_card=build_confirmation_card(report),
        market_cards=build_market_cards(list(report.get("market_snapshot", []))),
        market_regime_card=build_market_regime_card(report),
        coverage_cards=build_coverage_cards(report),
        feed_sources=build_feed_sources(report),
        methodology_card=build_methodology_card(),
    )


def render_site(reports: list[dict[str, object]]) -> str:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not reports:
        return """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{site_title}</title>
    <meta name="description" content="{tagline}">
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <p class="eyebrow">Macro Intelligence Demo</p>
        <h1>{site_title}</h1>
        <p class="tagline">{tagline}</p>
        <div class="meta-row">
          <div class="card">
            <div class="kicker">Status</div>
            <div class="value">Waiting for Data</div>
            <div class="subtle">The pipeline ran, but no qualifying news items were available.</div>
          </div>
          <div class="card">
            <div class="kicker">Last Build</div>
            <div class="value">{updated_at}</div>
            <div class="subtle">Published via GitHub Pages</div>
          </div>
        </div>
      </section>
      <section class="section">
        {methodology_card}
      </section>
    </main>
  </body>
</html>
""".format(
            site_title=escape(SITE_TITLE),
            tagline=escape(SITE_TAGLINE),
            updated_at=escape(updated_at),
            methodology_card=build_methodology_card(),
        )

    latest = reports[-1]
    return """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{site_title}</title>
    <meta name="description" content="{tagline}">
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <p class="eyebrow">Macro Intelligence Demo</p>
        <h1>{site_title}</h1>
        <p class="tagline">{tagline}</p>
        <div class="meta-row">
          <div class="card">
            <div class="kicker">Latest Date</div>
            <div class="value">{latest_date}</div>
            <div class="subtle">Auto-generated end-of-day report</div>
          </div>
          <div class="card">
            <div class="kicker">Last Build</div>
            <div class="value">{updated_at}</div>
            <div class="subtle">Published via GitHub Pages</div>
          </div>
          <div class="card">
            <div class="kicker">What It Does</div>
            <div class="value">News + Market</div>
            <div class="subtle">Aggregates news tone, tracks market proxies, and checks whether both were aligned.</div>
          </div>
        </div>
      </section>

      {latest_section}

      <footer class="footer">
        Built from public RSS feeds and free market proxies. This demo is generated automatically from the pipeline in this repository.
      </footer>
    </main>
  </body>
</html>
""".format(
        site_title=escape(SITE_TITLE),
        tagline=escape(SITE_TAGLINE),
        latest_date=escape(str(latest["date"])),
        updated_at=escape(updated_at),
        latest_section=build_report_section(latest, featured=True),
    )


def generate_site(news_path: str | Path, market_path: str | Path | None, output_dir: str | Path) -> Path:
    documents = load_documents(news_path)
    signals = [analyze_document(doc) for doc in documents]
    market_data = load_market_data(market_path)
    reports = build_report_data(signals, market_data=market_data, debug=False)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "styles.css").write_text(CSS, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "report-data.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    (output / "index.html").write_text(render_site(reports), encoding="utf-8")
    return output / "index.html"


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Generate a static GitHub Pages site.")
    parser.add_argument("--input", default=str(project_root / "data" / "latest_news.json"))
    parser.add_argument("--market", default=str(project_root / "data" / "latest_market.json"))
    parser.add_argument("--output-dir", default=str(project_root / "docs"))
    args = parser.parse_args()

    market_path = args.market if Path(args.market).exists() else None
    index_path = generate_site(args.input, market_path, args.output_dir)
    print(f"Generated static site at {index_path}")


if __name__ == "__main__":
    main()
