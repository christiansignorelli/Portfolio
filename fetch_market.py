from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


MARKET_PROXIES = {
    "SPY": {"yahoo": "SPY", "label": "US equities"},
    "TLT": {"yahoo": "TLT", "label": "Long-duration Treasuries"},
    "GLD": {"yahoo": "GLD", "label": "Gold"},
    "USO": {"yahoo": "USO", "label": "Oil proxy"},
    "UUP": {"yahoo": "UUP", "label": "US dollar proxy"},
    "HYG": {"yahoo": "HYG", "label": "High yield credit"},
}


@dataclass
class MarketSnapshot:
    symbol: str
    label: str
    as_of: str
    close: float
    return_1d: float
    return_5d: float


def fetch_url(url: str, timeout: int = 20) -> str:
    request = Request(
        url,
        headers={"User-Agent": "MacroSignalsAnalyzer/0.1 (+market fetcher)"},
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def parse_yahoo_chart(text: str) -> tuple[list[int], list[float]]:
    payload = json.loads(text)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    closes = result["indicators"]["quote"][0].get("close", [])

    filtered_pairs = [
        (ts, close)
        for ts, close in zip(timestamps, closes)
        if close is not None
    ]
    if not filtered_pairs:
        return [], []

    clean_timestamps = [ts for ts, _ in filtered_pairs]
    clean_closes = [float(close) for _, close in filtered_pairs]
    return clean_timestamps, clean_closes


def fetch_symbol(symbol: str, yahoo_symbol: str, label: str) -> MarketSnapshot:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{yahoo_symbol}?range=1mo&interval=1d&includePrePost=false"
    )
    text = fetch_url(url)
    timestamps, closes = parse_yahoo_chart(text)
    if len(closes) < 2:
        raise ValueError(f"Not enough price history for {symbol}")

    latest_ts = timestamps[-1]
    latest_close = closes[-1]
    close_1d = closes[-2]
    close_5d = closes[-6] if len(closes) >= 6 else closes[0]

    return MarketSnapshot(
        symbol=symbol,
        label=label,
        as_of=datetime.fromtimestamp(latest_ts, tz=timezone.utc).date().isoformat(),
        close=latest_close,
        return_1d=round(pct_change(latest_close, close_1d), 2),
        return_5d=round(pct_change(latest_close, close_5d), 2),
    )


def save_snapshots(snapshots: list[MarketSnapshot], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": max(snapshot.as_of for snapshot in snapshots) if snapshots else None,
        "snapshots": [
            {
                "symbol": snapshot.symbol,
                "label": snapshot.label,
                "as_of": snapshot.as_of,
                "close": snapshot.close,
                "return_1d": snapshot.return_1d,
                "return_5d": snapshot.return_5d,
            }
            for snapshot in snapshots
        ],
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Fetch free daily market proxy prices.")
    parser.add_argument(
        "--output",
        default=str(project_root / "data" / "latest_market.json"),
        help="Where to save the fetched market data.",
    )
    args = parser.parse_args()

    snapshots: list[MarketSnapshot] = []
    errors: list[str] = []

    for symbol, config in MARKET_PROXIES.items():
        try:
            snapshots.append(fetch_symbol(symbol, config["yahoo"], config["label"]))
        except (URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{symbol}: {exc}")

    output = save_snapshots(snapshots, args.output)
    print(f"Saved {len(snapshots)} market snapshots to {output}")
    if errors:
        print("")
        print("Symbols with errors:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
