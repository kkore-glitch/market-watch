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
- Google News RSS: 補抓市場驅動新聞，例如 NVIDIA 財報、AI 半導體、美股指數、美債殖利率、美元與台股反彈原因。
- Yahoo Finance chart endpoint: 作為非官方備援來源，用於 `^TWII`、`^GSPC` 與台股 ETF 的行情補抓。
- Stooq daily CSV: 選用備援來源；若要使用需在 `.env` 設定 `STOOQ_API_KEY`。

建議申請 FinMind token 並放在 `.env`：

```powershell
FINMIND_TOKEN=你的_token
OPENAI_API_KEY=你的_api_key
STOOQ_API_KEY=你的_stooq_key
```

`OPENAI_API_KEY` 與 `STOOQ_API_KEY` 是選用的；沒有設定時，工具仍會輸出規則式分析與一段可貼給 AI 的分析提示詞。

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

macOS / zsh：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
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

macOS / zsh 可直接用 venv 裡的 Python：

```bash
.venv/bin/python -m market_watch.cli run --no-ai
```

若有設定 `OPENAI_API_KEY`，拿掉 `--no-ai` 即可輸出 AI 綜合解讀。

### AI token 使用規則

- 打開 PWA 看報告、切換頁籤、重新整理頁面：不會使用 AI token。
- 按 PWA 上方的 `GPT` 按鈕：只會複製提示詞，不會使用 API token；你可以貼到 ChatGPT Plus 裡分析。
- 按 PWA 上方的 `AI` 按鈕：會透過後端呼叫 OpenAI API，按一次會重跑一次 AI 分析並消耗一次 API token。
- 執行 `python -m market_watch.cli run --no-ai`：不會使用 AI token，只會產生規則式分析。
- 執行 `python -m market_watch.cli run` 且 `.env` 有 `OPENAI_API_KEY`：會呼叫 OpenAI API，每產生一次報告會消耗一次 token。
- GitHub Actions 若 `MARKET_WATCH_USE_AI` 設為 `true`，每天排程產生報告時會消耗 AI token；未設定或不是 `true` 時會用 `--no-ai`，不消耗 AI token。
- PWA 的 `GPT` 按鈕是給 ChatGPT Plus 手動使用的低成本流程；ChatGPT Plus 不能當作 `OPENAI_API_KEY` 使用。
- 若未來要把 PWA 做成「按一下就自動呼叫 API 更新 AI 解讀」，必須使用 `market_watch.server` 或其他後端服務；按一次會呼叫後端重跑報告並消耗一次 API token。
- 若 PWA 部署在 GitHub Pages 這種純靜態網站，`AI` 按鈕不能安全地直接呼叫 OpenAI；要即時分析必須另外部署後端服務。
- 不能把 `OPENAI_API_KEY` 放進前端 JavaScript，否則任何打開網頁的人都可能看到或盜用 key。

### 模型選擇

在 `.env` 裡調整 `OPENAI_MODEL`：

```text
OPENAI_MODEL=gpt-5.2-chat-latest
```

建議：

- `gpt-5.2-chat-latest`: 較適合自然、像 ChatGPT 的市場解讀。
- `gpt-5.2`: 較適合更深入、較謹慎的推理分析，成本通常較高。
- `gpt-4.1-mini`: 較省錢，適合每天自動跑基礎摘要。

若模型因 API 等級或帳號限制不能使用，請先改回 `gpt-4.1-mini`。

## 手機 PWA

先產生最新報告：

```bash
.venv/bin/python -m market_watch.cli run --no-ai
```

再從專案根目錄啟動靜態伺服器：

```bash
python3 -m http.server 8000
```

在手機瀏覽器打開：

```text
http://你的電腦區網IP:8000/pwa/
```

iPhone Safari 可用分享選單加入主畫面。PWA 只讀取 `reports/latest.json`，不會在手機端抓行情，也不會把 API token 放進瀏覽器。

若你不想另外付 API 費，使用 PWA 上方的 `GPT` 按鈕即可。它會複製完整提示詞，你再貼到 ChatGPT Plus 裡分析。

若要使用 PWA 上方的 `AI` 按鈕，請用內建後端伺服器，不要用 `python3 -m http.server`：

```bash
.venv/bin/python -m market_watch.server
```

API 模式必須在 `.env` 裡設定 `OPENAI_API_KEY`，每次按 `AI` 讓後端產生 AI 解讀都會消耗一次 OpenAI API token。這不是 ChatGPT Plus 額度。不要把 key 寫進前端、README 或 GitHub。

## 判斷原則

工具會把「事實」與「解讀」分開：

- 事實：價格、漲跌、成交量、均線位置、KD 數值、三大法人買賣超、融資融券變化、新聞標題與來源。
- 規則式觀察：跌破月線、跌破半年線、KD 交叉、成交量高於 20 日均量、外資/投信/自營商買賣超方向。
- AI 解讀：把上述事實整合成客觀敘述，要求 AI 明確標示不確定性，避免直接給買賣指令。

## 每日使用注意事項

- 建議在台股收盤後、資料源更新完成後再跑；若最新交易日尚未更新，報告會以資料源回傳的最新日期為準。
- Yahoo Finance 是非官方來源，可能出現 429 或短暫失敗；工具會改用其他設定好的來源，或在報告中標示資料取得失敗。
- 若單一標的資料失敗，報告仍會產生，並在該標的與「資料取得注意事項」中列出原因。
- `--no-ai` 不會使用 OpenAI token；拿掉 `--no-ai` 才會呼叫 OpenAI API 並消耗 token。
- PWA 檢視既有報告不會使用 OpenAI token，也不會使用 FinMind token。
- 「基礎買賣建議」是規則式觀察，依照均線、KD、量能與籌碼資料產生，不知道你的成本、部位與風險承受度。
- AI 解讀只根據報告 payload 生成，仍需自行檢查資料日期、來源與是否有重大盤後事件。

## 後續可擴充

- 每天收盤後自動排程產生報告
- 加入圖表與網頁儀表板
- 加入台指期、選擇權 Put/Call、匯率、10 年期美債殖利率、VIX
- 加入歷史回測，檢查每個觀察標準過去的有效性
