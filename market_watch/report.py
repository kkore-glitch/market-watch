from __future__ import annotations

from datetime import datetime
from typing import Any

from .ai import build_ai_prompt


def render_markdown(payload: dict[str, Any], ai_summary: str | None) -> str:
    lines: list[str] = []
    lines.append(f"# 每日市場觀察 {payload['as_of']}")
    lines.append("")
    lines.append("本報告用於客觀確認市場現況，不構成投資建議。")
    lines.append("")

    if ai_summary:
        lines.append("## AI 綜合解讀")
        lines.append("")
        lines.append(ai_summary.strip())
        lines.append("")

    lines.append("## 一、台股大盤")
    append_group(lines, payload, {"TAIEX"})
    lines.append("")

    lines.append("## 二、S&P 500 與指定標的")
    append_group(lines, payload, {item["id"] for item in payload["targets"] if item["id"] != "TAIEX"})
    lines.append("")

    lines.append("## 三、新聞與波動因子")
    append_news(lines, payload.get("news", []))
    lines.append("")

    append_collection_errors(lines, payload.get("collection_errors", []))

    lines.append("## AI 協作提示詞")
    lines.append("")
    lines.append("沒有設定 `OPENAI_API_KEY` 時，可以把下面提示詞貼給 AI：")
    lines.append("")
    lines.append("```text")
    lines.append(build_ai_prompt(payload))
    lines.append("```")
    lines.append("")
    lines.append(f"產生時間: {datetime.now().isoformat(timespec='seconds')}")
    return "\n".join(lines)


def append_group(lines: list[str], payload: dict[str, Any], ids: set[str]) -> None:
    for item in payload["targets"]:
        if item["id"] not in ids:
            continue
        lines.append("")
        lines.append(f"### {item['name']} ({item['id']})")
        lines.append("")
        if item.get("error"):
            lines.append(f"- 資料狀態: {item['error']}")
            lines.append("- 觀察標準: 資料不足，今日暫不產生技術面判斷")
            lines.append("- 人話解讀: " + item.get("interpretation", {}).get("summary", "資料不足"))
            lines.append("- 基礎買賣建議: " + item.get("interpretation", {}).get("action", "資料不足"))
            continue
        signal = item["signal"]
        interpretation = item.get("interpretation", {})
        lines.append(
            f"- 現況: {signal['date']} 收 {signal['close']:,.2f}，"
            f"漲跌 {signal['change']:,.2f} ({signal['change_pct']:.2f}%)"
        )
        if signal.get("volume") is not None:
            ratio = signal.get("volume_ratio_20d")
            ratio_text = f"，20 日量比 {ratio:.2f}" if ratio is not None else ""
            lines.append(f"- 交易狀況: 成交量 {signal['volume']:,}{ratio_text}")
        lines.append(f"- KD: K {signal['k']:.2f} / D {signal['d']:.2f}")
        lines.append(
            "- 均線: "
            + format_line("月線", signal.get("sma20"))
            + "；"
            + format_line("季線", signal.get("sma60"))
            + "；"
            + format_line("半年線", signal.get("sma120"))
        )
        lines.append("- 觀察標準: " + join_or_none(signal["events"] + signal["warnings"] + signal["supports"]))
        lines.append("- 籌碼狀態: " + "；".join(item.get("pressure_reading", [])))
        lines.append("- 人話解讀: " + str(interpretation.get("summary", "資料不足")))
        lines.append("- 基礎買賣建議: " + str(interpretation.get("action", "資料不足")))
        lines.append(f"- 行情來源: {signal.get('source')}")


def append_news(lines: list[str], news: list[dict[str, Any]]) -> None:
    if not news:
        lines.append("")
        lines.append("目前未取得新聞資料。建議補充 FinMind 台股新聞、央行/美債/匯率與主要財經媒體摘要。")
        return
    for item in news[:12]:
        lines.append("")
        lines.append(f"- {item.get('date')} [{item.get('source')}] {item.get('title')}")
        if item.get("link"):
            lines.append(f"  {item['link']}")


def append_collection_errors(lines: list[str], errors: list[str]) -> None:
    if not errors:
        return
    lines.append("")
    lines.append("## 四、資料取得注意事項")
    for error in errors:
        lines.append("")
        lines.append(f"- {error}")


def format_line(name: str, value: float | None) -> str:
    return f"{name} {value:,.2f}" if value is not None else f"{name} 資料不足"


def join_or_none(items: list[str]) -> str:
    return "；".join(items) if items else "目前無明確規則訊號"
