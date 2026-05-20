from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .config import Target
from .data_sources import FinMindClient


def summarize_institutional(raw: pd.DataFrame) -> dict[str, object]:
    if raw.empty:
        return {"available": False, "summary": "無三大法人資料"}
    frame = raw.copy()
    frame["buy"] = pd.to_numeric(frame["buy"], errors="coerce").fillna(0)
    frame["sell"] = pd.to_numeric(frame["sell"], errors="coerce").fillna(0)
    frame["net"] = frame["buy"] - frame["sell"]
    latest_date = frame["date"].max()
    latest = frame[frame["date"] == latest_date]
    by_name = latest.groupby("name", as_index=False)["net"].sum()
    total = float(by_name["net"].sum())
    leader = by_name.iloc[by_name["net"].abs().argmax()] if not by_name.empty else None
    direction = "買超" if total > 0 else "賣超" if total < 0 else "中性"
    pressure = "法人偏多" if total > 0 else "法人偏空" if total < 0 else "法人方向不明"
    if leader is not None:
        pressure += f"，主要來自 {leader['name']} {float(leader['net']):,.0f}"
    return {
        "available": True,
        "date": str(latest_date),
        "total_net": total,
        "direction": direction,
        "pressure": pressure,
        "by_name": by_name.to_dict(orient="records"),
    }


def summarize_market_margin(raw: pd.DataFrame) -> dict[str, object]:
    if raw.empty:
        return {"available": False, "summary": "無整體融資融券資料"}
    frame = raw.copy()
    for column in ["TodayBalance", "YesBalance", "buy", "sell"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    latest_date = frame["date"].max()
    latest = frame[frame["date"] == latest_date]
    rows = []
    for _, row in latest.iterrows():
        change = float(row.get("TodayBalance", 0) - row.get("YesBalance", 0))
        rows.append({"name": row.get("name"), "balance_change": change})
    summary = []
    for item in rows:
        name = item["name"]
        change = item["balance_change"]
        if change > 0:
            summary.append(f"{name}餘額增加 {change:,.0f}")
        elif change < 0:
            summary.append(f"{name}餘額減少 {abs(change):,.0f}")
    return {"available": True, "date": str(latest_date), "rows": rows, "summary": "；".join(summary)}


def collect_chip_data(target: Target, finmind: FinMindClient, as_of: date) -> dict[str, object]:
    start = as_of - timedelta(days=14)
    result: dict[str, object] = {}
    if target.group.startswith("taiwan") and target.id != "TAIEX":
        try:
            result["institutional"] = summarize_institutional(finmind.get_institutional(target.id, start, as_of))
        except Exception as exc:
            result["institutional"] = {"available": False, "summary": f"三大法人資料取得失敗: {exc}"}
    if target.id == "TAIEX":
        try:
            result["institutional"] = summarize_institutional(finmind.get_market_institutional(start, as_of))
        except Exception as exc:
            result["institutional"] = {"available": False, "summary": f"整體法人資料取得失敗: {exc}"}
        try:
            result["margin"] = summarize_market_margin(finmind.get_market_margin(start, as_of))
        except Exception as exc:
            result["margin"] = {"available": False, "summary": f"整體融資融券資料取得失敗: {exc}"}
    return result


def pressure_reading(signal: dict[str, object], chip: dict[str, object]) -> list[str]:
    readings: list[str] = []
    if signal["change_pct"] > 0 and signal.get("volume_ratio_20d") and signal["volume_ratio_20d"] > 1.2:
        readings.append("價漲量增，短線買盤承接較積極")
    if signal["change_pct"] < 0 and signal.get("volume_ratio_20d") and signal["volume_ratio_20d"] > 1.2:
        readings.append("價跌量增，短線賣壓較明顯")
    inst = chip.get("institutional")
    if isinstance(inst, dict) and inst.get("available"):
        readings.append(str(inst.get("pressure")))
    margin = chip.get("margin")
    if isinstance(margin, dict) and margin.get("available") and margin.get("summary"):
        readings.append(f"散戶槓桿線索: {margin['summary']}")
    if not readings:
        readings.append("目前資料不足以判斷明確買賣壓來源")
    return readings
