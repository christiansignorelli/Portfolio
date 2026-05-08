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
SITE_TAGLINE = "End-of-day market wrap-up from news language and market confirmation"

CSS = """
:root {
  --bg: #f4efe7;
  --panel: #fffdf8;
  --panel-strong: #f7f1e8;
  --ink: #1f2933;
  --muted: #5d6b78;
  --line: #d7cfc2;
  --shadow: 0 12px 30px rgba(31, 41, 51, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  background:
    radial-gradient(circle at top left, rgba(22, 93, 255, 0.08), transparent 35%),
    linear-gradient(180deg, #fbf7f0 0%, var(--bg) 100%);
  color: var(--ink);
}
.page { width: min(1120px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 72px; }
.hero, .card, .bucket-card, .market-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: var(--shadow);
}
.hero { padding: 28px; }
.card, .bucket-card { padding: 20px; }
.market-card { padding: 16px; }
.eyebrow, .kicker {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  color: var(--muted);
}
h1 { margin: 0; font-size: clamp(34px, 6vw, 64px); line-height: 0.95; }
h2 { margin: 0 0 12px; font-size: 24px; }
.tagline, .subtle, .section p, .source, .footer { color: var(--muted); }
.tagline { margin: 14px 0 0; max-width: 720px; font-size: 18px; }
.meta-row, .signal-grid, .market-grid, .bucket-grid {
  display: grid;
  gap: 16px;
}
.meta-row { margin-top: 22px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.signal-grid, .bucket-grid { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.market-grid { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.explain-grid { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.section { margin-top: 28px; }
.value { font-size: 28px; line-height: 1.05; margin: 0 0 8px; }
.status {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  background: var(--panel-strong);
  margin-bottom: 12px;
}
ul { margin: 12px 0 0; padding-left: 18px; }
li + li { margin-top: 8px; }
.headline { font-weight: 700; }
.footer { margin-top: 36px; font-size: 13px; }
.mini-list { margin: 10px 0 0; padding-left: 18px; color: var(--muted); }
.mini-list li + li { margin-top: 6px; }
.source-list {
  margin: 14px 0 0;
  padding-left: 18px;
}
.source-list li + li {
  margin-top: 8px;
}
.source-list a {
  color: #114c9b;
  text-decoration: none;
}
.source-list a:hover {
  text-decoration: underline;
}
.check-list {
  display: grid;
