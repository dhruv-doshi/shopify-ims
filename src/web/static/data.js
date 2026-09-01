const root = document.querySelector(".container");
const token = root.dataset.token;
let baseDashboardData = null;
let activePrompt = "overview";

function hide(el) {
  if (el) el.style.display = "none";
}

function show(el) {
  if (el) el.style.display = "";
}

function formatChartLabel(label) {
  const text = String(label || "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text.slice(5);
  if (text.length > 10) return `${text.slice(0, 9)}…`;
  return text;
}

function formatAsOf(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function showError(message) {
  hide(document.getElementById("banner"));
  hide(document.getElementById("demo-badge"));
  hide(document.getElementById("meta"));
  hide(document.getElementById("prompt-chips"));
  hide(document.getElementById("kpis"));
  hide(document.getElementById("charts"));
  hide(document.getElementById("tables"));
  hide(document.getElementById("chart"));
  hide(document.getElementById("table"));
  hide(document.getElementById("subtitle"));
  hide(document.getElementById("summary"));
  document.getElementById("title").textContent = "Report unavailable";
  const errorEl = document.getElementById("error-state");
  errorEl.innerHTML = `<h2>Link expired or unavailable</h2><p>${message}</p>`;
  errorEl.classList.remove("hidden");
}

function renderBarChart(container, chart) {
  const labels = (chart.labels || []).map(formatChartLabel);
  const values = chart.values || [];
  if (!labels.length) return;
  const max = Math.max(...values, 1);
  const wrap = document.createElement("div");
  wrap.className = "chart-block";
  wrap.innerHTML = `<h3>${chart.title || "Chart"}</h3>`;
  const bars = document.createElement("div");
  bars.className = "chart bar-chart";
  bars.innerHTML = labels
    .map((label, i) => {
      const h = ((values[i] || 0) / max) * 100;
      return `<div class="bar" style="height:${h}%" title="${label}"><span>${label}</span></div>`;
    })
    .join("");
  wrap.appendChild(bars);
  container.appendChild(wrap);
}

function renderLineChart(container, chart) {
  const labels = (chart.labels || []).map(formatChartLabel);
  const values = chart.values || [];
  if (!labels.length) return;
  const max = Math.max(...values, 1);
  const w = 320;
  const h = 160;
  const pad = 20;
  const points = values.map((v, i) => {
    const x = pad + (i / Math.max(labels.length - 1, 1)) * (w - pad * 2);
    const y = h - pad - (v / max) * (h - pad * 2);
    return `${x},${y}`;
  });
  const wrap = document.createElement("div");
  wrap.className = "chart-block";
  wrap.innerHTML = `<h3>${chart.title || "Chart"}</h3>`;
  wrap.innerHTML += `<svg class="line-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${chart.title || "line chart"}">
    <polyline fill="none" stroke="#111" stroke-width="2" points="${points.join(" ")}" />
  </svg>
  <div class="line-labels">${labels.map((l) => `<span title="${l}">${l}</span>`).join("")}</div>`;
  container.appendChild(wrap);
}

function isDashboardPayload(data) {
  return (
    Array.isArray(data.kpis) ||
    Array.isArray(data.charts) ||
    Array.isArray(data.tables) ||
    Boolean(data.prompt) ||
    Boolean(data.snapshot)
  );
}

function buildQuickView(baseData, prompt) {
  const view = JSON.parse(JSON.stringify(baseData));
  const snap = view.snapshot || {};
  const inventory = snap.inventory || [];
  const salesByProduct = snap.sales_by_product || [];
  const salesByDay = (snap.sales_by_day || []).slice(-7);
  const kpis = snap.kpis || {};

  if (prompt === "low stock") {
    const lowStock = inventory.filter((p) => (p.qty || 0) <= 5);
    view.tables = [
      {
        title: "Low stock (≤5 units)",
        columns: ["Product", "Qty", "Price"],
        rows: lowStock.slice(0, 15).map((p) => [p.name, String(p.qty), `$${Number(p.price).toFixed(2)}`]),
      },
    ];
    view.charts = [];
    view.kpis = [
      { label: "Low stock SKUs", value: String(lowStock.length), hint: "Live inventory" },
      { label: "Units on hand", value: String(kpis.units_on_hand || 0), hint: "Live inventory" },
      { label: "Products", value: String(view.product_count || inventory.length), hint: "Live inventory" },
    ];
    view.bannerText = "Low stock view";
    return view;
  }

  if (prompt === "top sellers") {
    view.tables = [
      {
        title: "Top sellers (30d demo sales)",
        columns: ["Product", "Units", "Revenue"],
        rows: salesByProduct.slice(0, 10).map((p) => [p.name, String(p.units), `$${Number(p.revenue).toFixed(2)}`]),
      },
    ];
    view.charts = salesByProduct.length
      ? [
          {
            type: "bar",
            title: "Top sellers by revenue (demo)",
            labels: salesByProduct.slice(0, 8).map((p) => p.name),
            values: salesByProduct.slice(0, 8).map((p) => Number(p.revenue.toFixed(2))),
          },
        ]
      : [];
    view.kpis = [
      { label: "Top seller units", value: String(salesByProduct[0]?.units || 0), hint: "Demo sales" },
      { label: "Top seller revenue", value: `$${Number(salesByProduct[0]?.revenue || 0).toFixed(2)}`, hint: "Demo sales" },
      { label: "Revenue (30d)", value: `$${Number(kpis.revenue_30d || 0).toFixed(2)}`, hint: "Demo sales" },
    ];
    view.bannerText = "Top sellers view";
    return view;
  }

  view.bannerText = view.prompt ? `Read-only · generated for: ${view.prompt}` : "Overview";
  return view;
}

function renderPromptChips(data, onSelect) {
  const chipsEl = document.getElementById("prompt-chips");
  const prompts = data.quick_prompts || ["overview", "low stock", "top sellers"];
  if (!data.snapshot) {
    hide(chipsEl);
    return;
  }
  chipsEl.innerHTML = prompts
    .map((prompt) => {
      const active = prompt === activePrompt ? " active" : "";
      return `<button type="button" class="prompt-chip${active}" data-prompt="${prompt}">${prompt}</button>`;
    })
    .join("");
  chipsEl.classList.remove("hidden");
  chipsEl.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.addEventListener("click", () => onSelect(btn.dataset.prompt));
  });
}

