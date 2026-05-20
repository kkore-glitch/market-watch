# 台股與美股市場觀察工具

這是一個每日市場狀況檢查工具，用來客觀整理台股大盤、0050、00878、00719B、S&P 500 的技術面、籌碼面與新聞摘要。它不是投資建議工具，而是把資料、判斷規則與 AI 解讀分開呈現，幫助你確認「現在市場正在發生什麼」。

## 功能

- 台股大盤、台股 ETF、S&P 500 每日行情摘要
- K 線資料、KD 指標、月線 20 日、季線 60 日、半年線 120 日
- KD 黃金交叉/死亡交叉、跌破或站回均線、量能異常、乖離風險
- 台股三大法人、整體市場融資融券作為買賣壓來源線索
- 新聞摘要與可能利多/利空影響
- 可選擇呼叫 AI 產出更自然的客觀解讀

## 資料來源

- FinMind API: 台股日行情、三大法人、融資融券、台股新聞、美股日行情。FinMind 文件指出其提供台股技術面、籌碼面、新聞與國際市場資料，資料每日更新，API base URL 為 `https://api.finmindtrade.com/api/v4`。
- Yahoo Finance chart endpoint: 作為非官方備援來源，用於 `^TWII`、`^GSPC` 與台股 ETF 的行情補抓。

建議申請 FinMind token 並放在 `.env`：

```powershell
FINMIND_TOKEN=你的_token
OPENAI_API_KEY=你的_api_key
```

`OPENAI_API_KEY` 是選用的；沒有設定時，工具仍會輸出規則式分析與一段可貼給 AI 的分析提示詞。

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 使用

產生今日報告：

```powershell
python -m market_watch.cli run
```

指定日期與輸出檔：

```powershell
python -m market_watch.cli run --as-of 2026-05-20 --output reports/market-2026-05-20.md
```

不呼叫 AI，只產生資料與規則式解讀：

```powershell
python -m market_watch.cli run --no-ai
```

## 判斷原則

工具會把「事實」與「解讀」分開：

- 事實：價格、漲跌、成交量、均線位置、KD 數值、三大法人買賣超、融資融券變化、新聞標題與來源。
- 規則式觀察：跌破月線、跌破半年線、KD 交叉、成交量高於 20 日均量、外資/投信/自營商買賣超方向。
- AI 解讀：把上述事實整合成客觀敘述，要求 AI 明確標示不確定性，避免直接給買賣指令。

## 後續可擴充

- 每天收盤後自動排程產生報告
- 加入圖表與網頁儀表板
- 加入台指期、選擇權 Put/Call、匯率、10 年期美債殖利率、VIX
- 加入歷史回測，檢查每個觀察標準過去的有效性
