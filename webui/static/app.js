const $ = (sel) => document.querySelector(sel);

const SUPPORTED_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"];

function isSupported(name) {
  const lower = (name || "").toLowerCase();
  return SUPPORTED_EXTS.some(ext => lower.endsWith(ext));
}

$("#scan-btn").addEventListener("click", async () => {
  const dir = $("#dir").value.trim();
  const recursive = $("#recursive").checked;
  const workers = parseInt($("#workers").value || "2", 10);
  const status = $("#status");

  if (!dir) {
    status.className = "status error";
    status.textContent = "请填写目录路径";
    return;
  }
  status.className = "status";
  status.textContent = "正在提交扫描任务...";
  $("#scan-btn").disabled = true;

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory: dir, recursive, workers }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      status.className = "status error";
      status.textContent = "失败：" + (data.error || resp.status);
      $("#scan-btn").disabled = false;
      return;
    }
    window.location.href = "/jobs/" + data.job_id;
  } catch (e) {
    status.className = "status error";
    status.textContent = "请求失败：" + e.message;
    $("#scan-btn").disabled = false;
  }
});

const demoBtn = document.getElementById("demo-btn");
if (demoBtn) {
  demoBtn.addEventListener("click", async () => {
    const status = $("#status");
    status.className = "status";
    status.textContent = "正在准备 Demo 测试集...";
    demoBtn.disabled = true;
    $("#scan-btn").disabled = true;
    try {
      const resp = await fetch("/api/demo", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) {
        status.className = "status error";
        status.textContent = "Demo 失败：" + (data.error || resp.status);
        demoBtn.disabled = false;
        $("#scan-btn").disabled = false;
        return;
      }
      status.textContent = "Demo 已启动，扫描目录: " + data.root;
      window.location.href = "/jobs/" + data.job_id;
    } catch (e) {
      status.className = "status error";
      status.textContent = "请求失败：" + e.message;
      demoBtn.disabled = false;
      $("#scan-btn").disabled = false;
    }
  });
}


// ----------------- 拖拽上传 -----------------

const dz = document.getElementById("dropzone");
const dzPickerDir = document.getElementById("dz-picker-dir");
const dzPickerFiles = document.getElementById("dz-picker-files");
const dzPickDirBtn = document.getElementById("dz-pick-dir");
const dzPickFilesBtn = document.getElementById("dz-pick-files");
const dzStatus = document.getElementById("dz-status");
const dzProgress = document.getElementById("dz-progress");
const dzBar = document.getElementById("dz-bar");
const dzProgressText = document.getElementById("dz-progress-text");

function dzSetStatus(text, isError) {
  if (!dzStatus) return;
  dzStatus.className = "status" + (isError ? " error" : "");
  dzStatus.textContent = text || "";
}

function dzSetBusy(on) {
  if (!dz) return;
  dz.classList.toggle("busy", !!on);
}

function dzSetProgress(loaded, total, label) {
  if (!dzProgress) return;
  dzProgress.classList.remove("hidden");
  const pct = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
  dzBar.style.width = pct + "%";
  if (label) {
    dzProgressText.textContent = label;
  } else {
    const mb = (n) => (n / 1024 / 1024).toFixed(1) + " MB";
    dzProgressText.textContent = `已上传 ${pct}%  (${mb(loaded)} / ${mb(total)})`;
  }
}

function dzResetProgress() {
  if (!dzProgress) return;
  dzProgress.classList.add("hidden");
  dzBar.style.width = "0%";
  dzProgressText.textContent = "";
}

// 递归读取一个 DataTransferItem entry，把里面所有支持的图片以 {file, path} 形式返回
function readEntry(entry, pathPrefix) {
  return new Promise((resolve) => {
    if (!entry) { resolve([]); return; }
    if (entry.isFile) {
      entry.file((file) => {
        if (isSupported(file.name)) {
          resolve([{ file, path: pathPrefix + file.name }]);
        } else {
          resolve([]);
        }
      }, () => resolve([]));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const readBatch = () => {
        reader.readEntries(async (entries) => {
          if (!entries.length) {
            resolve(all);
            return;
          }
          for (const child of entries) {
            const sub = await readEntry(child, pathPrefix + entry.name + "/");
            for (const item of sub) all.push(item);
          }
          readBatch();
        }, () => resolve(all));
      };
      readBatch();
    } else {
      resolve([]);
    }
  });
}

