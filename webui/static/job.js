const $ = (sel) => document.querySelector(sel);

let allResults = [];
let pollTimer = null;

const RISK_CN = { HIGH: "高风险", MEDIUM: "中风险", LOW: "低风险", UNKNOWN: "未知", ERROR: "出错" };

const AI_STATUS_CN = {
  VERIFIED_AI_GENERATED: "C2PA 验证：AI 生成",
  VERIFIED_AI_EDITED: "C2PA 验证：AI 编辑",
  PROVENANCE_PRESENT_BUT_UNVERIFIED: "有 C2PA 但未验证",
  POSSIBLE_AI_BUT_UNVERIFIED: "疑似 AI（关键字命中）",
  NO_PROVENANCE_FOUND: "无可信来源凭证",
  PROVENANCE_STRIPPED_OR_UNKNOWN: "凭证被剥离 / 未知",
};

function slugFromPath(imagePath, outputDir) {
  if (!imagePath || !outputDir) return "";
  const parts = outputDir.split(/[\\/]/);
  return parts[parts.length - 1] || "";
}

function badge(level) {
  const lvl = level || "UNKNOWN";
  const cn = RISK_CN[lvl] || lvl;
  return `<span class="badge ${lvl}">${cn}</span>`;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function buildEvidenceChips(r) {
  const chips = [];
  const ms = r.module_scores || {};
  const stf = r.steg_findings || {};
  const exf = r.extraction_findings || {};

  if (exf.trailing_bytes && exf.trailing_bytes > 0) {
    const tags = (exf.trailing_magics || []).join(", ");
    chips.push({ cls: "chip-high", text: `图像末尾附加 ${exf.trailing_bytes} 字节${tags ? "（" + tags + "）" : ""}` });
  }
  if (exf.lsb_streams && exf.lsb_streams > 0) {
    chips.push({ cls: "chip-high", text: `LSB 比特流提取出可读内容（${exf.lsb_streams} 段）` });
  }
  if ((ms.steganalysis || 0) >= 0.5) {
    const spa = stf.spa_rate != null ? (stf.spa_rate * 100).toFixed(1) + "%" : "-";
    const chi = stf.chi_square_p != null ? stf.chi_square_p.toFixed(2) : "-";
    chips.push({ cls: "chip-high", text: `隐写检测命中（卡方 P=${chi}, SPA=${spa}）` });
  } else if ((stf.chi_square_p || 0) >= 0.95 || (stf.spa_rate || 0) >= 0.05) {
    const spa = stf.spa_rate != null ? (stf.spa_rate * 100).toFixed(1) + "%" : "-";
    const chi = stf.chi_square_p != null ? stf.chi_square_p.toFixed(2) : "-";
    chips.push({ cls: "chip-med", text: `隐写指标偏高（卡方 P=${chi}, SPA=${spa}）` });
  }
  if ((ms.lsb || 0) >= 0.9) {
    chips.push({ cls: "chip-high", text: "LSB 位平面接近白噪声" });
  }
  if ((ms.metadata || 0) >= 0.6) {
    chips.push({ cls: "chip-high", text: "元数据命中版权图库 / AI 关键字" });
  }
  if ((ms.visible_watermark || 0) >= 0.5) {
    chips.push({ cls: "chip-high", text: "OCR 出可见水印 / 版权文字" });
  }
  if ((ms.phash_match || 0) >= 0.5) {
    chips.push({ cls: "chip-high", text: "pHash 命中本地参考图" });
  }
  if ((ms.fft || 0) >= 0.5) {
    chips.push({ cls: "chip-med", text: "FFT 频谱异常" });
  }
  if ((ms.dct || 0) >= 0.5) {
    chips.push({ cls: "chip-med", text: "DCT 分布偏离自然图像" });
  }
  if ((ms.noise || 0) >= 0.5) {
    chips.push({ cls: "chip-med", text: "局部噪声不一致" });
  }
  if ((ms.ela || 0) >= 0.5) {
    chips.push({ cls: "chip-med", text: "ELA 误差异常" });
  }
  const aiCn = AI_STATUS_CN[r.ai_status] || r.ai_status;
  if (aiCn) {
    let cls = "chip-info";
    if ((r.ai_status || "").startsWith("VERIFIED")) cls = "chip-high";
    else if (r.ai_status === "POSSIBLE_AI_BUT_UNVERIFIED") cls = "chip-med";
    chips.push({ cls, text: aiCn });
  }
  return chips;
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
    const conf = r.confidence != null ? r.confidence.toFixed(2) : "-";
    const detail = r.ok
      ? `<a href="/jobs/${JOB_ID}/image/${encodeURIComponent(slug)}">查看详情</a>`
      : `<span class="muted small">${escapeHtml((r.error || "").substring(0, 80))}</span>`;

    let conclusionHtml;
    if (!r.ok) {
      conclusionHtml = `<div class="muted small">分析失败：${escapeHtml((r.error || "").substring(0, 200))}</div>`;
    } else {
      const summaryText = r.summary || "（未生成结论）";
      const chips = buildEvidenceChips(r);
      const chipsHtml = chips.length
        ? `<div class="chips">${chips.map(c => `<span class="chip ${c.cls}">${escapeHtml(c.text)}</span>`).join("")}</div>`
        : `<div class="chips"><span class="chip chip-low">未触发明显风险信号</span></div>`;
      conclusionHtml = `<div class="conclusion-summary">${escapeHtml(summaryText)}</div>${chipsHtml}`;
    }

    tbody.insertAdjacentHTML("beforeend", `
      <tr>
        <td>${idx + 1}</td>
        <td title="${escapeHtml(r.image_path)}"><div class="fname">${escapeHtml(fname)}</div></td>
        <td>${badge(risk)}</td>
        <td>${conf}</td>
        <td>${conclusionHtml}</td>
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

function fmtDuration(sec) {
  if (sec == null || !isFinite(sec) || sec < 0) return "-";
  if (sec < 60) return `${Math.round(sec)} 秒`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m} 分 ${s} 秒`;
}

function fmtFileName(p) {
  if (!p) return "";
  const parts = String(p).split(/[\\/]/);
  return parts[parts.length - 1] || "";
}

const PHASE_CN = {
  starting: "已读取目录，开始派发任务…",
  analyzing: "正在分析中…",
  no_images: "目录里没有发现支持的图片",
};

function updateProgressUi(job) {
  const total = job.total || 0;
  const done = job.done || 0;
  const status = job.status || "running";
  const phase = job.phase || "";
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  // 状态徽章
  const pill = $("#job-status-pill");
  pill.classList.remove("done", "error");
  if (status === "done") {
    pill.classList.add("done");
    pill.textContent = `已完成（${done}/${total}）`;
  } else if (status === "error") {
    pill.classList.add("error");
    pill.textContent = "扫描失败";
  } else {
    // running
    if (total === 0 && phase !== "no_images") {
      pill.textContent = "正在读取目录…";
    } else if (phase === "no_images") {
      pill.textContent = "目录为空";
    } else {
      pill.textContent = `扫描中（${done}/${total}）`;
    }
  }

  // 副标题（meta）
  const meta = $("#job-progress-meta");
  if (status === "error") {
    meta.textContent = job.error || "扫描出错";
  } else if (status === "done") {
    const elapsed = job.started_at ? (Date.now() / 1000 - job.started_at) : null;
    meta.textContent = `共 ${total} 张图，用时 ${fmtDuration(elapsed)}`;
  } else if (total === 0) {
    meta.textContent = PHASE_CN[phase] || "枚举目录、计算图片数量…";
  } else if (done < total) {
    // 估算剩余时间
    const elapsed = job.started_at ? (Date.now() / 1000 - job.started_at) : null;
    let etaText = "";
    if (elapsed && done > 0) {
      const perItem = elapsed / done;
      const remain = perItem * (total - done);
      etaText = `，预计还需 ${fmtDuration(remain)}`;
    }
    meta.textContent = `已完成 ${done} / ${total}${etaText}`;
  } else {
    meta.textContent = "所有图片都已分析，正在生成汇总…";
  }

  // 进度条（fill + percent）
  const fill = $("#progress-fill");
  const track = fill.parentElement;
  fill.classList.remove("done", "error");
  track.classList.remove("done", "error");
  if (status === "done") {
    fill.classList.add("done");
    track.classList.add("done");
    fill.style.width = "100%";
    $("#progress-percent").textContent = "100%";
  } else if (status === "error") {
    fill.classList.add("error");
    track.classList.add("error");
    $("#progress-percent").textContent = "！";
  } else {
    fill.style.width = pct + "%";
    if (total > 0) {
      $("#progress-percent").textContent = pct + "%";
    } else {
      // 还没拿到 total，shimmer 自己会动，百分比留空
      $("#progress-percent").textContent = "";
    }
  }

  // 当前正在分析的文件
  const cur = $("#job-current-file");
  const fname = fmtFileName(job.current_file || "");
  if (status === "running" && fname) {
    cur.textContent = fname;
    cur.classList.add("has-file");
  } else if (status === "running" && total > 0 && done < total) {
    // 多 worker 时不一定有 current_file；展示一句兜底
    cur.textContent = "并发分析中…";
    cur.classList.remove("has-file");
  } else {
    cur.textContent = "";
    cur.classList.remove("has-file");
  }

  // 已用时
  const elapsedEl = $("#job-elapsed");
  if (job.started_at) {
    const elapsed = Date.now() / 1000 - job.started_at;
    if (status === "done") {
      elapsedEl.textContent = `用时 ${fmtDuration(elapsed)}`;
    } else if (status === "running") {
      elapsedEl.textContent = `已用时 ${fmtDuration(elapsed)}`;
    } else {
      elapsedEl.textContent = "";
    }
  } else {
    elapsedEl.textContent = "";
  }
}

async function poll() {
  try {
    const resp = await fetch(`/api/jobs/${JOB_ID}`);
    if (!resp.ok) return;
    const job = await resp.json();
    updateProgressUi(job);

    if (job.results && job.results.length) {
      const seen = new Set(allResults.map(r => r.image_path));
      job.results.forEach(r => {
        if (r && r.image_path && !seen.has(r.image_path)) allResults.push(r);
      });
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
      clearInterval(pollTimer);
      pollTimer = null;
    }
  } catch (e) {
    console.error(e);
  }
}

$("#filter").addEventListener("input", renderTable);
$("#risk-filter").addEventListener("change", renderTable);

// 在第一次轮询返回前先把 UI 摆好（pulse + shimmer 已经在转），避免空白
updateProgressUi({ status: "running", done: 0, total: 0, phase: "" });

poll();
pollTimer = setInterval(poll, 1000);
