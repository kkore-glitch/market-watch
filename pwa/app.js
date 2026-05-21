const state = {
  report: null,
};

const summaryStrip = document.querySelector("#summaryStrip");
const targetsView = document.querySelector("#targetsView");
const newsView = document.querySelector("#newsView");
const notesView = document.querySelector("#notesView");
const refreshButton = document.querySelector("#refreshButton");
const apiAiButton = document.querySelector("#apiAiButton");
const gptButton = document.querySelector("#gptButton");

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

refreshButton.addEventListener("click", () => loadReport(true));
apiAiButton.addEventListener("click", () => runApiAiAnalysis());
gptButton.addEventListener("click", () => copyChatGptPrompt());

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

loadReport();

async function loadReport(force = false) {
  setLoading();
  try {
    const cacheBust = force ? `?t=${Date.now()}` : "";
    const response = await fetch(`../reports/latest.json${cacheBust}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.report = await response.json();
    render();
  } catch (error) {
    renderError(error);
  }
}

async function copyChatGptPrompt() {
  if (!state.report) {
    window.alert("報告尚未載入，請稍後再試。");
    return;
  }
  const originalText = gptButton.textContent;
  gptButton.disabled = true;
  gptButton.textContent = "OK";
  try {
    const prompt = state.report.ai_prompt || buildFallbackPrompt(state.report);
    await navigator.clipboard.writeText(prompt);
    window.alert("已複製 ChatGPT 分析提示詞。你可以貼到 ChatGPT Plus 裡請它分析。");
  } catch (error) {
    window.alert(`複製失敗：${error.message}`);
  } finally {
    gptButton.textContent = originalText;
    gptButton.disabled = false;
  }
}

async function runApiAiAnalysis() {
  const ok = window.confirm("要用 AI 重新產生今日分析嗎？");
  if (!ok) return;

  const originalText = apiAiButton.textContent;
  apiAiButton.disabled = true;
  gptButton.disabled = true;
  refreshButton.disabled = true;
  apiAiButton.textContent = "...";
  try {
    const response = await fetch("../api/generate?ai=true", { method: "POST" });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    await loadReport(true);
    switchView("notes");
    window.alert("AI 分析已更新。");
  } catch (error) {
    window.alert(`AI 分析未執行：${error.message}\n\n如果你正在用 python3 -m http.server 或 GitHub Pages，這個按鈕不會生效。請改用 .venv/bin/python -m market_watch.server，並在 .env 設定 OPENAI_API_KEY。`);
  } finally {
    apiAiButton.textContent = originalText;
    apiAiButton.disabled = false;
    gptButton.disabled = false;
    refreshButton.disabled = false;
  }
}

function setLoading() {
  summaryStrip.innerHTML = metric("狀態", "載入中") + metric("資料日", "-") + metric("標的", "-");
}

function render() {
  const report = state.report;
  const targets = report.targets || [];
  const failed = targets.filter((item) => item.error).length;
  summaryStrip.innerHTML = [
    metric("資料日", report.as_of || "-"),
    metric("AI 狀態", report.ai_used ? "已分析" : "規則版"),
    metric("資料狀態", failed ? `${targets.length - failed}/${targets.length} 成功` : `${targets.length} 正常`),
  ].join("");

  targetsView.innerHTML = targets.map(renderTarget).join("") || empty("尚無標的資料");
  newsView.innerHTML = renderNews(report.news || []);
  notesView.innerHTML = renderNotes(report);
}

function renderTarget(item) {
  if (item.error) {
    const interpretation = item.interpretation || {};
    return `
      <article class="target-card">
        <div class="target-head">
          <div class="target-title">
            <h2>${escapeHtml(item.name)} (${escapeHtml(item.id)})</h2>
            <p>${escapeHtml(item.group)}</p>
          </div>
        </div>
        <div class="target-body">
          <div class="chips"><span class="chip error">${escapeHtml(item.error)}</span></div>
          <p class="reading">${escapeHtml(interpretation.summary || "資料不足")}</p>
          <p class="reading">${escapeHtml(interpretation.action || "資料不足")}</p>
        </div>
      </article>
    `;
  }

  const signal = item.signal;
  const interpretation = item.interpretation || {};
  const changeClass = signal.change > 0 ? "up" : signal.change < 0 ? "down" : "";
  const toneClass = toneToClass(interpretation.tone);
  const observations = [
    ...(signal.events || []).map((text) => chip(text)),
    ...(signal.warnings || []).map((text) => chip(text, "warning")),
    ...(signal.supports || []).map((text) => chip(text)),
  ].join("") || chip("目前無明確規則訊號");

  return `
    <article class="target-card">
      <div class="target-head">
        <div class="target-title">
          <h2>${escapeHtml(item.name)} (${escapeHtml(item.id)})</h2>
          <p>${escapeHtml(signal.date || "")}</p>
          <span class="tone-pill ${toneClass}">${escapeHtml(interpretation.tone || "觀望")}</span>
        </div>
        ${renderSparkline(signal.intraday_sparkline || [], signal.intraday_note || "30 分資料不足", changeClass)}
        <div class="price">
          <strong>${formatNumber(signal.close)}</strong>
          <span class="change ${changeClass}">${formatSigned(signal.change)} (${formatSigned(signal.change_pct)}%)</span>
        </div>
      </div>
      <div class="target-body">
        <div class="kv-grid">
          ${kv("KD", `K ${formatNumber(signal.k)} / D ${formatNumber(signal.d)}`)}
          ${kv("20 日量比", signal.volume_ratio_20d == null ? "資料不足" : formatNumber(signal.volume_ratio_20d))}
          ${kv("月線", formatNullable(signal.sma20))}
          ${kv("季線 / 半年線", `${formatNullable(signal.sma60)} / ${formatNullable(signal.sma120)}`)}
        </div>
        <div>
          <p class="section-label">觀察標準</p>
          <div class="chips">${observations}</div>
        </div>
        <div>
          <p class="section-label">籌碼狀態</p>
          <p class="reading">${escapeHtml((item.pressure_reading || []).join("；"))}</p>
        </div>
        <div>
          <p class="section-label">人話解讀</p>
          <p class="reading">${escapeHtml(interpretation.summary || "資料不足")}</p>
        </div>
        <div>
          <p class="section-label">基礎買賣建議</p>
          <p class="reading">${escapeHtml(interpretation.action || "資料不足")}</p>
        </div>
        <p class="source">行情來源: ${escapeHtml(signal.source || "-")}</p>
      </div>
    </article>
  `;
}

function renderNews(items) {
  if (!items.length) {
    return empty("目前未取得新聞資料");
  }
  return items.slice(0, 20).map((item) => {
    const body = `
      <time>${escapeHtml(item.date || "")} ${escapeHtml(item.source || "")}</time>
      <strong>${escapeHtml(item.title || "")}</strong>
    `;
    if (item.link) {
      return `<a class="news-item" href="${escapeAttribute(item.link)}" target="_blank" rel="noreferrer">${body}</a>`;
    }
    return `<article class="news-item">${body}</article>`;
  }).join("");
}

function renderNotes(report) {
  const aiText = report.ai_summary ? report.ai_summary : "尚未產生 AI 解讀。目前顯示的是各標的卡片中的規則式解讀。";
  return notice("AI 解讀", aiText, "ai-summary");
}

function buildFallbackPrompt(report) {
  return `請根據以下 JSON 產生每日市場觀察報告。請把事實與推論分開，避免直接下買進或賣出指令。\n\n${JSON.stringify(report, null, 2)}`;
}

function renderError(error) {
  summaryStrip.innerHTML = metric("狀態", "讀取失敗") + metric("資料日", "-") + metric("標的", "-");
  targetsView.innerHTML = notice("讀取失敗", `找不到 reports/latest.json 或伺服器尚未啟動。${error.message}`);
  newsView.innerHTML = empty("尚無新聞資料");
  notesView.innerHTML = notice("處理方式", "請先在專案根目錄執行報告產生命令，再重新整理 PWA。");
}

function switchView(view) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `${view}View`);
  });
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function kv(label, value) {
  return `<div class="kv"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function chip(text, type = "") {
  return `<span class="chip ${type}">${escapeHtml(text)}</span>`;
}

function renderSparkline(points, note, changeClass) {
  if (!points.length) {
    return `
      <div class="sparkline-wrap empty-line">
        <span>30分</span>
        <div class="sparkline-missing">${escapeHtml(note || "資料不足")}</div>
      </div>
    `;
  }
  const values = points.map((item) => Number(item.close)).filter((value) => !Number.isNaN(value));
  if (values.length < 2) {
    return `
      <div class="sparkline-wrap empty-line">
        <span>30分</span>
        <div class="sparkline-missing">資料不足</div>
      </div>
    `;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 112;
  const height = 46;
  const step = width / (values.length - 1);
  const d = values
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `
    <div class="sparkline-wrap">
      <span>30分</span>
      <svg class="sparkline ${changeClass}" viewBox="0 0 ${width} ${height}" aria-hidden="true">
        <path d="${d}"></path>
      </svg>
    </div>
  `;
}

function toneToClass(tone) {
  if (tone === "偏多") return "tone-up";
  if (tone === "偏空") return "tone-down";
  return "tone-neutral";
}

function notice(title, body, className = "") {
  const extraClass = className ? ` ${escapeAttribute(className)}` : "";
  return `<article class="notice-card${extraClass}"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></article>`;
}

function empty(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ");
}

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function formatNullable(value) {
  return value == null ? "資料不足" : formatNumber(value);
}

function formatSigned(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