async function collectFromDataTransfer(dataTransfer) {
  const items = dataTransfer.items;
  const collected = [];
  if (items && items.length && typeof items[0].webkitGetAsEntry === "function") {
    const entries = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (it.kind === "file") entries.push(it.webkitGetAsEntry());
    }
    for (const ent of entries) {
      const sub = await readEntry(ent, "");
      for (const item of sub) collected.push(item);
    }
  } else if (dataTransfer.files && dataTransfer.files.length) {
    for (const f of dataTransfer.files) {
      if (isSupported(f.name)) collected.push({ file: f, path: f.name });
    }
  }
  return collected;
}

function uploadAndStart(items) {
  return new Promise((resolve, reject) => {
    if (!items.length) {
      reject(new Error("没有发现支持的图片文件（JPG/PNG/WebP/BMP/TIFF/GIF）"));
      return;
    }
    const fd = new FormData();
    let totalBytes = 0;
    for (const it of items) {
      fd.append("files", it.file, it.file.name);
      fd.append("paths", it.path);
      totalBytes += it.file.size;
    }
    fd.append("recursive", "true");
    fd.append("workers", "2");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/scan_upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        dzSetProgress(e.loaded, e.total);
      }
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else {
        reject(new Error(data.error || ("HTTP " + xhr.status)));
      }
    };
    xhr.onerror = () => reject(new Error("网络错误，上传失败"));
    dzSetProgress(0, totalBytes, `准备上传 ${items.length} 个文件，共约 ${(totalBytes / 1024 / 1024).toFixed(1)} MB`);
    xhr.send(fd);
  });
}

async function handleDroppedItems(items) {
  if (!items.length) {
    dzSetStatus("没有发现支持的图片文件（JPG/PNG/WebP/BMP/TIFF/GIF）", true);
    return;
  }
  dzSetBusy(true);
  dzSetStatus(`已读取 ${items.length} 个图片文件，开始上传到本机后端...`);
  try {
    const data = await uploadAndStart(items);
    const skipped = data.skipped ? `（跳过 ${data.skipped} 个不支持的文件）` : "";
    dzSetStatus(`上传完成，已成功收 ${data.uploaded} 个文件 ${skipped}，正在跳转到任务页...`);
    setTimeout(() => {
      window.location.href = "/jobs/" + data.job_id;
    }, 400);
  } catch (e) {
    dzSetStatus("失败：" + e.message, true);
    dzResetProgress();
  } finally {
    dzSetBusy(false);
  }
}

if (dz) {
  ["dragenter", "dragover"].forEach((evt) => {
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dz.classList.add("dragover");
    });
  });
  ["dragleave", "dragend"].forEach((evt) => {
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dz.classList.remove("dragover");
    });
  });
  dz.addEventListener("drop", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    dz.classList.remove("dragover");
    if (dz.classList.contains("busy")) return;
    dzSetStatus("正在读取拖入的内容...");
    try {
      const items = await collectFromDataTransfer(e.dataTransfer);
      await handleDroppedItems(items);
    } catch (err) {
      dzSetStatus("读取失败：" + err.message, true);
    }
  });
  // 用 capture 阶段拦截：只要点击的是 .dz-actions 内的按钮，根本不让 dz 自己的 click 监听跑。
  // 这样可以彻底避免"先弹文件夹选择，再弹多图选择"的双弹现象（事件冒泡 + 上一轮 stopPropagation
  // 来不及生效的情况）。
  dz.addEventListener("click", (e) => {
    const t = e.target;
    if (t && t.closest && t.closest(".dz-actions")) {
      // 命中按钮区域：直接放行给按钮自己的 handler 处理，dz 不参与
      return;
    }
    // 完全空白处点击：仅给文字提示，**不**再调用任何 picker
    if (dz.classList.contains("busy")) return;
    dzSetStatus("请点击下方按钮：「选择文件夹」或「选择多张图片」；也可以直接把文件夹拖进来。");
  });
  dz.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && !dz.classList.contains("busy") && dzPickerDir) {
      e.preventDefault();
      dzPickerDir.click();
    }
  });
}

// 检测当前浏览器是否真的支持 webkitdirectory：用一个临时 input 探测属性
function browserSupportsDirectoryPicker() {
  try {
    const probe = document.createElement("input");
    probe.type = "file";
    return ("webkitdirectory" in probe) || ("directory" in probe);
  } catch (_) {
    return false;
  }
}

