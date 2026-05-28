"""Flask web UI for Image Forensics Inspector."""
from __future__ import annotations

import json
import re
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
            job["last"] = res
            job["results"].append(res)
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
