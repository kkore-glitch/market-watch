from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from io import StringIO
from typing import Any

import pandas as pd
import requests

from .config import Target


class DataSourceError(RuntimeError):
    pass


class FinMindClient:
    base_url = "https://api.finmindtrade.com/api/v4/data"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("FINMIND_TOKEN")

    def get_dataset(
        self,
        dataset: str,
        start_date: date,
        end_date: date | None,
        data_id: str | None = None,
    ) -> pd.DataFrame:
        params: dict[str, Any] = {
            "dataset": dataset,
            "start_date": start_date.isoformat(),
        }
        if end_date:
            params["end_date"] = end_date.isoformat()
        if data_id:
            params["data_id"] = data_id

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in (200, "200"):
            raise DataSourceError(f"FinMind {dataset} failed: {payload.get('msg')}")
        return pd.DataFrame(payload.get("data", []))

    def get_price(self, target: Target, start_date: date, end_date: date) -> pd.DataFrame:
        dataset = target.finmind_dataset or "TaiwanStockPrice"
        raw = self.get_dataset(dataset, start_date, end_date, data_id=target.id)
        if raw.empty:
            raise DataSourceError(f"No FinMind price data for {target.id}")
        return normalize_price_frame(raw, source=f"FinMind:{dataset}")

    def get_institutional(self, stock_id: str, start_date: date, end_date: date) -> pd.DataFrame:
        return self.get_dataset(
            "TaiwanStockInstitutionalInvestorsBuySell",
            start_date,
            end_date,
            data_id=stock_id,
        )

    def get_market_institutional(self, start_date: date, end_date: date) -> pd.DataFrame:
        return self.get_dataset("TaiwanStockTotalInstitutionalInvestors", start_date, end_date)

    def get_market_margin(self, start_date: date, end_date: date) -> pd.DataFrame:
        return self.get_dataset("TaiwanStockTotalMarginPurchaseShortSale", start_date, end_date)

    def get_news(self, stock_id: str, day: date) -> pd.DataFrame:
        return self.get_dataset("TaiwanStockNews", day, day, data_id=stock_id)

    def get_taiwan_stock_intraday(self, stock_id: str, day: date) -> pd.DataFrame:
        raw = self.get_dataset("TaiwanStockPriceTick", day, None, data_id=stock_id)
        if raw.empty:
            raise DataSourceError(f"No FinMind intraday tick data for {stock_id}")
        return normalize_intraday_frame(raw, value_column="deal_price", source="FinMind:TaiwanStockPriceTick")

    def get_taiex_intraday(self, day: date) -> pd.DataFrame:
        raw = self.get_dataset("TaiwanVariousIndicators5Seconds", day, None)
        if raw.empty:
            raise DataSourceError("No FinMind intraday index data for TAIEX")
        return normalize_intraday_frame(raw, value_column="TAIEX", source="FinMind:TaiwanVariousIndicators5Seconds")


class YahooChartClient:
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def get_price(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        period1 = int(datetime.combine(start_date, datetime.min.time()).timestamp())
        period2 = int(datetime.combine(end_date, datetime.max.time()).timestamp())
        params = {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
        }
        response = requests.get(self.base_url.format(symbol=symbol), params=params, timeout=30)
        response.raise_for_status()
        result = response.json()["chart"]["result"]
        if not result:
            raise DataSourceError(f"No Yahoo chart data for {symbol}")

        item = result[0]
        timestamps = item.get("timestamp") or []
        quote = item["indicators"]["quote"][0]
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(timestamps, unit="s").date,
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "close": quote.get("close"),
                "volume": quote.get("volume"),
            }
        ).dropna(subset=["close"])
        frame["source"] = "Yahoo Finance chart endpoint"
        return frame

    def get_intraday_price(self, symbol: str, days: int = 5, interval: str = "30m") -> pd.DataFrame:
        params = {
            "range": f"{days}d",
            "interval": interval,
            "events": "history",
        }
        response = requests.get(self.base_url.format(symbol=symbol), params=params, timeout=30)
        response.raise_for_status()
        result = response.json()["chart"]["result"]
        if not result:
            raise DataSourceError(f"No Yahoo intraday chart data for {symbol}")

        item = result[0]
        timestamps = item.get("timestamp") or []
        quote = item["indicators"]["quote"][0]
        frame = pd.DataFrame(
            {
                "datetime": pd.to_datetime(timestamps, unit="s"),
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "close": quote.get("close"),
                "volume": quote.get("volume"),
            }
        ).dropna(subset=["close"])
        frame["source"] = f"Yahoo Finance chart endpoint {interval}"
        return frame.sort_values("datetime").reset_index(drop=True)