const DIR_PICKER_OK = browserSupportsDirectoryPicker();
if (!DIR_PICKER_OK && dzPickDirBtn) {
  // 不支持的话，禁用"选择文件夹"按钮并改成提示文案，引导用户走"选择多张图片"
  dzPickDirBtn.disabled = true;
  dzPickDirBtn.title = "当前浏览器不支持文件夹选择，请用「选择多张图片」或直接把文件夹拖进来";
  dzPickDirBtn.style.opacity = "0.5";
  dzPickDirBtn.textContent = "选择文件夹（当前浏览器不支持）";
}

if (dzPickDirBtn) {
  dzPickDirBtn.addEventListener("click", (e) => {
    // stopImmediatePropagation 比 stopPropagation 更狠：连同同元素上其它 listener 也不再触发，
    // 防止任何顺序问题导致 dz 的 click 监听仍然被调用。
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if (dzPickDirBtn.disabled) return;
    if (!DIR_PICKER_OK) {
      dzSetStatus("当前浏览器不支持文件夹选择，请改用「选择多张图片」，或直接把文件夹拖进来。", true);
      return;
    }
    if (!dz.classList.contains("busy") && dzPickerDir) dzPickerDir.click();
  });
}

if (dzPickFilesBtn) {
  dzPickFilesBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if (!dz.classList.contains("busy") && dzPickerFiles) dzPickerFiles.click();
  });
}

if (dzPickerDir) {
  dzPickerDir.addEventListener("change", async () => {
    const files = Array.from(dzPickerDir.files || []);
    const items = files
      .filter((f) => isSupported(f.name))
      .map((f) => ({ file: f, path: f.webkitRelativePath || f.name }));
    if (!items.length) {
      dzSetStatus("没有发现支持的图片文件（JPG/PNG/WebP/BMP/TIFF/GIF）。如果系统没有打开'选择文件夹'对话框，请改用右侧「选择多张图片」。", true);
      dzPickerDir.value = "";
      return;
    }
    await handleDroppedItems(items);
    dzPickerDir.value = "";
  });
}

if (dzPickerFiles) {
  dzPickerFiles.addEventListener("change", async () => {
    const files = Array.from(dzPickerFiles.files || []);
    const items = files
      .filter((f) => isSupported(f.name))
      .map((f) => ({ file: f, path: f.name }));
    if (!items.length) {
      dzSetStatus("没有发现支持的图片文件（JPG/PNG/WebP/BMP/TIFF/GIF）", true);
      dzPickerFiles.value = "";
      return;
    }
    await handleDroppedItems(items);
    dzPickerFiles.value = "";
  });
}


// ----------------- SynthID 增强（方案 B：一键启用 reverse-SynthID 官方包） -----------------

const synthidSetupBtn = document.getElementById("synthid-setup-btn");
const synthidStatusBtn = document.getElementById("synthid-status-btn");
const synthidStatusEl = document.getElementById("synthid-status");
const synthidLogEl = document.getElementById("synthid-log");

let synthidPollTimer = null;
let synthidConfirmEl = null;

function renderSynthidStatus(data) {
  if (!synthidStatusEl) return;
  if (!data) {
    synthidStatusEl.className = "status";
    synthidStatusEl.textContent = "";
    return;
  }
  const pkg = data.package_installed ? "✅ 已安装" : "⬜ 未安装";
  const cb = data.codebook_present ? "✅ 已下载" : "⬜ 未下载";
  const tail = " （codebook 路径：" + (data.codebook_path || "-") + "）";
  let line = `官方 reverse-SynthID 包：${pkg}；codebook：${cb}${tail}`;
  let css = "status";
  // 从日志末尾几行嗅出"刚刚失败/异常"
  const recentLog = (data.log_tail || []).slice(-8).join("\n").toLowerCase();
  const finishedWithFailure =
    !data.running
    && (!data.package_installed || !data.codebook_present)
    && (recentLog.includes("命令失败")
      || recentLog.includes("异常")
      || recentLog.includes("失败")
      || recentLog.includes("error"));

  if (data.running) {
    line = "⏳ 正在后台安装 reverse-SynthID + 下载 codebook（约 220MB），请稍候…  " + line;
  } else if (data.package_installed && data.codebook_present) {
    line = "🎉 一切就绪！每张图的「AI 来源凭证」 tab 现在可以使用官方 reverse-SynthID 反推。" + tail;
  } else if (finishedWithFailure) {
    css = "status error";
    line = "❌ 上次安装失败：" + line + "  请查看下方日志的诊断提示，修复后再点「一键启用」重试。";
  }
  synthidStatusEl.className = css;
  synthidStatusEl.textContent = line;

  // 日志面板永远可见（哪怕暂时为空），避免按下后看上去"啥也没发生"
  if (synthidLogEl) {
    synthidLogEl.style.display = "block";
    const log = (data.log_tail || []).join("\n");
    synthidLogEl.textContent = log
      || (data.running
        ? "（安装刚刚启动，日志即将出现…）"
        : "（暂无安装日志。点击上方按钮可触发一键安装。）");
    synthidLogEl.scrollTop = synthidLogEl.scrollHeight;
  }
}

