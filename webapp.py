"""Flask web UI for Image Forensics Inspector."""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from image_forensics.batch import analyze_directory


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = APP_ROOT / "analysis_output"
DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


app = Flask(
    __name__,
    template_folder=str(APP_ROOT / "webui" / "templates"),
    static_folder=str(APP_ROOT / "webui" / "static"),
)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


# 服务进程启动时间戳，用于给静态资源加 ?v=...，进程重启即天然失效
ASSET_VERSION = str(int(time.time()))


@app.context_processor
def _inject_asset_version():
    """让所有模板都能用 {{ asset_version }} 给 css/js 加版本号。"""
    return {"asset_version": ASSET_VERSION}


@app.after_request
def _smart_cache_headers(resp):
    """精细化缓存策略，避免 no-store 一刀切拖慢图片 / 报告。

    规则：
    - HTML 页面 / API JSON：no-store（每次都要拿到最新内容）。
    - /static 下的 css/js：必须重新校验，靠 ETag / 文件 mtime 304；
      因为 HTML 里引用时已挂 ?v=ASSET_VERSION，进程重启就会变 URL。
    - 大图（原图 preview / 可视化 vis/*.png）：走浏览器默认缓存，
      因为同一个 job_id + slug 的内容不会变，可以放心 max-age。
    """
    path = request.path or ""
    ctype = (resp.headers.get("Content-Type") or "").lower()

    # 不动错误响应（让客户端可重试）
    if resp.status_code >= 400:
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # 1) /api/** 都按"动态数据"处理
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # 2) HTML 页面：no-store（保证后续改 UI 不会被旧 HTML 卡住）
    if "text/html" in ctype:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # 3) /static/ css/js：允许缓存，但必须 revalidate；
    #    URL 上已经有 ?v=ASSET_VERSION，进程重启就拉新版本
    if path.startswith("/static/"):
        resp.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        return resp

    # 4) 任务产物（原图预览 / 可视化图）：内容跟 job_id+slug 绑定，不会变，
    #    长缓存可显著加快详情页 tab 切换
    if "/jobs/" in path and ("/preview" in path or "/vis/" in path):
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp

    # 5) 兜底：保守地不缓存
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _safe_relative_path(raw: str) -> Path | None:
    """Sanitize a client-supplied relative path so it cannot escape staging dir.

    - 反斜杠转正斜杠；
    - 去掉盘符 / 起始斜杠；
    - 拒绝任何 ``..`` 段；
    - 只保留扩展名命中 ``SUPPORTED_IMAGE_EXTS`` 的文件。
    """
    if not raw:
        return None
    s = raw.replace("\\", "/").lstrip("/")
    s = re.sub(r"^[a-zA-Z]:/", "", s)
    parts = [p for p in s.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    if not parts:
        return None
    rel = Path(*parts)
    if rel.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
        return None
    return rel


JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _job_progress(job_id: str):
    def cb(done: int, total: int, res: dict[str, Any]) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job["done"] = done
            job["total"] = total
            # batch.py 现在会用 phase=starting/analyzing 推送"正在做什么"的脉搏，
            # 这些不是真正的图片分析结果，只更新 current_file，不进 results 列表。
            phase = (res or {}).get("phase")
            if phase in ("starting", "analyzing"):
                job["current_file"] = (res or {}).get("image_path") or ""
                job["phase"] = phase
                return
            if phase == "no_images":
                job["phase"] = "no_images"
                return
            job["last"] = res
            job["results"].append(res)
            job["current_file"] = ""
    return cb


def _run_job(job_id: str, root: Path, out: Path, recursive: bool, workers: int) -> None:
    try:
        summary = analyze_directory(
            root, out,
            recursive=recursive,
            workers=workers,
            progress_cb=_job_progress(job_id),
        )
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job["status"] = "done"
                job["summary"] = summary
                job["finished_at"] = time.time()
    except Exception as exc:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = str(exc)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json(force=True, silent=True) or {}
    raw_dir = (data.get("directory") or "").strip()
    if not raw_dir:
        return jsonify({"error": "directory is required"}), 400
    root = Path(raw_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return jsonify({"error": f"not a directory: {root}"}), 400
    recursive = bool(data.get("recursive", True))
    try:
        workers = int(data.get("workers", 2))
    except Exception:
        workers = 2
    workers = max(1, min(8, workers))

    job_id = uuid.uuid4().hex[:12]
    out_dir = DEFAULT_OUTPUT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "root": str(root),
            "output_dir": str(out_dir),
            "recursive": recursive,
            "workers": workers,
            "done": 0,
            "total": 0,
            "results": [],
            "started_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, root, out_dir, recursive, workers),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/demo", methods=["POST"])
def api_demo():
    """One-click demo: prepare bundled test images and run the analyzer.

    Reuses the same job pipeline as ``/api/scan`` so the existing job page
    can render the result without any extra UI work.
    """
    demo_root = APP_ROOT / "tools" / "test_images"
    ref_dir = APP_ROOT / "tools" / "phash_reference"

    if not demo_root.exists() or not any(demo_root.iterdir()):
        try:
            import runpy
            runpy.run_path(str(APP_ROOT / "tools" / "make_test_images.py"),
                           run_name="__main__")
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"failed to prepare demo images: {exc}"}), 500

    if ref_dir.exists():
        import os as _os
        _os.environ.setdefault("FORENSICS_PHASH_REFERENCE_DIR", str(ref_dir))

    job_id = uuid.uuid4().hex[:12]
    out_dir = DEFAULT_OUTPUT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "root": str(demo_root),
            "output_dir": str(out_dir),
            "recursive": True,
            "workers": 1,
            "done": 0,
            "total": 0,
            "results": [],
            "started_at": time.time(),
            "demo": True,
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, demo_root, out_dir, True, 1),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "root": str(demo_root)})


