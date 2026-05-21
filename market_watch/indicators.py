from __future__ import annotations

import pandas as pd


def add_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy().sort_values("date").reset_index(drop=True)
    frame["sma20"] = frame["close"].rolling(20).mean()
    frame["sma60"] = frame["close"].rolling(60).mean()
    frame["sma120"] = frame["close"].rolling(120).mean()
    frame["vol20"] = frame["volume"].rolling(20).mean()

    low9 = frame["low"].rolling(9).min()
    high9 = frame["high"].rolling(9).max()
    rsv = (frame["close"] - low9) / (high9 - low9) * 100
    rsv = rsv.replace([float("inf"), float("-inf")], pd.NA).fillna(50)
    frame["k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    frame["d"] = frame["k"].ewm(alpha=1 / 3, adjust=False).mean()
    return frame


def latest_signal(frame: pd.DataFrame) -> dict[str, object]:
    if len(frame) < 2:
        raise ValueError("Need at least two rows to calculate signals")
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    close = float(latest["close"])
    prev_close = float(previous["close"])
    change = close - prev_close
    change_pct = change / prev_close * 100 if prev_close else 0

    events: list[str] = []
    warnings: list[str] = []
    supports: list[str] = []

    if previous["k"] <= previous["d"] and latest["k"] > latest["d"]:
        events.append("KD 黃金交叉")
    if previous["k"] >= previous["d"] and latest["k"] < latest["d"]:
        events.append("KD 死亡交叉")
    if latest["k"] >= 80 and latest["d"] >= 80:
        warnings.append("KD 高檔鈍化或過熱")
    if latest["k"] <= 20 and latest["d"] <= 20:
        supports.append("KD 低檔區，留意止跌或反彈訊號")

    for column, label in [("sma20", "月線"), ("sma60", "季線"), ("sma120", "半年線")]:
        value = latest[column]
        prev_value = previous[column]
        if pd.isna(value):
            continue
        distance = (close / float(value) - 1) * 100
        if previous["close"] >= prev_value and close < value:
            warnings.append(f"跌破{label}")
        elif previous["close"] <= prev_value and close > value:
            events.append(f"站回{label}")
        elif close >= value:
            supports.append(f"收在{label}之上 {distance:.2f}%")
        else:
            warnings.append(f"收在{label}之下 {distance:.2f}%")

    if pd.notna(latest["vol20"]) and latest["vol20"] > 0:
        volume_ratio = float(latest["volume"] / latest["vol20"])
        if volume_ratio >= 1.5:
            events.append(f"成交量放大至 20 日均量 {volume_ratio:.2f} 倍")
        elif volume_ratio <= 0.7:
            warnings.append(f"量能低於 20 日均量，量比 {volume_ratio:.2f}")
    else:
        volume_ratio = None

    return {
        "date": str(latest["date"]),
        "close": close,
        "change": change,
        "change_pct": change_pct,
        "volume": int(latest["volume"]) if pd.notna(latest["volume"]) else None,
        "volume_ratio_20d": volume_ratio,
        "k": float(latest["k"]),
        "d": float(latest["d"]),
        "sma20": none_or_float(latest["sma20"]),
        "sma60": none_or_float(latest["sma60"]),
        "sma120": none_or_float(latest["sma120"]),
        "events": events,
        "warnings": warnings,
        "supports": supports,
        "source": str(latest.get("source", "")),
        "sparkline": sparkline_points(frame),
    }


def none_or_float(value: object) -> float | None:
    return None if pd.isna(value) else float(value)


def sparkline_points(frame: pd.DataFrame, periods: int = 60) -> list[dict[str, object]]:
    recent = frame.tail(periods)
    return [
        {"date": str(row["date"]), "close": float(row["close"])}
        for _, row in recent.iterrows()
        if pd.notna(row["close"])
    ]