class StooqClient:
    base_url = "https://stooq.com/q/d/l/"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("STOOQ_API_KEY")

    def get_price(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        if not self.api_key:
            raise DataSourceError("Stooq API key is not configured")
        params = {
            "s": symbol,
            "d1": start_date.strftime("%Y%m%d"),
            "d2": end_date.strftime("%Y%m%d"),
            "i": "d",
            "apikey": self.api_key,
        }
        response = requests.get(self.base_url, params=params, timeout=30)
        response.raise_for_status()
        raw = pd.read_csv(StringIO(response.text))
        if raw.empty or "Date" not in raw.columns:
            raise DataSourceError(f"No Stooq daily data for {symbol}")
        return normalize_price_frame(raw, source="Stooq daily CSV")


class GoogleNewsClient:
    base_url = "https://news.google.com/rss/search"

    def search(self, query: str, limit: int = 8) -> list[dict[str, object]]:
        params = {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
        response = requests.get(self.base_url, params=params, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items: list[dict[str, object]] = []
        for item in root.findall("./channel/item")[:limit]:
            source = item.find("source")
            items.append(
                {
                    "date": item.findtext("pubDate"),
                    "source": source.text if source is not None else "Google News",
                    "title": item.findtext("title"),
                    "link": item.findtext("link"),
                    "topic": query,
                }
            )
        return items


class TwseOhlcClient:
    base_url = "https://mis.twse.com.tw/stock/data/{name}.txt"

    def get_taiex_intraday(self) -> pd.DataFrame:
        return self.get_ohlc_file("mis_ohlc_TSE", "TWSE MIS:TSE intraday OHLC")

    def get_tw50_intraday(self) -> pd.DataFrame:
        return self.get_ohlc_file("mis_ohlc_TW50", "TWSE MIS:TW50 intraday OHLC")

    def get_ohlc_file(self, name: str, source: str) -> pd.DataFrame:
        response = requests.get(self.base_url.format(name=name), timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("rtcode") != "0000" or not payload.get("ohlcArray"):
            raise DataSourceError(f"No TWSE OHLC data for {name}")
        return normalize_twse_ohlc(payload, source)


def normalize_price_frame(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    frame = raw.copy()
    rename = {
        "Date": "date",
        "max": "high",
        "min": "low",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Trading_Volume": "volume",
    }
    frame = frame.rename(columns=rename)
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise DataSourceError(f"Price data missing columns: {missing}")
    frame = frame[required].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    frame["source"] = source
    return frame


def normalize_intraday_frame(raw: pd.DataFrame, value_column: str, source: str) -> pd.DataFrame:
    if "date" not in raw.columns:
        raise DataSourceError("Intraday data missing date column")
    if value_column not in raw.columns:
        raise DataSourceError(f"Intraday data missing {value_column} column")

    frame = raw.copy()
    frame["datetime"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame[value_column], errors="coerce")
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
    else:
        frame["volume"] = 0
    frame = frame.dropna(subset=["datetime", "close"]).sort_values("datetime")
    frame = frame[["datetime", "close", "volume"]].reset_index(drop=True)
    frame["source"] = source
    return frame


def normalize_twse_ohlc(payload: dict[str, Any], source: str) -> pd.DataFrame:
    rows = payload.get("ohlcArray") or []
    date_text = ""
    info = payload.get("infoArray") or []
    if info and isinstance(info[0], dict):
        date_text = str(info[0].get("d") or "")
    if len(date_text) != 8:
        date_text = str(payload.get("lastDatetime") or "")[:8]
    if len(date_text) != 8:
        raise DataSourceError("TWSE OHLC payload missing trade date")

    trade_day = datetime.strptime(date_text, "%Y%m%d").date()
    frequency = int(payload.get("frequency") or 1)
    points: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        close = pd.to_numeric(row.get("c"), errors="coerce")
        if pd.isna(close):
            continue
        ts = str(row.get("ts") or "")
        if len(ts) >= 4:
            hour = int(ts[0:2])
            minute = int(ts[2:4])
            second = int(ts[4:6]) if len(ts) >= 6 else 0
        else:
            minutes = (index + 1) * frequency
            hour = 9 + minutes // 60
            minute = minutes % 60
            second = 0
        volume = pd.to_numeric(row.get("s"), errors="coerce")
        if pd.isna(volume):
            volume = 0
        points.append(
            {
                "datetime": datetime.combine(trade_day, datetime.min.time()).replace(
                    hour=hour,
                    minute=minute,
                    second=second,
                ),
                "close": float(close),
                "volume": float(volume),
                "source": source,
            }
        )
    if not points:
        raise DataSourceError("TWSE OHLC payload has no usable close prices")
    return pd.DataFrame(points).sort_values("datetime").reset_index(drop=True)


def aggregate_intraday(frame: pd.DataFrame, interval: str = "30min") -> pd.DataFrame:
    if frame.empty:
        return frame
    grouped = (
        frame.set_index("datetime")
        .resample(interval, origin="start_day", offset="9h")
        .agg({"close": "last", "volume": "sum"})
        .dropna(subset=["close"])
        .reset_index()
    )
    grouped["source"] = str(frame["source"].iloc[-1]) if "source" in frame.columns and not frame.empty else "Intraday"
    return grouped


def fetch_price(
    target: Target,
    start_date: date,
    end_date: date,
    finmind: FinMindClient,
    yahoo: YahooChartClient,
    stooq: StooqClient | None = None,
) -> pd.DataFrame:
    errors: list[str] = []
    sources = [target.preferred_source, "yahoo" if target.preferred_source != "yahoo" else "finmind"]
    if target.stooq_symbol and "stooq" not in sources:
        sources.append("stooq")
    for source in sources:
        try:
            if source == "finmind":
                return finmind.get_price(target, start_date, end_date)
            if source == "yahoo" and target.yahoo_symbol:
                return yahoo.get_price(target.yahoo_symbol, start_date, end_date)
            if source == "stooq" and target.stooq_symbol:
                return (stooq or StooqClient()).get_price(target.stooq_symbol, start_date, end_date)
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    raise DataSourceError(f"Unable to fetch {target.id}: {'; '.join(errors)}")