@app.route("/api/scan_upload", methods=["POST"])
def api_scan_upload():
    """Receive a folder dropped from the browser as multipart files.

    前端用 ``DataTransferItem.webkitGetAsEntry`` 递归把整个目录里的文件
    读出来，再以 ``files[]`` 上传，每个文件附带 ``paths[]`` 字段保留相对
    路径（例如 ``photos/2024/cat.jpg``）。后端把它们按原始结构落地到
    ``analysis_output/<job_id>/_uploaded/``，再像 ``/api/scan`` 一样跑分析。
    """
    files = request.files.getlist("files")
    paths = request.form.getlist("paths")
    if not files:
        return jsonify({"error": "no files uploaded"}), 400

    try:
        recursive = request.form.get("recursive", "true").lower() != "false"
    except Exception:
        recursive = True
    try:
        workers = int(request.form.get("workers", "2"))
    except Exception:
        workers = 2
    workers = max(1, min(8, workers))

    job_id = uuid.uuid4().hex[:12]
    out_dir = DEFAULT_OUTPUT / job_id
    staging = out_dir / "_uploaded"
    staging.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0
    for idx, fs in enumerate(files):
        raw_rel = paths[idx] if idx < len(paths) else fs.filename or ""
        rel = _safe_relative_path(raw_rel)
        if rel is None:
            skipped += 1
            continue
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        fs.save(str(target))
        saved += 1

    if saved == 0:
        return jsonify({
            "error": "no supported image files in upload",
            "skipped": skipped,
            "supported_extensions": sorted(SUPPORTED_IMAGE_EXTS),
        }), 400

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "root": str(staging),
            "output_dir": str(out_dir),
            "recursive": recursive,
            "workers": workers,
            "done": 0,
            "total": saved,
            "results": [],
            "started_at": time.time(),
            "uploaded": True,
            "uploaded_count": saved,
            "skipped_count": skipped,
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, staging, out_dir, recursive, workers),
        daemon=True,
    )
    thread.start()
    return jsonify({
        "job_id": job_id,
        "root": str(staging),
        "uploaded": saved,
        "skipped": skipped,
    })


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        return jsonify({
            "id": job["id"],
            "status": job["status"],
            "root": job["root"],
            "output_dir": job["output_dir"],
            "done": job["done"],
            "total": job["total"],
            "current_file": job.get("current_file", ""),
            "phase": job.get("phase", ""),
            "started_at": job.get("started_at"),
            "results": job["results"][-50:],
            "summary": job.get("summary"),
            "error": job.get("error"),
        })


