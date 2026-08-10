(function () {
  const apiBase = (window.HYDROSL_API_BASE || "").replace(/\/$/, "");
  const dataBase = (window.HYDROSL_DATA_BASE || "./data").replace(/\/$/, "");
  const state = {
    assets: [],
    selected: null,
    selectedData: null,
    staticManifest: null,
    activeTab: "current",
  };

  const $ = (id) => document.getElementById(id);
  const formatNumber = (value, digits = 0) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  };
  const assetLabel = (type) => String(type || "unknown").replaceAll("_", " ");
  const metricLabel = (code) => String(code || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function dataUrl(relativePath) {
    const base = new URL(`${dataBase}/`, window.location.href);
    return new URL(relativePath, base).toString();
  }

  function assetFileKey(assetId) {
    return String(assetId).replaceAll(":", "__");
  }

  async function getStaticManifest() {
    if (!state.staticManifest) state.staticManifest = await fetchJson(dataUrl("manifest.json"));
    return state.staticManifest;
  }

  function fetchCutoff(manifest) {
    return String(manifest.source_fetched_at || "").slice(0, 10);
  }

  async function getStatic(path) {
    const request = new URL(path, window.location.href);
    if (request.pathname === "/api/v1/overview") return fetchJson(dataUrl("overview.json"));
    if (request.pathname === "/api/v1/assets") return fetchJson(dataUrl("assets.json"));
    if (request.pathname === "/api/v1/summaries") return fetchJson(dataUrl("summaries.json"));
    if (request.pathname === "/api/v1/sources") return fetchJson(dataUrl("sources.json"));
    if (request.pathname === "/api/v1/metrics") return fetchJson(dataUrl("metrics.json"));
    if (request.pathname === "/api/v1/issues") {
      const quality = await fetchJson(dataUrl("quality.json"));
      return quality.issues || [];
    }
    if (request.pathname.startsWith("/api/v1/assets/") && request.pathname.endsWith("/data")) {
      const assetId = decodeURIComponent(request.pathname.slice("/api/v1/assets/".length, -5));
      const data = await fetchJson(dataUrl(`assets/${assetFileKey(assetId)}.json`));
      if (request.searchParams.get("include_future") === "true") return data;
      const cutoff = fetchCutoff(await getStaticManifest());
      return {
        ...data,
        records: (data.records || []).filter((item) => !item.observed_date || item.observed_date <= cutoff),
        observations: (data.observations || []).filter((item) => !item.observed_date || item.observed_date <= cutoff),
        seasonal_references: (data.seasonal_references || []).filter((item) => !item.observed_date || item.observed_date <= cutoff),
      };
    }
    if (request.pathname === "/api/v1/observations" || request.pathname === "/api/v1/trends") {
      const assetId = request.searchParams.get("asset_id");
      if (!assetId) return [];
      const data = await fetchJson(dataUrl(`assets/${assetFileKey(assetId)}.json`));
      let observations = data.observations || [];
      const includeFuture = request.searchParams.get("include_future") === "true";
      if (!includeFuture) {
        const cutoff = fetchCutoff(await getStaticManifest());
        if (cutoff) observations = observations.filter((item) => !item.observed_date || item.observed_date <= cutoff);
      }
      const metric = request.searchParams.get("metric_code");
      const season = request.searchParams.get("season");
      const from = request.searchParams.get("from");
      const to = request.searchParams.get("to");
      if (metric) observations = observations.filter((item) => item.metric_code === metric);
      if (season) observations = observations.filter((item) => item.season === season);
      if (from) observations = observations.filter((item) => !item.observed_date || item.observed_date >= from);
      if (to) observations = observations.filter((item) => !item.observed_date || item.observed_date <= to);
      observations.sort((left, right) => String(left.observed_date || "").localeCompare(String(right.observed_date || "")));
      const limit = Number(request.searchParams.get("limit") || 10000);
      if (request.pathname === "/api/v1/trends") {
        return { asset_id: assetId, metric_code: metric, unit: observations[0]?.unit || null, values: observations.slice(0, limit) };
      }
      return observations.slice(0, limit);
    }
    throw new Error(`No static read model for ${request.pathname}`);
  }

  async function get(path) {
    if (apiBase) return fetchJson(`${apiBase}${path}`);
    return getStatic(path);
  }

  function setConnection(ok, message) {
    $("connection-status").textContent = message;
    document.querySelector(".status-dot").style.background = ok ? "#7dc5a8" : "#e3a53b";
  }

  function metricValue(asset, code) {
    const metric = asset.latest_metrics?.[code];
    return metric ? metric.value : null;
  }

  function metricText(asset, code) {
    const metric = asset.latest_metrics?.[code];
    if (!metric) return "-";
    return metric.text_value || (metric.value === null || metric.value === undefined ? "-" : `${formatNumber(metric.value, 1)} ${metric.unit || ""}`.trim());
  }

  function renderOverview(data) {
    $("asset-count").textContent = formatNumber(data.asset_count);
    const breakdown = Object.entries(data.asset_types || {})
      .map(([type, count]) => `${formatNumber(count)} ${assetLabel(type)}`)
      .join(" / ");
    $("asset-breakdown").textContent = breakdown || "Awaiting latest ingestion";
    $("effective-storage").textContent = data.effective_storage_acft_total
      ? formatNumber(data.effective_storage_acft_total)
      : "-";
    $("average-filled").textContent = data.average_effective_storage_pct === null
      ? "-"
      : `${formatNumber(data.average_effective_storage_pct, 1)}%`;
    $("latest-report").textContent = data.latest_report_date || data.latest_observed_date || "-";
    $("spilling-count").textContent = formatNumber(data.reservoirs_spilling);
    $("quality-count").textContent = formatNumber(data.quality_issue_count);
  }

  function renderAssets() {
    const tbody = $("asset-table");
    const search = $("asset-search").value.trim().toLowerCase();
    const type = $("asset-type").value;
    const filtered = state.assets.filter((asset) => {
      const matchesType = !type || asset.asset_type === type;
      const haystack = [asset.canonical_name, ...(asset.aliases || []), asset.district, asset.range_name]
        .filter(Boolean).join(" ").toLowerCase();
      return matchesType && (!search || haystack.includes(search));
    });
    tbody.innerHTML = "";
    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No matching assets in the warehouse.</td></tr>';
      return;
    }
    filtered.forEach((asset) => {
      const storage = metricValue(asset, "effective_storage_pct");
      const depth = metricValue(asset, "water_depth_ft") ?? metricValue(asset, "water_depth_m");
      const spilling = metricText(asset, "spilling");
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(asset.canonical_name || "Unnamed asset")}</td>
        <td><span class="type-pill">${escapeHtml(assetLabel(asset.asset_type))}</span></td>
        <td>${escapeHtml(asset.range_name || "-")}</td>
        <td>${escapeHtml(asset.district || "-")}</td>
        <td>${storage === null ? "-" : `${formatNumber(storage, 1)}%`}</td>
        <td>${depth === null ? "-" : formatNumber(depth, 2)}</td>
        <td>${escapeHtml(spilling)}</td>
        <td>${asset.latitude != null && asset.longitude != null ? `${Number(asset.latitude).toFixed(3)}, ${Number(asset.longitude).toFixed(3)}` : "-"}</td>`;
      row.addEventListener("click", () => selectAsset(asset));
      tbody.appendChild(row);
    });
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
  }

  function renderMetricGrid(target, metrics, filter) {
    const container = $(target);
    container.innerHTML = "";
    const entries = Object.entries(metrics || {})
      .filter(([code]) => !filter || filter(code))
      .sort(([left], [right]) => left.localeCompare(right));
    if (!entries.length) {
      container.innerHTML = '<div class="empty-state">No structured measurements are available for this asset.</div>';
      return;
    }
    entries.forEach(([code, metric]) => {
      const value = metric.text_value || (metric.value === null || metric.value === undefined ? "-" : formatNumber(metric.value, 2));
      const card = document.createElement("div");
      card.className = "metric-card";
      card.innerHTML = `<span>${escapeHtml(metricLabel(code))}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(metric.unit || metric.quality_flag || "")}</small>`;
      container.appendChild(card);
    });
  }

  function metricOptions(observations) {
    const metrics = new Map();
    observations.forEach((item) => {
      if (item.value !== null && item.value !== undefined) metrics.set(item.metric_code, item.unit || "");
    });
    return [...metrics.entries()].sort(([left], [right]) => left.localeCompare(right));
  }

  function drawChart(values) {
    const svg = $("detail-chart");
    svg.innerHTML = "";
    const numeric = values.filter((item) => item.value !== null && item.value !== undefined && item.observed_date);
    if (!numeric.length) {
      svg.innerHTML = '<text x="20" y="35" fill="#6c7b82" font-size="12">No numeric history for this metric</text>';
      return;
    }
    const width = 600;
    const height = 190;
    const pad = 28;
    const valuesOnly = numeric.map((item) => Number(item.value));
    const min = Math.min(...valuesOnly);
    const max = Math.max(...valuesOnly);
    const range = max - min || 1;
    const points = numeric.map((item, index) => {
      const x = pad + (index / Math.max(numeric.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - ((Number(item.value) - min) / range) * (height - pad * 2);
      return [x, y];
    });
    const line = points.map(([x, y]) => `${x},${y}`).join(" ");
    const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
    const firstDate = numeric[0].observed_date;
    const lastDate = numeric[numeric.length - 1].observed_date;
    svg.innerHTML = `<line class="chart-axis" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}"/><polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${line}"/><text class="chart-label" x="${pad}" y="${height - 7}">${firstDate}</text><text class="chart-label" text-anchor="end" x="${width - pad}" y="${height - 7}">${lastDate}</text><text class="chart-label" x="${pad}" y="14">${formatNumber(max, 2)}</text><text class="chart-label" x="${pad}" y="${height - pad - 5}">${formatNumber(min, 2)}</text>`;
  }

  function renderHistory(data) {
    const observations = data.observations || [];
    const options = metricOptions(observations);
    const select = $("metric-select");
    const current = select.value;
    select.innerHTML = options.map(([code, unit]) => `<option value="${escapeHtml(code)}">${escapeHtml(metricLabel(code))}${unit ? ` (${escapeHtml(unit)})` : ""}</option>`).join("");
    if (options.some(([code]) => code === current)) select.value = current;
    const metric = select.value || options[0]?.[0];
    if (!metric) {
      drawChart([]);
      $("history-label").textContent = "No numeric metric";
      $("detail-latest").textContent = "-";
      return;
    }
    const season = $("history-season").value;
    const values = observations.filter((item) => item.metric_code === metric && (!season || item.season === season));
    drawChart(values);
    $("history-label").textContent = metricLabel(metric);
    const latest = values[values.length - 1];
    $("detail-latest").textContent = latest ? `${formatNumber(latest.value, 2)} ${latest.unit || ""} on ${latest.observed_date}` : "No data";
  }

  function renderSeasonal(data) {
    const tbody = $("seasonal-table");
    tbody.innerHTML = "";
    const refs = data.seasonal_references || [];
    if (!refs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No seasonal reference data.</td></tr>';
      return;
    }
    refs.forEach((item) => {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(item.season || "-")}</td><td>${escapeHtml(item.reference_period || "-")}</td><td>${escapeHtml(item.value === null || item.value === undefined ? item.raw_value || "-" : `${formatNumber(item.value, 2)} ${item.unit || ""}`)}</td><td>${escapeHtml(item.observed_date || "-")}</td><td>${escapeHtml(item.source_sheet || "-")} / ${escapeHtml(item.source_row || "-")}</td>`;
      tbody.appendChild(row);
    });
  }

  function renderOperations(data) {
    const metrics = data.latest_metrics || {};
    const operational = ["rainfall_preceding_day_mm", "spilling", "spill_value_acft", "sluice_discharge_cusec", "spilling_discharge_cusec", "diversion_cusec", "other_outflow", "sluice_status", "ds_impact"];
    renderMetricGrid("operation-metrics", metrics, (code) => operational.includes(code));
    const tbody = $("operation-records");
    tbody.innerHTML = "";
    [...(data.records || [])].reverse().forEach((record) => {
      const remarks = Object.entries(record.attributes || {}).filter(([key]) => key.includes("remark") || key.includes("spill") || key.includes("sluice")).map(([key, value]) => `${metricLabel(key)}: ${value}`).join(" | ");
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(record.observed_date || record.report_date || "-")}</td><td>${escapeHtml(record.sheet_name || "-")}</td><td>${escapeHtml(remarks || "-")}</td>`;
      tbody.appendChild(row);
    });
  }

  function renderSource(data) {
    $("detail-source").textContent = `Asset ID: ${data.asset?.asset_id || "-"}. Source aliases: ${(data.asset?.aliases || []).join(", ") || "none recorded"}. Raw source rows are preserved below.`;
    const tbody = $("source-records");
    tbody.innerHTML = "";
    [...(data.records || [])].reverse().forEach((record) => {
      const raw = Object.entries(record.raw_fields || {}).map(([key, value]) => `${key}: ${value}`).join(" | ");
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(record.sheet_name || "-")}</td><td>${escapeHtml(record.section || "-")}</td><td>${escapeHtml(record.source_row || "-")}</td><td>${escapeHtml(record.observed_date || record.report_date || "-")}</td><td class="raw-cell">${escapeHtml(raw)}</td>`;
      tbody.appendChild(row);
    });
  }

  function renderSummaries(summaries) {
    $("summary-count").textContent = formatNumber(summaries.length);
    const tbody = $("summaries-table");
    tbody.innerHTML = "";
    summaries.slice(0, 100).forEach((summary) => {
      const values = summary.values || {};
      const value = (key) => values[key]?.value ?? values[key]?.raw_value ?? "-";
      const scalar = (key) => values[key]?.value ?? values[key]?.raw_value ?? values[key] ?? "-";
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(summary.sheet_name || "-")}</td><td>${escapeHtml(summary.scope || "-")}</td><td>${escapeHtml(scalar("tank_count"))}</td><td>${escapeHtml(value("gross_storage_acft"))}</td><td>${escapeHtml(value("effective_storage_acft"))}</td><td>${escapeHtml(value("effective_storage_pct"))}</td>`;
      tbody.appendChild(row);
    });
  }

  function renderIssues(issues) {
    const tbody = $("issues-table");
    tbody.innerHTML = "";
    issues.forEach((issue) => {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(issue.sheet_name || "-")}</td><td>${escapeHtml(issue.field || issue.code || "-")}</td><td class="raw-cell">${escapeHtml(issue.raw_value || "-")}</td><td>${escapeHtml(issue.message || "-")}</td>`;
      tbody.appendChild(row);
    });
    if (!issues.length) tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No quality issues recorded.</td></tr>';
  }

  function renderSourceCatalogue(sources) {
    const target = $("source-catalogue");
    target.innerHTML = `<p>Run: ${escapeHtml(sources.run_id || "-")}<br/>Fetched: ${escapeHtml(sources.fetched_at || "-")}</p>`;
    (sources.sheets || []).forEach((sheet) => {
      const row = document.createElement("div");
      row.className = "source-row";
      row.innerHTML = `<strong>${escapeHtml(sheet.sheet_name || "-")}</strong><span>GID ${escapeHtml(sheet.gid || "-")} / ${escapeHtml(sheet.status || "-")}</span>`;
      target.appendChild(row);
    });
  }

  function setDetailTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll(".detail-tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
    document.querySelectorAll(".detail-view").forEach((view) => view.classList.toggle("hidden", view.dataset.view !== tab));
    if (state.selectedData) renderActiveDetail();
  }

  function renderActiveDetail() {
    const data = state.selectedData;
    if (state.activeTab === "current") renderMetricGrid("current-metrics", data.latest_metrics || {});
    if (state.activeTab === "history") renderHistory(data);
    if (state.activeTab === "seasonal") renderSeasonal(data);
    if (state.activeTab === "operations") renderOperations(data);
    if (state.activeTab === "source") renderSource(data);
  }

  async function selectAsset(asset) {
    state.selected = asset;
    $("detail-name").textContent = asset.canonical_name || "Unnamed asset";
    $("detail-placeholder").classList.add("hidden");
    $("detail-content").classList.remove("hidden");
    $("detail-meta").innerHTML = [
      `<span class="meta-chip">${escapeHtml(assetLabel(asset.asset_type))}</span>`,
      `<span class="meta-chip">${escapeHtml(asset.district || "District unavailable")}</span>`,
      `<span class="meta-chip">${escapeHtml(asset.range_name || "Range unavailable")}</span>`,
      `<span class="meta-chip">${escapeHtml(asset.latest_metrics?.effective_storage_pct?.observed_date || "Date unavailable")}</span>`,
    ].join("");
    try {
      const includeFuture = $("show-future").checked;
      state.selectedData = await get(`/api/v1/assets/${encodeURIComponent(asset.asset_id)}/data?include_future=${includeFuture}`);
      renderActiveDetail();
    } catch (error) {
      $("detail-placeholder").textContent = `Asset data unavailable: ${error.message}`;
      $("detail-placeholder").classList.remove("hidden");
      $("detail-content").classList.add("hidden");
    }
  }

  async function boot() {
    $("asset-type").addEventListener("change", renderAssets);
    $("asset-search").addEventListener("input", renderAssets);
    $("metric-select").addEventListener("change", () => state.selectedData && renderHistory(state.selectedData));
    $("history-season").addEventListener("change", () => state.selectedData && renderHistory(state.selectedData));
    $("show-future").addEventListener("change", () => state.selected && selectAsset(state.selected));
    document.querySelectorAll(".detail-tab").forEach((button) => button.addEventListener("click", () => setDetailTab(button.dataset.tab)));
    try {
      const [overview, assets, summaries, sources, quality] = await Promise.all([
        get("/api/v1/overview"),
        get("/api/v1/assets"),
        get("/api/v1/summaries"),
        get("/api/v1/sources"),
        get("/api/v1/issues"),
      ]);
      state.assets = assets;
      renderOverview(overview);
      renderAssets();
      renderSummaries(summaries);
      renderSourceCatalogue(sources);
      renderIssues(quality);
      setConnection(true, apiBase ? "API connected" : "Published data connected");
    } catch (error) {
      setConnection(false, "Data unavailable");
      $("asset-table").innerHTML = `<tr><td colspan="8" class="empty-state">${escapeHtml(error.message)}. Run ingestion/export or check the published data URL.</td></tr>`;
    }
  }

  boot();
})();