function renderDashboard(data) {
  if (!baseDashboardData) baseDashboardData = JSON.parse(JSON.stringify(data));
  const view =
    activePrompt === "overview"
      ? baseDashboardData
      : buildQuickView(baseDashboardData, activePrompt);

  hide(document.getElementById("chart"));
  hide(document.getElementById("table"));
  hide(document.getElementById("error-state"));

  document.getElementById("title").textContent = view.title || "Inventory dashboard";
  const subtitle = document.getElementById("subtitle");
  subtitle.textContent = view.subtitle || "";
  show(subtitle);
  hide(document.getElementById("summary"));

  const badge = document.getElementById("demo-badge");
  badge.classList.remove("hidden");

  const meta = document.getElementById("meta");
  const asOf = formatAsOf(view.as_of);
  const count = view.product_count ?? (view.snapshot?.inventory || []).length;
  const source = view.inventory_source === "shopify" ? "Shopify inventory" : "Local demo inventory";
  meta.textContent = asOf ? `As of ${asOf} · ${count} products · ${source}` : `${count} products · ${source}`;
  meta.classList.remove("hidden");

  const banner = document.getElementById("banner");
  const bannerText = view.bannerText || (view.prompt ? `Read-only · generated for: ${view.prompt}` : "");
  if (bannerText) {
    banner.textContent = bannerText;
    banner.classList.remove("hidden");
  } else {
    hide(banner);
  }

  renderPromptChips(baseDashboardData, (prompt) => {
    activePrompt = prompt;
    renderDashboard(baseDashboardData);
  });

  const kpisEl = document.getElementById("kpis");
  const kpis = Array.isArray(view.kpis) ? view.kpis : [];
  if (kpis.length) {
    show(kpisEl);
    kpisEl.innerHTML = kpis
      .map(
        (k) =>
          `<div class="kpi-card"><div class="kpi-label">${k.label || ""}</div>` +
          `<div class="kpi-value">${k.value || ""}</div>` +
          `${k.hint ? `<div class="kpi-hint">${k.hint}</div>` : ""}</div>`
      )
      .join("");
  } else {
    hide(kpisEl);
  }

  const chartsEl = document.getElementById("charts");
  chartsEl.innerHTML = "";
  (view.charts || []).forEach((chart) => {
    if (chart.type === "line") renderLineChart(chartsEl, chart);
    else renderBarChart(chartsEl, chart);
  });
  if (!chartsEl.children.length) hide(chartsEl);
  else show(chartsEl);

  const tablesEl = document.getElementById("tables");
  tablesEl.innerHTML = "";
  (view.tables || []).forEach((table) => {
    const block = document.createElement("div");
    block.className = "table-block";
    const cols = table.columns || [];
    const rows = table.rows || [];
    block.innerHTML = `<h3>${table.title || "Table"}</h3>
      <table><thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    tablesEl.appendChild(block);
  });
  if (!tablesEl.children.length) hide(tablesEl);
  else show(tablesEl);
}

function renderLegacy(data) {
  hide(document.getElementById("error-state"));
  hide(document.getElementById("banner"));
  hide(document.getElementById("demo-badge"));
  hide(document.getElementById("meta"));
  hide(document.getElementById("prompt-chips"));
  hide(document.getElementById("kpis"));
  hide(document.getElementById("charts"));
  hide(document.getElementById("tables"));

  document.getElementById("title").textContent = data.title || "Inventory report";
  document.getElementById("summary").textContent = data.summary || "";

  const columns = data.columns || [];
  const rows = data.rows || [];
  const thead = document.querySelector("#table thead");
  const tbody = document.querySelector("#table tbody");
  thead.innerHTML = `<tr>${columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");

  const chart = data.chart;
  const chartEl = document.getElementById("chart");
  if (chart && chart.labels && chart.values) {
    show(chartEl);
    const labels = chart.labels.map(formatChartLabel);
    const max = Math.max(...chart.values, 1);
    chartEl.innerHTML = labels
      .map((label, i) => {
        const h = (chart.values[i] / max) * 100;
        return `<div class="bar" style="height:${h}%" title="${label}"><span>${label}</span></div>`;
      })
      .join("");
  } else {
    hide(chartEl);
  }
  show(document.getElementById("table"));
}

async function load() {
  const res = await fetch(`/api/data/${token}`);
  if (res.status === 404) {
    showError("This link has expired. Send /dashboard in Telegram to generate a new one.");
    return;
  }
  if (!res.ok) {
    showError("Could not load this report. Send /dashboard in Telegram to try again.");
    return;
  }
  const data = await res.json();
  activePrompt = data.prompt || "overview";
  if (isDashboardPayload(data)) {
    renderDashboard(data);
  } else {
    renderLegacy(data);
  }
}

load().catch(() => {
  showError("Could not load this report. Send /dashboard in Telegram to try again.");
});
