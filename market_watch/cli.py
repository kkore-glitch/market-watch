from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .ai import build_ai_prompt, generate_ai_summary
from .analysis import collect_chip_data, human_interpretation, pressure_reading
from .config import load_config, target_to_dict
from .data_sources import (
    FinMindClient,
    GoogleNewsClient,
    StooqClient,
    TwseOhlcClient,
    YahooChartClient,
    aggregate_intraday,
    fetch_price,
)
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
    stooq = StooqClient()
    google_news = GoogleNewsClient()
    twse_ohlc = TwseOhlcClient()

    target_reports: list[dict[str, Any]] = []
    news_items: list[dict[str, Any]] = []
    collection_errors: list[str] = []

    for target in config.targets:
        item = target_to_dict(target)
        try:
            prices = fetch_price(target, start, as_of, finmind, yahoo, stooq)
            signal = latest_signal(add_indicators(prices))
            intraday = intraday_sparkline(target, finmind, yahoo, twse_ohlc, as_of)
            signal["intraday_sparkline"] = intraday["points"]
            signal["intraday_source"] = intraday["source"]
            signal["intraday_note"] = intraday["note"]
            signal["intraday_error"] = intraday["error"]
            chip = collect_chip_data(target, finmind, as_of)
            item["signal"] = signal
            item["chip"] = chip
            item["pressure_reading"] = pressure_reading(signal, chip)
            item["interpretation"] = human_interpretation(target, signal, chip)
        except Exception as exc:
            message = f"{target.name} ({target.id}) 資料取得失敗: {exc}"
            item["error"] = message
            item["signal"] = None
            item["chip"] = {}
            item["pressure_reading"] = ["資料不足，暫不判斷買賣壓來源"]
            item["interpretation"] = {
                "tone": "資料不足",
                "score": 0,
                "summary": "資料取得失敗，今日不產生市場解讀。",
                "action": "先補齊資料，不用這筆結果做判斷。",
                "facts": [],
            }
            collection_errors.append(message)
        target_reports.append(item)

        if not item.get("error") and target.group.startswith("taiwan") and target.id != "TAIEX":
            try:
                news = finmind.get_news(target.id, as_of)
                news_items.extend(news.to_dict(orient="records"))
            except Exception as exc:
                collection_errors.append(f"{target.name} ({target.id}) 新聞取得失敗: {exc}")

    for query in market_driver_queries(as_of):
        try:
            news_items.extend(google_news.search(query, limit=6))
        except Exception as exc:
            collection_errors.append(f"市場驅動新聞取得失敗 ({query}): {exc}")

    payload = {
        "as_of": as_of.isoformat(),
        "targets": target_reports,
        "news": sort_news_items(dedupe_news(news_items)),
        "collection_errors": collection_errors,
        "source_notes": [
            "FinMind API for Taiwan price, institutional, margin, news, and US daily price data when available.",
            "Google News RSS is used for market-driver headlines such as AI semiconductors, NVIDIA earnings, US indexes, yields, and Taiwan market rebound narratives.",
            "30-minute mini charts use TWSE index OHLC, FinMind intraday data when available, then Yahoo Finance chart endpoint as fallback. If all fail, the PWA shows intraday data as unavailable instead of falling back to a daily trend.",
            "Stooq daily CSV can be used as an optional fallback for configured symbols when STOOQ_API_KEY is set.",
        ],
    }
    ai_summary = None if args.no_ai else generate_ai_summary(payload)
    markdown = render_markdown(payload, ai_summary)
    output = Path(args.output) if args.output else config.output_dir / f"market-{as_of.isoformat()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    write_json_outputs(output, payload, ai_summary)
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


def sort_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=news_timestamp, reverse=True)


def news_timestamp(item: dict[str, Any]) -> datetime:
    value = str(item.get("date") or "")
    try:
        if "," in value:
            return parsedate_to_datetime(value).replace(tzinfo=None)
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.min


def market_driver_queries(as_of: date) -> list[str]:
    year = as_of.year
    return [
        f"NVIDIA 財報 AI 半導體 台股 {year}",
        f"Nvidia earnings AI demand S&P 500 Taiwan stocks {year}",
        f"美債殖利率 美元 台股 外資 {year}",
        f"台股 反彈 原因 半導體 AI {as_of.isoformat()}",
    ]


def intraday_sparkline(
    target: Any,
    finmind: FinMindClient,
    yahoo: YahooChartClient,
    twse_ohlc: TwseOhlcClient,
    as_of: date,
) -> dict[str, object]:
    errors: list[str] = []
    try:
        if target.id == "TAIEX":
            frame = aggregate_intraday(twse_ohlc.get_taiex_intraday()).tail(30)
            return intraday_payload(frame, "TWSE 30m")
        if target.id == "0050":
            frame = aggregate_intraday(twse_ohlc.get_tw50_intraday()).tail(30)
            if len(frame) >= 2:
                return intraday_payload(frame, "TWSE Taiwan50 30m proxy")
    except Exception as exc:
        errors.append(f"TWSE: {exc}")

    try:
        if target.id == "TAIEX":
            frame = aggregate_intraday(finmind.get_taiex_intraday(as_of)).tail(30)
            return intraday_payload(frame, "FinMind 30m")
        if target.group.startswith("taiwan"):
            frame = aggregate_intraday(finmind.get_taiwan_stock_intraday(target.id, as_of)).tail(30)
            return intraday_payload(frame, "FinMind 30m")
    except Exception as exc:
        errors.append(f"FinMind: {exc}")

    if not target.yahoo_symbol:
        return {"points": [], "source": None, "note": "30 分資料不足", "error": None}
    try:
        frame = yahoo.get_intraday_price(target.yahoo_symbol, days=5, interval="30m").tail(60)
        return intraday_payload(frame, "Yahoo 30m")
    except Exception as exc:
        errors.append(f"Yahoo: {exc}")

    return {"points": [], "source": None, "note": "30 分資料不足", "error": "；".join(errors)}


def intraday_payload(frame: Any, source: str) -> dict[str, object]:
    points = [
        {"datetime": row["datetime"].isoformat(), "close": float(row["close"])}
        for _, row in frame.iterrows()
    ]
    return {"points": points, "source": source, "note": "30 分線", "error": None}


def write_json_outputs(output: Path, payload: dict[str, Any], ai_summary: str | None) -> None:
    data = dict(payload)
    data["ai_summary"] = ai_summary
    data["ai_used"] = ai_summary is not None
    data["ai_prompt"] = build_ai_prompt(payload)
    data["generated_at"] = datetime.now().isoformat(timespec="seconds")
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    output.with_suffix(".json").write_text(json_text, encoding="utf-8")
    (output.parent / "latest.json").write_text(json_text, encoding="utf-8")


if __name__ == "__main__":
    main()
