(function () {
  const apiBase = (window.HYDROSL_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
  const state = { assets: [], selected: null };

  const $ = (id) => document.getElementById(id);
  const formatNumber = (value, digits = 0) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  };
  const assetLabel = (type) => String(type || "unknown").replaceAll("_", " ");

  async function get(path) {
    const response = await fetch(`${apiBase}${path}`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function setConnection(ok, message) {
    $("connection-status").textContent = message;
    document.querySelector(".status-dot").style.background = ok ? "#7dc5a8" : "#e3a53b";
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
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No matching assets in the warehouse.</td></tr>';
      return;
    }
    filtered.slice(0, 250).forEach((asset) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(asset.canonical_name || "Unnamed asset")}</td>
        <td><span class="type-pill">${escapeHtml(assetLabel(asset.asset_type))}</span></td>
        <td>${escapeHtml(asset.range_name || "-")}</td>
        <td>${escapeHtml(asset.district || "-")}</td>
        <td>${asset.latitude != null && asset.longitude != null
          ? `${Number(asset.latitude).toFixed(3)}, ${Number(asset.longitude).toFixed(3)}` : "-"}</td>`;
      row.addEventListener("click", () => selectAsset(asset));
      tbody.appendChild(row);
    });
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
  }

  function drawChart(values) {
    const svg = $("detail-chart");
    svg.innerHTML = "";
    if (!values.length) return;
    const width = 360;
    const height = 130;
    const pad = 10;
    const points = values.map((item, index) => {
      const x = pad + (index / Math.max(values.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - (Math.max(0, Math.min(100, Number(item.value))) / 100) * (height - pad * 2);
      return [x, y];
    });
    const line = points.map(([x, y]) => `${x},${y}`).join(" ");
    const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
    svg.innerHTML = `<polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${line}"/>`;
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
    ].join("");
    $("detail-source").textContent = `Asset ID: ${asset.asset_id}. Source aliases: ${(asset.aliases || []).join(", ") || "none recorded"}.`;
    try {
      const observations = await get(`/api/v1/observations?asset_id=${encodeURIComponent(asset.asset_id)}&metric_code=effective_storage_pct&limit=400`);
      const usable = observations.filter((item) => item.value !== null && item.value !== undefined);
      drawChart(usable);
      const latest = usable[usable.length - 1];
      $("detail-latest").textContent = latest ? `${formatNumber(latest.value, 1)}% on ${latest.observed_date || "unknown date"}` : "No percentage data";
    } catch (error) {
      $("detail-latest").textContent = "Observation request unavailable";
      $("detail-source").textContent += ` ${error.message}`;
    }
  }

  async function boot() {
    $("asset-type").addEventListener("change", renderAssets);
    $("asset-search").addEventListener("input", renderAssets);
    try {
      const [overview, assets] = await Promise.all([get("/api/v1/overview"), get("/api/v1/assets")]);
      state.assets = assets;
      renderOverview(overview);
      renderAssets();
      setConnection(true, "API connected");
    } catch (error) {
      setConnection(false, "API unavailable");
      $("asset-table").innerHTML = `<tr><td colspan="5" class="empty-state">${escapeHtml(error.message)}. Start the HydroSL API and run ingestion.</td></tr>`;
    }
  }

  boot();
})();
