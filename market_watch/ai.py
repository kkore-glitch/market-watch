from __future__ import annotations

import json
import os
from typing import Any


SYSTEM_PROMPT = """你是客觀的市場狀況分析助理。請只根據輸入資料判斷，不使用保證語氣。
請用繁體中文輸出，格式必須容易在手機閱讀：

一、台股大盤
- 現況：
- 交易壓力：
- 基礎買賣建議：
- 需要注意：

二、ETF 與 S&P 500
- 0050：
- 00878：
- 00719B：
- S&P 500：

三、新聞與波動因子
- 可能影響：
- 需要補充的資料：

每個段落之間留一個空行。請把事實與推論分開，買賣建議只能是基礎觀察建議，不要下保證式或個人化指令。
如果資料不足，請直接說資料不足與可能需要補充的資料。"""


def build_ai_prompt(payload: dict[str, Any]) -> str:
    return (
        "請根據以下 JSON 產生每日市場觀察報告。"
        "請把事實與推論分開，避免直接下買進或賣出指令。"
        "請務必使用清楚標題、條列與空行，不要輸出成一整段。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def generate_ai_summary(payload: dict[str, Any], model: str | None = None) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_ai_prompt(payload)},
        ],
    )
    return response.output_text
