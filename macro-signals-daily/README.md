# Macro Signals Daily

Macro Signals Daily is a lightweight end-of-day macro market wrap-up. It reads public financial RSS feeds, filters for macro-relevant headlines, scores each qualifying document with FinBERT financial sentiment, pulls free market proxy data, and publishes a static HTML brief through GitHub Pages.

Live demo:

- Portfolio page: <https://christiansignorelli.github.io/Portfolio/>
- Current report: <https://christiansignorelli.github.io/Portfolio/macro-signals-daily/>
- Legacy route redirect: <https://christiansignorelli.github.io/Portfolio/macro-signals/>

## Why This Exists

This project explores how far a practical macro-monitoring workflow can go without an always-on LLM API. The goal is a low-cost, explainable daily research product built from public data and repeatable rules.

It is meant to demonstrate:

- automated public-data collection
- transparent macro theme detection
- FinBERT-based financial sentiment scoring
- a simple news-versus-market confirmation framework
- scheduled publishing with GitHub Actions
- a realistic, portfolio-ready research workflow

## What It Does

- Pulls macro-relevant headlines from public RSS feeds
- Filters out lower-signal market noise
- Detects themes like policy, inflation, growth, liquidity, rates, energy, FX, and risk
- Scores each document as positive, negative, or neutral financial sentiment using `ProsusAI/finbert`
- Aggregates the day into a single news sentiment score using unique documents only
- Pulls market proxy data from Yahoo Finance
- Classifies the day as `risk_on`, `risk_off`, or `mixed` from a weighted proxy basket
- Compares aggregated news tone with the market response
- Generates `index.html`, `styles.css`, and `report-data.json`

## Methodology

FinBERT measures financial tone. It does not directly tell us whether inflation, rates, liquidity, or growth are rising or falling.

Because of that, the project does not compare sentiment directly with any single macro variable. Instead, it compares the aggregated tone of the news with a basket of risk-on and risk-off market proxies.

### News Sentiment

- Each analyzed document keeps its model label: `positive`, `neutral`, or `negative`
- For the daily aggregate, labels are converted to `+1`, `0`, and `-1`
- The project deduplicates documents before aggregation so the same headline is not counted twice
- The daily score becomes:
  - `positive` when the average is at least `+0.20`
  - `negative` when the average is at most `-0.20`
  - `neutral` otherwise
- If fewer than 3 unique documents are available, the daily label becomes `insufficient_data`

### Market Confirmation

The confirmation framework compares the aggregated news tone with a weighted market basket:

- `SPY` and `HYG` are the main signals
- `TLT` and `GLD` are secondary defensive signals
- `UUP` and `USO` are shown as context only

The market regime is based on daily moves, not five-day moves.

Initial weights:

- `SPY`: 0.40
- `HYG`: 0.35
- `TLT`: 0.15
- `GLD`: 0.10

Interpretation:

- Rising `SPY` or `HYG` supports `risk_on`
- Falling `SPY` or `HYG` supports `risk_off`
- Rising `TLT` or `GLD` leans defensive and therefore toward `risk_off`
- Falling `TLT` or `GLD` leans toward `risk_on`

Small daily moves inside `+/- 0.20%` are treated as neutral noise.

### Confirmation Status

The report then compares both sides:

- `confirmed`
- `divergent`
- `unconfirmed`
- `market_led`
- `neutral`
- `insufficient_data`

Important:

- confirmation does not imply causality
- confirmation does not imply predictive power
- a `divergent` result does not automatically mean the model was incorrect
- divergence can happen because news was already priced in, the reaction was delayed, other catalysts dominated, or data was incomplete

## Data Sources

News feeds:

- <https://www.marketwatch.com/rss/topstories>
- <https://www.investing.com/rss/news_14.rss>

Market proxy data:

- Yahoo Finance chart API

Market proxies:

- `SPY` for U.S. equities
- `HYG` for high-yield credit
- `TLT` for long-duration Treasuries
- `GLD` for gold
- `UUP` for U.S. dollar context
- `USO` for oil context

## Workflow

The scheduled workflow lives at:

```text
.github/workflows/daily-macro-signals.yml
```

It runs daily at:

```text
21:15 UTC
```

The workflow:

1. Checks out the repository
2. Installs Python dependencies from `macro-signals-daily/requirements.txt`
3. Fetches public RSS headlines with `fetch_news.py`
4. Fetches market proxy data with `fetch_market.py`
5. Generates the static site with `generate_site.py --output-dir macro-signals-daily`
6. Commits updated generated files back to `main`
7. GitHub Pages serves the updated static files

## Generated Files

The daily workflow updates these files inside `macro-signals-daily/`:

```text
data/latest_market.json
data/latest_news.json
index.html
report-data.json
styles.css
```

`report-data.json` is the structured output used by the generated HTML and is the fastest way to verify the latest report date.

## Local Run

From the repository root:

```bash
python3 -m pip install -r macro-signals-daily/requirements.txt
python3 macro-signals-daily/fetch_news.py
python3 macro-signals-daily/fetch_market.py
python3 macro-signals-daily/generate_site.py --output-dir macro-signals-daily
```

Then open:

```text
macro-signals-daily/index.html
```

## Project Structure

```text
macro-signals-daily/
  data/
    latest_market.json
    latest_news.json
  fetch_market.py
  fetch_news.py
  generate_site.py
  index.html
  macro_signals/
    __init__.py
    analyzer.py
  report-data.json
  requirements.txt
  styles.css
  tests/
    test_analyzer.py
```

## Strengths

- very low operating cost
- transparent rules and scoring
- clear separation between news tone and market reaction
- consistent scheduled output
- static hosting through GitHub Pages

## Limitations

- RSS summaries are thinner than full article text
- keyword theme detection can miss nuance when wording changes
- FinBERT measures financial sentiment, not macro direction
- market proxies are noisy and context-dependent
- free data sources can occasionally fail, lag, or change response formats

## Status

The current production route is:

```text
https://christiansignorelli.github.io/Portfolio/macro-signals-daily/
```

The old route redirects here:

```text
https://christiansignorelli.github.io/Portfolio/macro-signals/
```