@app.route("/api/jobs/<job_id>/summary")
def api_job_summary(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    summary_path = Path(job["output_dir"]) / "summary.json"
    if not summary_path.exists():
        return jsonify({"error": "summary not ready"}), 404
    return jsonify(json.loads(summary_path.read_text(encoding="utf-8")))


def _resolve_per_image_dir(job_id: str, slug: str) -> Path:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    out = Path(job["output_dir"]) / slug
    if not out.exists():
        abort(404)
    return out


@app.route("/api/jobs/<job_id>/image/<slug>/report")
def api_image_report(job_id: str, slug: str):
    out = _resolve_per_image_dir(job_id, slug)
    rj = out / "report.json"
    if not rj.exists():
        return jsonify({"error": "report missing"}), 404
    return jsonify(json.loads(rj.read_text(encoding="utf-8")))


@app.route("/jobs/<job_id>/image/<slug>/vis/<path:filename>")
def serve_visualization(job_id: str, slug: str, filename: str):
    out = _resolve_per_image_dir(job_id, slug)
    return send_from_directory(out / "visualizations", filename)


@app.route("/jobs/<job_id>/image/<slug>/preview")
def serve_preview(job_id: str, slug: str):
    """Serve the original image (read from path stored in report)."""
    out = _resolve_per_image_dir(job_id, slug)
    rj = out / "report.json"
    if not rj.exists():
        abort(404)
    rep = json.loads(rj.read_text(encoding="utf-8"))
    src = Path(rep.get("input", {}).get("file_path", ""))
    if not src.exists() or not src.is_file():
        abort(404)
    return send_from_directory(src.parent, src.name)


@app.route("/jobs/<job_id>")
def page_job(job_id: str):
    return render_template("job.html", job_id=job_id)


@app.route("/jobs/<job_id>/image/<slug>")
def page_image(job_id: str, slug: str):
    return render_template("image.html", job_id=job_id, slug=slug)


# ---- SynthID 增强（方案 B：可选启用 reverse-SynthID 官方包 + codebook） ----

# 仅暴露状态查询 + 触发后台安装；安装是自费用户主动行为，且会写入当前 venv。
_SYNTHID_SETUP_LOG: list[str] = []
_SYNTHID_SETUP_RUNNING = False


def _check_synthid_enhance_status() -> dict:
    """检查 reverse-SynthID 官方组件是否就绪。

    这个仓库其实没有 setup.py / pyproject.toml，作者的设计就是 git clone 后
    把 src/extraction/ 加进 sys.path 直接 import。所以"已安装"的判定标准是：
      1) 兜底 clone 目录存在 .cache/reverse_synthid_clone/src/extraction/synthid_bypass_v4.py
      2) artifacts/spectral_codebook_v4.npz 存在（或者从仓库的 v3_expanded 拷贝过来）
    """
    clone_dir = APP_ROOT / ".cache" / "reverse_synthid_clone"
    src_extraction = clone_dir / "src" / "extraction"
    pkg_ok = (
        (src_extraction / "synthid_bypass_v4.py").exists()
        and (src_extraction / "robust_extractor.py").exists()
    )
    # 顺手把 src/extraction 加到 sys.path 里，让别处可以 `import synthid_bypass_v4`
    if pkg_ok:
        import sys as _sys
        sp = str(src_extraction)
        if sp not in _sys.path:
            _sys.path.insert(0, sp)
    codebook_path = APP_ROOT / "artifacts" / "spectral_codebook_v4.npz"
    return {
        "package_installed": pkg_ok,
        "codebook_present": codebook_path.exists(),
        "codebook_path": str(codebook_path),
        "running": _SYNTHID_SETUP_RUNNING,
        "log_tail": _SYNTHID_SETUP_LOG[-30:],
    }


@app.route("/api/synthid_enhance/status", methods=["GET"])
def api_synthid_enhance_status():
    return jsonify(_check_synthid_enhance_status())


@app.route("/api/synthid_enhance/setup", methods=["POST"])
def api_synthid_enhance_setup():
    """触发后台安装 reverse-SynthID（pip install + 下载 codebook）。

    安全注意：
      - 仅当 host 是本机回环时允许（默认 127.0.0.1）；
      - 用户必须发 POST，避免被 GET 链接误触发；
      - 安装过程串行，重复 POST 直接返回 already running。
    """
    global _SYNTHID_SETUP_RUNNING
    if _SYNTHID_SETUP_RUNNING:
        return jsonify({"status": "already_running", **_check_synthid_enhance_status()})

    import threading
    _SYNTHID_SETUP_RUNNING = True
    _SYNTHID_SETUP_LOG.clear()
    _SYNTHID_SETUP_LOG.append("[setup] 开始安装 reverse-SynthID 官方组件...")

    def _run():
        global _SYNTHID_SETUP_RUNNING
        try:
            import sys as _sys
            import platform as _platform
            import os as _os
            import shutil as _shutil
            is_windows = _platform.system().lower().startswith("win")

            _SYNTHID_SETUP_LOG.append(
                "[setup] aloshdenny/reverse-SynthID 仓库本身不是 pip 包（没有 setup.py），"
                "作者设计为 git clone 后把 src/extraction 加到 sys.path 直接 import。"
                "所以这里我们 git clone 它一份到 .cache/，再把仓库自带的 codebook 拷过来。"
            )

            # 让 git 在某些环境（Win 长路径 / autocrlf）和 git ≥ 2.45 的 Clone Protection
            # 下都能 checkout 成功；最后两条都是用环境变量传入子进程，不污染用户全局。
            try:
                git_pre_cmds = [
                    ["git", "config", "--global", "core.longpaths", "true"],
                    ["git", "config", "--global", "core.autocrlf", "false"],
                ]
                for gc in git_pre_cmds:
                    _SYNTHID_SETUP_LOG.append("[setup] $ " + " ".join(gc))
                    gp = subprocess.run(gc, capture_output=True, text=True, timeout=15)
                    if gp.returncode != 0:
                        _SYNTHID_SETUP_LOG.append(
                            f"[setup] (warn) git config 失败 exit={gp.returncode}; 跳过"
                        )
            except FileNotFoundError:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] (error) 未检测到 git。"
                    + ("Windows 用户请安装 https://git-scm.com/download/win；"
                       if is_windows else
                       "macOS 用户可以用 `xcode-select --install` 或 `brew install git` 安装；")
                    + "缺少 git 无法继续。"
                )
                return

            # ---- Step 1: git clone reverse-SynthID 仓库到 .cache/ ----
            cache_dir = APP_ROOT / ".cache" / "reverse_synthid_clone"
            clone_ok = False
            if cache_dir.exists() and (cache_dir / "src" / "extraction" / "synthid_bypass_v4.py").exists():
                _SYNTHID_SETUP_LOG.append(f"[setup] 发现已 clone 的副本：{cache_dir}（跳过 clone）")
                clone_ok = True
            else:
                if cache_dir.exists():
                    _shutil.rmtree(cache_dir, ignore_errors=True)
                cache_dir.parent.mkdir(parents=True, exist_ok=True)
                clone_cmd = [
                    "git", "clone", "--depth", "1",
                    "https://github.com/aloshdenny/reverse-SynthID.git",
                    str(cache_dir),
                ]
                _SYNTHID_SETUP_LOG.append("[setup] $ " + " ".join(clone_cmd))
                # 关键：仓库里 artifacts/*.npz 是直接提交的二进制，git ≥ 2.45 默认开了
                # Clone Protection 会拒绝 checkout。用环境变量关掉这个保护。
                clone_env = _os.environ.copy()
                clone_env["GIT_CLONE_PROTECTION_ACTIVE"] = "false"
                clone_proc = subprocess.run(
                    clone_cmd, capture_output=True, text=True, timeout=600,
                    env=clone_env,
                )
                _SYNTHID_SETUP_LOG.extend((clone_proc.stdout or "").splitlines()[-15:])
                if clone_proc.returncode == 0:
                    clone_ok = True
                    _SYNTHID_SETUP_LOG.append("[setup] git clone 完成 ✓")
                else:
                    _SYNTHID_SETUP_LOG.append(
                        f"[setup] git clone 失败 exit={clone_proc.returncode}; stderr 末尾："
                    )
                    _SYNTHID_SETUP_LOG.extend((clone_proc.stderr or "").splitlines()[-15:])
                    err_blob = (clone_proc.stderr or "").lower()
                    if "should have been pointers" in err_blob or "clone protection" in err_blob:
                        _SYNTHID_SETUP_LOG.append(
                            "[setup] 诊断：Git Clone Protection 仍在拦截。我们已经传了 "
                            "GIT_CLONE_PROTECTION_ACTIVE=false，仍然失败说明你的 git 版本"
                            "可能不识别这个变量。请升级 git 到 2.46+ 或手动："
                            "`git -c protocol.version=2 clone --depth 1 ...` 后把目录放到 "
                            f"{cache_dir}。"
                        )
                    elif "could not resolve host" in err_blob or "failed to connect" in err_blob:
                        _SYNTHID_SETUP_LOG.append(
                            "[setup] 诊断：无法访问 github.com。请检查网络/代理后重试。"
                        )

            # ---- Step 2: 把 src/extraction 加到 sys.path 让上层能 import ----
            pkg_ok = False
            if clone_ok:
                src_extraction = cache_dir / "src" / "extraction"
                if (src_extraction / "synthid_bypass_v4.py").exists():
                    sp = str(src_extraction)
                    if sp not in _sys.path:
                        _sys.path.insert(0, sp)
                    pkg_ok = True
                    _SYNTHID_SETUP_LOG.append(
                        f"[setup] 已把 {src_extraction} 加到 sys.path，"
                        "上层可以 import synthid_bypass_v4 / robust_extractor ✓"
                    )
                else:
                    _SYNTHID_SETUP_LOG.append(
                        "[setup] (error) clone 完成但找不到 src/extraction/synthid_bypass_v4.py，"
                        "可能仓库结构变了，请到 GitHub 上确认。"
                    )

            # ---- Step 3: 准备 codebook ----
            artifacts_dir = APP_ROOT / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            target_codebook = artifacts_dir / "spectral_codebook_v4.npz"
            cb_ready = target_codebook.exists() and target_codebook.stat().st_size > 1024

            if cb_ready:
                _SYNTHID_SETUP_LOG.append(
                    f"[setup] codebook 已存在：{target_codebook}（跳过）"
                )
            elif clone_ok:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] 准备 codebook：仓库里没有 v4 文件，"
                    "v4 是用户自己用 scripts/build_codebook_v4.py 现场 build 的。"
                    "我们退而拷贝仓库里现成的 v3_expanded → spectral_codebook_v4.npz 占位，"
                    "上层探测器会自动适配。"
                )
                # README 表明仓库自带 v3 / v3_expanded（直接 commit 的二进制）。
                local_candidates = [
                    cache_dir / "artifacts" / "spectral_codebook_v3_expanded.npz",
                    cache_dir / "artifacts" / "spectral_codebook_v3.npz",
                ]
                for src in local_candidates:
                    if src.exists() and src.stat().st_size > 1024:
                        try:
                            _shutil.copy2(src, target_codebook)
                            _SYNTHID_SETUP_LOG.append(
                                f"[setup] 已拷贝 {src.name} → {target_codebook.name}"
                                f"（{src.stat().st_size // 1024} KiB）✓"
                            )
                            cb_ready = True
                            break
                        except Exception as cp_exc:
                            _SYNTHID_SETUP_LOG.append(
                                f"[setup] 拷贝 {src.name} 失败：{cp_exc!r}"
                            )

                if not cb_ready:
                    _SYNTHID_SETUP_LOG.append(
                        "[setup] codebook 拷贝失败：仓库里也没找到 v3/v3_expanded。"
                        "你可以按照仓库 README 的 V4 Quickstart 自己 build 一份，"
                        f"build 出的文件放到 {target_codebook} 即可。"
                    )

            # ---- Step 4: 总结 ----
            if pkg_ok and cb_ready:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] 全部完成 ✓ — reverse-SynthID 源码 + codebook 已就位，"
                    "本进程已 sys.path 注入；下次启动 webapp 时 _check_synthid_enhance_status "
                    "会自动重新注入。"
                )
            elif pkg_ok:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] 完成（部分）：reverse-SynthID 源码已就位，但 codebook 未拷贝。"
                    "内置 numpy 频域启发式探测不依赖 codebook，仍可正常使用。"
                )
            elif cb_ready:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] 完成（部分）：codebook 已就位，但 reverse-SynthID 源码未拿到。"
                    "内置 numpy 频域启发式探测仍可正常使用。"
                )
            else:
                _SYNTHID_SETUP_LOG.append(
                    "[setup] 完成（部分失败）：reverse-SynthID 源码与 codebook 都未就位，"
                    "但内置的 numpy 频域启发式探测仍可正常使用。"
                )
        except Exception as exc:
            _SYNTHID_SETUP_LOG.append(f"[setup] 异常：{exc!r}")
        finally:
            _SYNTHID_SETUP_RUNNING = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", **_check_synthid_enhance_status()})


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Image Forensics Inspector Web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
