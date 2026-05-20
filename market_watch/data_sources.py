from __future__ import annotations

import os
from datetime import date, datetime
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
        end_date: date,
        data_id: str | None = None,
    ) -> pd.DataFrame:
        params: dict[str, Any] = {
            "dataset": dataset,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
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


def normalize_price_frame(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    frame = raw.copy()
    rename = {
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


def fetch_price(target: Target, start_date: date, end_date: date, finmind: FinMindClient, yahoo: YahooChartClient) -> pd.DataFrame:
    errors: list[str] = []
    sources = [target.preferred_source, "yahoo" if target.preferred_source != "yahoo" else "finmind"]
    for source in sources:
        try:
            if source == "finmind":
                return finmind.get_price(target, start_date, end_date)
            if source == "yahoo" and target.yahoo_symbol:
                return yahoo.get_price(target.yahoo_symbol, start_date, end_date)
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    raise DataSourceError(f"Unable to fetch {target.id}: {'; '.join(errors)}")
