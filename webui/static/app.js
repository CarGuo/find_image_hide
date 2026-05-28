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
const dzPicker = document.getElementById("dz-picker");
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
  dz.addEventListener("click", () => {
    if (!dz.classList.contains("busy") && dzPicker) dzPicker.click();
  });
  dz.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && !dz.classList.contains("busy") && dzPicker) {
      e.preventDefault();
      dzPicker.click();
    }
  });
}

if (dzPicker) {
  dzPicker.addEventListener("change", async () => {
    const files = Array.from(dzPicker.files || []);
    const items = files
      .filter((f) => isSupported(f.name))
      .map((f) => ({ file: f, path: f.webkitRelativePath || f.name }));
    if (!items.length) {
      dzSetStatus("没有发现支持的图片文件（JPG/PNG/WebP/BMP/TIFF/GIF）", true);
      return;
    }
    await handleDroppedItems(items);
    dzPicker.value = "";
  });
}
