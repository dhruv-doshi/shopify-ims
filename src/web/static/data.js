const root = document.querySelector(".container");
const token = root.dataset.token;

function hide(el) {
  if (el) el.style.display = "none";
}

function renderBarChart(container, chart) {
  const labels = chart.labels || [];
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
      return `<div class="bar" style="height:${h}%"><span>${label}</span></div>`;
    })
    .join("");
  wrap.appendChild(bars);
  container.appendChild(wrap);
}

function renderLineChart(container, chart) {
  const labels = chart.labels || [];
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
  <div class="line-labels">${labels.map((l) => `<span>${l}</span>`).join("")}</div>`;
  container.appendChild(wrap);
}

function isDashboardPayload(data) {
  return (
    Array.isArray(data.kpis) ||
    Array.isArray(data.charts) ||
    Array.isArray(data.tables) ||
    Boolean(data.prompt)
  );
}

function renderDashboard(data) {
  hide(document.getElementById("chart"));
  hide(document.getElementById("table"));

  document.getElementById("title").textContent = data.title || "Inventory dashboard";
  const subtitle = document.getElementById("subtitle");
  subtitle.textContent = data.subtitle || "";
  hide(document.getElementById("summary"));

  const banner = document.getElementById("banner");
  if (data.prompt) {
    banner.textContent = `Read-only · generated for: ${data.prompt}`;
    banner.classList.remove("hidden");
  } else {
    hide(banner);
  }

  const kpisEl = document.getElementById("kpis");
  const kpis = Array.isArray(data.kpis) ? data.kpis : [];
  if (kpis.length) {
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
  (data.charts || []).forEach((chart) => {
    if (chart.type === "line") renderLineChart(chartsEl, chart);
    else renderBarChart(chartsEl, chart);
  });
  if (!chartsEl.children.length) hide(chartsEl);

  const tablesEl = document.getElementById("tables");
  tablesEl.innerHTML = "";
  (data.tables || []).forEach((table) => {
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
}

function renderLegacy(data) {
  hide(document.getElementById("banner"));
  hide(document.getElementById("subtitle"));
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
    const max = Math.max(...chart.values, 1);
    chartEl.innerHTML = chart.labels
      .map((label, i) => {
        const h = (chart.values[i] / max) * 100;
        return `<div class="bar" style="height:${h}%"><span>${label}</span></div>`;
      })
      .join("");
  } else {
    hide(chartEl);
  }
}

async function load() {
  const res = await fetch(`/api/data/${token}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (isDashboardPayload(data)) {
    renderDashboard(data);
  } else {
    renderLegacy(data);
  }
}

load().catch(console.error);
