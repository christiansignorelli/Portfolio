# Macro Signals Daily

Macro Signals Daily is a lightweight end-of-day macro market wrap-up that reads public financial news, detects macro themes, scores each document with FinBERT financial sentiment, and displays market proxies as context.

The project was built as a low-cost alternative to an always-on LLM API workflow. It uses public RSS feeds, the open Hugging Face `ProsusAI/finbert` model, and free market data to generate a daily HTML brief.

## What it does

- Pulls macro-relevant headlines from public RSS feeds
- Filters out lower-signal market noise
- Detects themes like policy, inflation, growth, liquidity, and risk
- Scores each document as positive, negative, or neutral financial sentiment with FinBERT
- Pulls free market proxy data for equities, bonds, dollar, oil, credit, and gold
- Shows market proxy data as context
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
2. Detect macro-focused keyword buckets
3. Score financial sentiment with FinBERT
4. Pull free market proxy data from Yahoo Finance
5. Display market moves as context without treating sentiment as macro direction
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
- Transparent theme detection with FinBERT sentiment labels
- Consistent output across runs
- Easy to automate and publish
- Good fit for a public-facing demo or MVP

## Limitations

- Less flexible than an LLM when language is nuanced or ambiguous
- FinBERT measures financial tone, not whether inflation, rates, growth, or liquidity are rising or falling
- Keyword theme detection can miss meaning when wording changes
- Uses RSS summaries instead of deep full-article understanding
- Market data is contextual and is not used as directional confirmation of FinBERT sentiment

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
