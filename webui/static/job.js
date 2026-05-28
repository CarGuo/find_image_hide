const $ = (sel) => document.querySelector(sel);

let allResults = [];
let pollTimer = null;

function slugFromPath(imagePath, outputDir) {
  if (!imagePath || !outputDir) return "";
  const parts = outputDir.split(/[\\/]/);
  return parts[parts.length - 1] || "";
}

function badge(level) {
  const lvl = level || "UNKNOWN";
  return `<span class="badge ${lvl}">${lvl}</span>`;
}

function renderTable() {
  const filterText = ($("#filter").value || "").toLowerCase();
  const filterRisk = $("#risk-filter").value;
  const tbody = $("#results-body");
  tbody.innerHTML = "";
  allResults.forEach((r, idx) => {
    const fname = (r.image_path || "").split(/[\\/]/).pop();
    const risk = r.ok ? (r.risk_level || "UNKNOWN") : "ERROR";
    if (filterText && !fname.toLowerCase().includes(filterText)) return;
    if (filterRisk && risk !== filterRisk) return;
    const slug = slugFromPath(r.image_path, r.output_dir);
    const ms = r.module_scores || {};
    const stf = r.steg_findings || {};
    const exf = r.extraction_findings || {};
    const spa = stf.spa_rate != null ? (stf.spa_rate * 100).toFixed(1) + "%" : "-";
    const chi = stf.chi_square_p != null ? stf.chi_square_p.toFixed(3) : "-";
    const trail = exf.trailing_bytes != null ? exf.trailing_bytes : 0;
    const trailMagics = (exf.trailing_magics || []).join(",");
    const trailDisp = trailMagics ? `${trail} <span class="small" style="color:#c43c3c">(${trailMagics})</span>` : `${trail}`;
    const extScore = ms.extraction != null ? ms.extraction.toFixed(2) : "-";
    const conf = r.confidence != null ? r.confidence.toFixed(2) : "-";
    const detail = r.ok
      ? `<a href="/jobs/${JOB_ID}/image/${encodeURIComponent(slug)}">详情</a>`
      : `<span class="muted small">${(r.error || "").substring(0,80)}</span>`;
    tbody.insertAdjacentHTML("beforeend", `
      <tr>
        <td>${idx + 1}</td>
        <td title="${r.image_path}">${fname}</td>
        <td>${r.format || "-"}</td>
        <td>${r.width ? r.width + "x" + r.height : "-"}</td>
        <td>${badge(risk)}</td>
        <td>${conf}</td>
        <td><span class="small">${r.ai_status || "-"}</span></td>
        <td>${spa}</td>
        <td>${chi}</td>
        <td>${trailDisp}</td>
        <td>${extScore}</td>
        <td>${detail}</td>
      </tr>
    `);
  });
}

function renderStats(job) {
  const stats = (job.summary && job.summary.stats) || {};
  const counts = stats.risk_counts || {};
  const pieces = ["HIGH", "MEDIUM", "LOW", "UNKNOWN", "ERROR"]
    .filter(k => counts[k])
    .map(k => `<span class="stat">${badge(k)} ${counts[k]}</span>`);
  $("#stats").innerHTML = pieces.join("");
}

async function poll() {
  try {
    const resp = await fetch(`/api/jobs/${JOB_ID}`);
    if (!resp.ok) return;
    const job = await resp.json();
    const total = job.total || 0;
    const done = job.done || 0;
    $("#progress-line").innerHTML = `
      <strong>状态：</strong>${job.status} &nbsp;
      <strong>目录：</strong>${job.root} &nbsp;
      <strong>进度：</strong>${done} / ${total}
    `;
    if (job.results && job.results.length) {
      const seen = new Set(allResults.map(r => r.image_path));
      job.results.forEach(r => { if (!seen.has(r.image_path)) allResults.push(r); });
      renderTable();
    }
    if (job.status === "done") {
      const sumResp = await fetch(`/api/jobs/${JOB_ID}/summary`);
      if (sumResp.ok) {
        const summary = await sumResp.json();
        allResults = summary.results || allResults;
        renderTable();
        renderStats({ summary });
      }
      clearInterval(pollTimer);
      pollTimer = null;
    } else if (job.status === "error") {
      $("#progress-line").innerHTML = `<span style="color:#c43c3c">失败：${job.error || "unknown"}</span>`;
      clearInterval(pollTimer);
      pollTimer = null;
    }
  } catch (e) {
    console.error(e);
  }
}

$("#filter").addEventListener("input", renderTable);
$("#risk-filter").addEventListener("change", renderTable);

poll();
pollTimer = setInterval(poll, 1500);
