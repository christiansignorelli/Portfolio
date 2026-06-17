# Macro Signals Daily

Macro Signals Daily is a lightweight end-of-day macro market wrap-up. It reads public financial RSS feeds, filters for macro-relevant headlines, scores each qualifying document with FinBERT financial sentiment, pulls free market proxy data, and publishes a static HTML brief through GitHub Pages.

Live demo:

- Portfolio page: <https://christiansignorelli.github.io/Portfolio/>
- Current report: <https://christiansignorelli.github.io/Portfolio/macro-signals-daily/>
- Legacy route redirect: <https://christiansignorelli.github.io/Portfolio/macro-signals/>

## Why This Exists

This project explores how far a practical macro-monitoring workflow can go without depending on an always-on LLM API. The goal is a low-cost, explainable daily research product built from public data and repeatable rules.

It is meant to demonstrate:

- automated public-data collection
- transparent macro theme detection
- FinBERT-based financial sentiment scoring
- market proxy context
- scheduled publishing with GitHub Actions
- a realistic, portfolio-ready research workflow

## What It Does

- Pulls macro-relevant headlines from public RSS feeds
- Filters out lower-signal market noise
- Detects themes like policy, inflation, growth, liquidity, rates, energy, FX, and risk
- Scores each document as positive, negative, or neutral financial sentiment using `ProsusAI/finbert`
- Pulls market proxy data from Yahoo Finance
- Shows market moves as context
- Generates `index.html`, `styles.css`, and `report-data.json`
- Publishes a daily static report through GitHub Pages

## Important Interpretation Note

FinBERT measures financial tone. It does not directly say whether inflation, rates, growth, liquidity, or risk are rising or falling.

Because of that, the current design shows market proxy data as context, but does not treat market moves as directional confirmation of FinBERT sentiment. This avoids presenting a false precision signal.

## Data Sources

News feeds:

- <https://www.marketwatch.com/rss/topstories>
- <https://www.investing.com/rss/news_14.rss>

Market proxy data:

- Yahoo Finance chart API

Market proxies:

- `SPY` for U.S. equities
- `TLT` for long-duration Treasuries
- `UUP` for U.S. dollar exposure
- `USO` for oil
- `HYG` for high-yield credit
- `GLD` for gold

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
data/latest_news.json
data/latest_market.json
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

## Route Migration

There are two similarly named routes in the portfolio:

```text
/Portfolio/macro-signals/
/Portfolio/macro-signals-daily/
```

`macro-signals-daily/` is the live project.

`macro-signals/` was an older static demo route that contained mock/snapshot data from April 2026. It is now kept only as a redirect to `macro-signals-daily/` so old bookmarks do not show stale training/demo data.

If the site ever appears to be showing `2026-04-28` or `2026-04-29`, the browser is almost certainly loading the old route or a cached GitHub Pages response. The correct live route should show the latest generated date from `macro-signals-daily/report-data.json`.

Quick checks:

```bash
curl -L -s "https://christiansignorelli.github.io/Portfolio/macro-signals-daily/report-data.json" | head
curl -L -s "https://christiansignorelli.github.io/Portfolio/macro-signals/?v=$(date +%s)" | grep -E "macro-signals-daily|2026-04"
```

Expected result:

- `macro-signals-daily/report-data.json` shows the current generated report date
- `macro-signals/` contains `macro-signals-daily` and does not serve the April snapshot

## Troubleshooting

If the report is stale:

1. Check the latest GitHub Actions run for `Daily Macro Signals Update`
2. Confirm `macro-signals-daily/report-data.json` changed on `main`
3. Confirm GitHub Pages has finished publishing the latest commit
4. Bust browser/CDN cache by appending a query string, for example `?v=timestamp`
5. If Pages still serves an old file after the commit landed, push an empty commit to trigger a rebuild:

```bash
git commit --allow-empty -m "Trigger Pages rebuild"
git push origin main
```

If a local checkout cannot run `git fetch`, `git commit`, or `git push` because `.git` is blocked by local filesystem permissions, use a fresh clone or run the publish commands from a normal Terminal session.

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

- Very low operating cost
- Transparent theme detection
- FinBERT sentiment labels instead of opaque generated narratives
- Consistent scheduled output
- Static hosting through GitHub Pages
- Good fit for a public-facing demo or MVP

## Limitations

- RSS summaries are thinner than full article text
- Keyword theme detection can miss nuance when wording changes
- FinBERT measures financial sentiment, not macro direction
- Market data is contextual and should not be treated as investment advice
- Free data sources can occasionally fail, lag, or change response formats

## Status

The current production route is:

```text
https://christiansignorelli.github.io/Portfolio/macro-signals-daily/
```

The old route redirects here:

```text
https://christiansignorelli.github.io/Portfolio/macro-signals/
```
