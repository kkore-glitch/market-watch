from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .ai import generate_ai_summary
from .analysis import collect_chip_data, pressure_reading
from .config import load_config, target_to_dict
from .data_sources import FinMindClient, YahooChartClient, fetch_price
from .indicators import add_indicators, latest_signal
from .report import render_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Taiwan and US market watch report")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Generate a market report")
    run.add_argument("--config", default="config/targets.yaml")
    run.add_argument("--as-of", default=date.today().isoformat())
    run.add_argument("--output")
    run.add_argument("--no-ai", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    if args.command == "run":
        run_report(args)


def run_report(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    start = as_of - timedelta(days=config.lookback_days * 2)
    finmind = FinMindClient()
    yahoo = YahooChartClient()

    target_reports: list[dict[str, Any]] = []
    news_items: list[dict[str, Any]] = []

    for target in config.targets:
        prices = fetch_price(target, start, as_of, finmind, yahoo)
        signal = latest_signal(add_indicators(prices))
        chip = collect_chip_data(target, finmind, as_of)
        item = target_to_dict(target)
        item["signal"] = signal
        item["chip"] = chip
        item["pressure_reading"] = pressure_reading(signal, chip)
        target_reports.append(item)

        if target.group.startswith("taiwan") and target.id != "TAIEX":
            try:
                news = finmind.get_news(target.id, as_of)
                news_items.extend(news.to_dict(orient="records"))
            except Exception:
                pass

    payload = {
        "as_of": as_of.isoformat(),
        "targets": target_reports,
        "news": dedupe_news(news_items),
        "source_notes": [
            "FinMind API for Taiwan price, institutional, margin, news, and US daily price data when available.",
            "Yahoo Finance chart endpoint is used as fallback for index and price history. It is unofficial and should be cross-checked for production use.",
        ],
    }
    ai_summary = None if args.no_ai else generate_ai_summary(payload)
    markdown = render_markdown(payload, ai_summary)
    output = Path(args.output) if args.output else config.output_dir / f"market-{as_of.isoformat()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(output)


def dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("date")), str(item.get("title")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


if __name__ == "__main__":
    main()
