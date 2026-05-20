from __future__ import annotations

import json
import os
from typing import Any


SYSTEM_PROMPT = """你是客觀的市場狀況分析助理。請只根據輸入資料判斷，不給個人化投資建議，不使用保證語氣。
請分成三段：台股大盤、其他標的與 S&P 500、新聞與波動因子。
每段都要清楚標示：現況、交易壓力、觀察標準、需要注意的解讀。
如果資料不足，請直接說資料不足與可能需要補充的資料。"""


def build_ai_prompt(payload: dict[str, Any]) -> str:
    return (
        "請根據以下 JSON 產生每日市場觀察報告。"
        "請把事實與推論分開，避免直接下買進或賣出指令。\n\n"
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
