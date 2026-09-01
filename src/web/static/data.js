const root = document.querySelector(".container");
const token = root.dataset.token;

async function load() {
  const data = await fetch(`/api/data/${token}`).then((r) => r.json());
  document.getElementById("title").textContent = data.title || "Inventory report";
  document.getElementById("summary").textContent = data.summary || "";

  const columns = data.columns || [];
  const rows = data.rows || [];
  const thead = document.querySelector("#table thead");
  const tbody = document.querySelector("#table tbody");
  thead.innerHTML = `<tr>${columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("");

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
    chartEl.style.display = "none";
  }
}

load().catch(console.error);
