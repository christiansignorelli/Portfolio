from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

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
.hero, .card, .bucket-card, .market-card, .archive-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: var(--shadow);
}
.hero { padding: 28px; }
.card, .bucket-card { padding: 20px; }
.market-card, .archive-card { padding: 16px; }
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
.meta-row, .signal-grid, .market-grid, .bucket-grid, .archive-list {
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
.archive-list { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 14px; }
.archive-card a { color: var(--ink); text-decoration: none; }
.footer { margin-top: 36px; font-size: 13px; }
.mini-list { margin: 10px 0 0; padding-left: 18px; color: var(--muted); }
.mini-list li + li { margin-top: 6px; }
.check-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}
.check-item {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.68);
}
.check-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.check-label {
  font-weight: 700;
}
.check-badge {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}
.check-yes {
  background: rgba(30, 122, 70, 0.12);
  color: #1b6c42;
}
.check-no {
  background: rgba(160, 49, 49, 0.12);
  color: #8d2c2c;
}
@media (max-width: 720px) {
  .page { width: min(100vw - 20px, 1120px); padding-top: 16px; }
}
"""


def format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


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


def build_crosscheck_explainer(report: dict[str, object]) -> str:
    unavailable = (
        not report["market_confirmation"]
        or "not enough market context" in str(report["market_confirmation"]).lower()
    )

    why_unavailable = (
        "<p class='subtle'>Why it may be unavailable: the build likely ran without a valid market snapshot file, "
        "or too few proxies were fetched to run the checks. Yes, that usually does depend on the specific run "
        "timing and data availability when the page was generated.</p>"
        if unavailable
        else "<p class='subtle'>In this run, enough proxies were available to compare the language signal against market behavior.</p>"
    )

    return """
    <div class="signal-grid explain-grid">
      <div class="card">
        <div class="kicker">How Cross-Check Works</div>
        <p class="subtle">
          The system first classifies the day's language into signals like hawkish policy,
          cooling inflation, softening growth, or risk-off. It then asks whether a small
          set of market proxies moved the way that narrative would normally suggest.
        </p>
        <ul class="mini-list">
          <li>Hawkish policy: bonds weaker, dollar firmer.</li>
          <li>Cooling inflation: bonds stronger.</li>
          <li>Inflation pressure: oil up, bonds weaker.</li>
          <li>Risk-off: equities and high-yield credit weaker.</li>
        </ul>
      </div>
      <div class="card">
        <div class="kicker">Availability</div>
        {why_unavailable}
      </div>
    </div>
    """.format(why_unavailable=why_unavailable)


def build_market_checks(report: dict[str, object]) -> str:
    checks = list(report.get("market_checks", []))
    if not checks:
        return "<p class='subtle'>No detailed checks were available for this run.</p>"

    items = []
    for check in checks:
        badge = "Confirmed" if check["confirmed"] else "Not confirmed"
        badge_class = "check-yes" if check["confirmed"] else "check-no"
        items.append(
            """
            <div class="check-item">
              <div class="check-top">
                <div class="check-label">{label}</div>
                <span class="check-badge {badge_class}">{badge}</span>
              </div>
              <div class="subtle">{expected}</div>
            </div>
            """.format(
                label=escape(str(check["label"]).title()),
                badge_class=badge_class,
                badge=badge,
                expected=escape(str(check["expected"])),
            )
        )
    return '<div class="check-list">' + "".join(items) + "</div>"


def build_bucket_cards(bucket_views: list[dict[str, object]]) -> str:
    cards = []
    for bucket in bucket_views:
        headlines = "".join(
            """
            <li>
              <div class="headline">{title}</div>
              <div class="source">{source}</div>
            </li>
            """.format(
                title=escape(str(doc["title"])),
                source=escape(str(doc["source"])),
            )
            for doc in bucket["documents"]
        )
        cards.append(
            """
            <article class="bucket-card">
              <div class="status">{name} | {label}</div>
              <ul>{headlines}</ul>
            </article>
            """.format(
                name=escape(str(bucket["name"])).upper(),
                label=escape(str(bucket["label"])),
                headlines=headlines,
            )
        )
    return '<div class="bucket-grid">' + "".join(cards) + "</div>"


def build_archive_cards(reports: list[dict[str, object]]) -> str:
    if len(reports) <= 1:
        return "<p class='subtle'>The archive will fill in as daily runs accumulate.</p>"

    cards = []
    for report in reversed(reports[:-1]):
        cards.append(
            """
            <div class="archive-card">
              <a href="#report-{date}">
                <strong>{date}</strong><br>
                <span class="subtle">{macro_read}</span>
              </a>
            </div>
            """.format(
                date=escape(str(report["date"])),
                macro_read=escape(str(report["macro_read"])),
            )
        )
    return '<div class="archive-list">' + "".join(cards) + "</div>"


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
          <div class="subtle">Language-derived daily interpretation</div>
        </div>
        <div class="card">
          <div class="kicker">Market Check</div>
          <div class="value">{market_confirmation}</div>
          <div class="subtle">Compares the language signal with bonds, the dollar, oil, equities, and credit proxies</div>
        </div>
      </div>

      <div class="section">
        <h2>Market Snapshot</h2>
        {market_cards}
      </div>

      <div class="section">
        <h2>Cross-Check Logic</h2>
        {crosscheck_explainer}
        {market_checks}
      </div>

      <div class="section">
        <h2>Signal Buckets</h2>
        {bucket_cards}
      </div>
    </section>
    """.format(
        report_id=report_id,
        title=escape(title),
        date=escape(str(report["date"])),
        daily_brief=escape(str(report["daily_brief"])),
        macro_read=escape(str(report["macro_read"]).replace("Macro read: ", "")),
        market_confirmation=escape(str(report["market_confirmation"] or "No market data")),
        market_cards=build_market_cards(list(report["market_snapshot"])),
        crosscheck_explainer=build_crosscheck_explainer(report),
        market_checks=build_market_checks(report),
        bucket_cards=build_bucket_cards(list(report["bucket_views"])),
    )


def render_site(reports: list[dict[str, object]]) -> str:
    if not reports:
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
    </main>
  </body>
</html>
""".format(
            site_title=escape(SITE_TITLE),
            tagline=escape(SITE_TAGLINE),
            updated_at=escape(updated_at),
        )

    latest = reports[-1]
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
            <div class="subtle">Reads RSS headlines, classifies macro tone, and publishes a post-close market wrap-up</div>
          </div>
        </div>
      </section>

      {latest_section}

      <section class="section">
        <div class="card">
          <div class="kicker">Report Archive</div>
          <h2>Previous Snapshots</h2>
          <p>Useful as a public demo of how the system would look for clients as it builds a daily history.</p>
          {archive_cards}
        </div>
      </section>

      {archive_sections}

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
        archive_cards=build_archive_cards(reports),
        archive_sections="".join(build_report_section(report) for report in reversed(reports[:-1])),
    )


def generate_site(news_path: str | Path, market_path: str | Path | None, output_dir: str | Path) -> Path:
    documents = load_documents(news_path)
    if not documents:
        project_root = Path(__file__).resolve().parent
        sample_path = project_root / "data" / "sample_news.json"
        if sample_path.exists():
            documents = load_documents(sample_path)
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
