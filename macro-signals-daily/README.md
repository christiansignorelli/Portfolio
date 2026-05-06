# Macro Signals Daily

Macro Signals Daily is a lightweight end-of-day macro market wrap-up that reads public financial news, classifies macro narrative shifts, and checks whether market proxies confirm the story.

The project was built as a low-cost alternative to an always-on LLM API workflow. Instead of relying on expensive model calls for every article, it uses transparent rule-based logic, public RSS feeds, and free market data to generate a daily HTML brief.

## What it does

- Pulls macro-relevant headlines from public RSS feeds
- Filters out lower-signal market noise
- Classifies narrative shifts across themes like policy, inflation, growth, liquidity, and risk
- Pulls free market proxy data for equities, bonds, dollar, oil, credit, and gold
- Compares language signals to expected market behavior
- Publishes a daily static HTML report through GitHub Pages

## Why I built it

I wanted to explore how far a practical macro-monitoring workflow could go without depending on expensive LLM API usage.

This project is meant to show:
- explainable signal generation
- lightweight automation
- daily report publishing
- a realistic research workflow built from public data

## How the workflow works

1. Fetch financial headlines from public RSS feeds
2. Score headlines with macro-focused rules and keyword buckets
3. Aggregate signal tone for the day
4. Pull free market proxy data from Yahoo Finance
5. Cross-check whether market moves align with the narrative
6. Generate a static HTML market wrap-up
7. Publish automatically with GitHub Actions

## Market proxies used

- `SPY` for U.S. equities
- `TLT` for long-duration Treasuries
- `UUP` for U.S. dollar exposure
- `USO` for oil
- `HYG` for high-yield credit
- `GLD` for gold

## Strengths of this approach

- Very low operating cost
- Transparent and explainable logic
- Consistent output across runs
- Easy to automate and publish
- Good fit for a public-facing demo or MVP

## Limitations

- Less flexible than an LLM when language is nuanced or ambiguous
- Can miss meaning when wording changes
- Depends on rule tuning over time
- Uses RSS summaries instead of deep full-article understanding
- Market confirmation is heuristic, not a full macro model

## Automation

The project is set up to run automatically with GitHub Actions and publish to GitHub Pages.

Current design goal:
- end-of-day market wrap-up
- previous report remains visible until the next daily run publishes a new one

## Project structure

```text
macro-signals-daily/
  fetch_news.py
  fetch_market.py
  generate_site.py
  macro_signals/
    __init__.py
    analyzer.py
