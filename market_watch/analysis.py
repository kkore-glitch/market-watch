from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .config import Target
from .data_sources import FinMindClient


INSTITUTION_LABELS = {
    "Foreign_Investor": "外資",
    "Investment_Trust": "投信",
    "Dealer_self": "自營商",
    "Dealer_Hedging": "自營商避險",
    "Foreign_Dealer_Self": "外資自營商",
    "total": "合計",
}

MARGIN_LABELS = {
    "MarginPurchase": "融資",
    "ShortSale": "融券",
    "MarginPurchaseMoney": "融資金額",
}


def summarize_institutional(raw: pd.DataFrame, unit: str = "shares") -> dict[str, object]:
    if raw.empty:
        return {"available": False, "summary": "無三大法人資料"}
    frame = raw.copy()
    frame["buy"] = pd.to_numeric(frame["buy"], errors="coerce").fillna(0)
    frame["sell"] = pd.to_numeric(frame["sell"], errors="coerce").fillna(0)
    frame["net"] = frame["buy"] - frame["sell"]
    latest_date = frame["date"].max()
    latest = frame[frame["date"] == latest_date]
    by_name = latest.groupby("name", as_index=False)["net"].sum()
    total_rows = by_name[by_name["name"].astype(str).str.lower() == "total"]
    detail = by_name[by_name["name"].astype(str).str.lower() != "total"]
    total = float(total_rows["net"].sum()) if not total_rows.empty else float(detail["net"].sum())
    leader = detail.iloc[detail["net"].abs().argmax()] if not detail.empty else None
    direction = "買超" if total > 0 else "賣超" if total < 0 else "中性"
    pressure = "法人偏多" if total > 0 else "法人偏空" if total < 0 else "法人方向不明"
    if leader is not None:
        pressure += (
            f"，主要來自 {institution_name(str(leader['name']))}"
            f" {format_institution_net(float(leader['net']), unit)}"
        )
    detail = detail.copy()
    detail["display_name"] = detail["name"].map(lambda value: institution_name(str(value)))
    detail["net_display"] = detail["net"].map(lambda value: format_institution_net(float(value), unit))
    return {
        "available": True,
        "date": str(latest_date),
        "total_net": total,
        "total_display": format_institution_net(total, unit),
        "direction": direction,
        "pressure": pressure,
        "by_name": detail.to_dict(orient="records"),
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
        name = str(row.get("name"))
        change = float(row.get("TodayBalance", 0) - row.get("YesBalance", 0))
        rows.append(
            {
                "name": name,
                "display_name": MARGIN_LABELS.get(name, name),
                "balance_change": change,
                "balance_change_display": format_margin_change(name, change),
            }
        )
    summary = []
    for item in rows:
        name = item["display_name"]
        change = item["balance_change"]
        display = str(item["balance_change_display"]).lstrip("+-")
        if change > 0:
            summary.append(f"{name}增加 {display}")
        elif change < 0:
            summary.append(f"{name}減少 {display}")
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
            result["institutional"] = summarize_institutional(finmind.get_market_institutional(start, as_of), unit="amount")
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


def human_interpretation(target: Target, signal: dict[str, object], chip: dict[str, object]) -> dict[str, object]:
    score = technical_score(signal) + chip_score(chip)
    tone = classify_score(score)
    facts = build_fact_sentences(signal, chip)
    return {
        "tone": tone,
        "score": score,
        "summary": build_human_summary(target, signal, chip, tone, facts),
        "action": build_action_observation(signal, tone),
        "facts": facts,
    }


def technical_score(signal: dict[str, object]) -> int:
    score = 0
    close = float(signal["close"])
    for key in ["sma20", "sma60", "sma120"]:
        value = signal.get(key)
        if value is None:
            continue
        score += 1 if close >= float(value) else -1
    if "KD 黃金交叉" in signal.get("events", []):
        score += 1
    if "KD 死亡交叉" in signal.get("events", []):
        score -= 1
    if signal["k"] >= 80 and signal["d"] >= 80:
        score -= 1
    if signal["k"] <= 20 and signal["d"] <= 20:
        score += 1
    volume_ratio = signal.get("volume_ratio_20d")
    if volume_ratio and volume_ratio > 1.2:
        score += 1 if signal["change_pct"] > 0 else -1
    return score


def chip_score(chip: dict[str, object]) -> int:
    inst = chip.get("institutional")
    if not isinstance(inst, dict) or not inst.get("available"):
        return 0
    total = float(inst.get("total_net", 0))
    if total > 0:
        return 1
    if total < 0:
        return -1
    return 0


def classify_score(score: int) -> str:
    if score >= 3:
        return "偏多"
    if score <= -2:
        return "偏空"
    return "中性偏觀望"


def build_fact_sentences(signal: dict[str, object], chip: dict[str, object]) -> list[str]:
    facts: list[str] = []
    close = float(signal["close"])
    sma20 = signal.get("sma20")
    if sma20 is not None:
        distance = (close / float(sma20) - 1) * 100
        facts.append(f"收盤價距離月線 {distance:+.2f}%")
    volume_ratio = signal.get("volume_ratio_20d")
    if volume_ratio is not None:
        facts.append(f"量能約為 20 日均量 {float(volume_ratio):.2f} 倍")
    inst = chip.get("institutional")
    if isinstance(inst, dict) and inst.get("available"):
        facts.append(f"法人合計{inst.get('total_display')}")
    margin = chip.get("margin")
    if isinstance(margin, dict) and margin.get("available") and margin.get("summary"):
        facts.append(f"融資融券變化: {margin['summary']}")
    return facts


def build_human_summary(
    target: Target,
    signal: dict[str, object],
    chip: dict[str, object],
    tone: str,
    facts: list[str],
) -> str:
    inst = chip.get("institutional")
    inst_text = ""
    if isinstance(inst, dict) and inst.get("available"):
        inst_text = f"籌碼面呈現{inst.get('pressure')}。"
    elif target.group.startswith("taiwan"):
        inst_text = "籌碼資料不足，法人方向暫時不能當作判斷主軸。"
    else:
        inst_text = "此標的目前沒有法人買賣超資料，主要看價格與量能。"

    warnings = "；".join(signal.get("warnings", []))
    supports = "；".join(signal.get("supports", []))
    structure = warnings or supports or "技術面沒有特別突出的規則訊號"
    fact_text = "；".join(facts[:3])
    return f"{target.name}目前整體判讀為{tone}。{inst_text}技術面重點是: {structure}。{fact_text}。"


def build_action_observation(signal: dict[str, object], tone: str) -> str:
    close = float(signal["close"])
    sma20 = signal.get("sma20")
    above_month = sma20 is not None and close >= float(sma20)
    volume_ratio = signal.get("volume_ratio_20d")
    volume_text = "量能沒有明顯放大"
    if volume_ratio and volume_ratio >= 1.5:
        volume_text = "量能明顯放大"
    elif volume_ratio and volume_ratio <= 0.7:
        volume_text = "量能偏低"

    if tone == "偏多":
        if above_month:
            return f"偏多但不追價，可等回測月線不破或量縮整理後再分批評估；{volume_text}時更要避免一次加滿。"
        return "雖然整體偏多，但尚未站穩月線，先等收回月線再提高積極度。"
    if tone == "偏空":
        return "偏保守，短線不急著接刀；已有部位可把月線或季線作為風險線，等賣壓收斂或重新站回月線再評估。"
    if above_month:
        return f"中性偏觀望，價格仍在月線上方，可小部位追蹤，不適合因單日波動大幅加碼；{volume_text}。"
    return "中性偏觀望，先等站回月線或出現價穩量縮，再考慮分批；跌破關鍵均線時應降低期待。"


def institution_name(name: str) -> str:
    return INSTITUTION_LABELS.get(name, name)


def format_institution_net(value: float, unit: str) -> str:
    direction = "買超" if value > 0 else "賣超" if value < 0 else "持平"
    absolute = abs(value)
    if unit == "amount":
        return f"{direction}約 {absolute / 100_000_000:.1f} 億元"
    return f"{direction}約 {absolute / 1000:,.0f} 張"


def format_margin_change(name: str, value: float) -> str:
    if name == "MarginPurchaseMoney":
        return f"{value / 100_000_000:+.1f} 億元"
    return f"{value / 1000:+.1f} 千張"