async function fetchSynthidStatus() {
  try {
    const resp = await fetch("/api/synthid_enhance/status");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    renderSynthidStatus(data);
    return data;
  } catch (e) {
    if (synthidStatusEl) {
      synthidStatusEl.className = "status error";
      synthidStatusEl.textContent = "状态查询失败：" + e.message;
    }
    return null;
  }
}

function startSynthidPolling() {
  if (synthidPollTimer) return;
  synthidPollTimer = setInterval(async () => {
    const data = await fetchSynthidStatus();
    if (!data || !data.running) {
      clearInterval(synthidPollTimer);
      synthidPollTimer = null;
      if (synthidSetupBtn) synthidSetupBtn.disabled = false;
    }
  }, 2000);
}

async function triggerSynthidSetup() {
  if (synthidSetupBtn) synthidSetupBtn.disabled = true;
  if (synthidStatusEl) {
    synthidStatusEl.className = "status";
    synthidStatusEl.textContent = "⏳ 正在请求后端启动安装…";
  }
  if (synthidLogEl) {
    synthidLogEl.style.display = "block";
    synthidLogEl.textContent = "（提交安装请求中…）";
  }
  try {
    const resp = await fetch("/api/synthid_enhance/setup", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || ("HTTP " + resp.status));
    renderSynthidStatus(data);
    startSynthidPolling();
  } catch (e) {
    if (synthidStatusEl) {
      synthidStatusEl.className = "status error";
      synthidStatusEl.textContent = "启动失败：" + e.message;
    }
    if (synthidSetupBtn) synthidSetupBtn.disabled = false;
  }
}

function showSynthidConfirm() {
  // IDE 内嵌 webview 对 window.confirm 兼容性差，改用内联确认 UI
  if (synthidConfirmEl) return;
  if (!synthidStatusEl) return;
  synthidConfirmEl = document.createElement("div");
  synthidConfirmEl.className = "synthid-confirm";
  synthidConfirmEl.innerHTML = `
    <div class="synthid-confirm-text">
      ⚠️ 即将执行：
      <code>pip install git+https://github.com/aloshdenny/reverse-SynthID.git</code>
      并下载约 <strong>220 MB</strong> codebook 到
      <code>artifacts/spectral_codebook_v4.npz</code>。<br>
      全部写入当前 Python 环境，仅在本机运行。是否继续？
    </div>
    <div class="synthid-confirm-actions">
      <button type="button" class="primary synthid-confirm-yes">确认安装</button>
      <button type="button" class="primary synthid-confirm-no" style="background:#888">取消</button>
    </div>
  `;
  synthidStatusEl.parentElement.insertBefore(synthidConfirmEl, synthidStatusEl);
  synthidConfirmEl.querySelector(".synthid-confirm-yes").addEventListener("click", async () => {
    synthidConfirmEl.remove();
    synthidConfirmEl = null;
    await triggerSynthidSetup();
  });
  synthidConfirmEl.querySelector(".synthid-confirm-no").addEventListener("click", () => {
    synthidConfirmEl.remove();
    synthidConfirmEl = null;
    if (synthidSetupBtn) synthidSetupBtn.disabled = false;
  });
}

if (synthidStatusBtn) {
  synthidStatusBtn.addEventListener("click", () => fetchSynthidStatus());
}

if (synthidSetupBtn) {
  synthidSetupBtn.addEventListener("click", async () => {
    // 先看一下当前后端状态：已经在跑就直接进入轮询
    const cur = await fetchSynthidStatus();
    if (cur && cur.running) {
      synthidSetupBtn.disabled = true;
      startSynthidPolling();
      return;
    }
    if (cur && cur.package_installed && cur.codebook_present) {
      // 已经装好，无需重复
      if (synthidStatusEl) {
        synthidStatusEl.className = "status";
        synthidStatusEl.textContent = "🎉 已经全部就绪，无需重复安装。";
      }
      return;
    }
    showSynthidConfirm();
  });
  fetchSynthidStatus();
}
