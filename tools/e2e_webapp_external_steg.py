"""End-to-end HTTP test for /api/scan_upload + external_steganalysis schema.

Stdlib only: urllib + hand-rolled multipart/form-data. No third-party deps.

Usage:
    python tools/e2e_webapp_external_steg.py --base-url http://127.0.0.1:5057
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]

IMAGES = [
    ROOT / "tools" / "test_images" / "normal_png.png",
    ROOT / "tools" / "test_images" / "ai_metadata.png",
    ROOT / "tools" / "test_images" / "lsb_steg.png",
    ROOT / "tools" / "test_images" / "trailing_zip.png",
    ROOT / "tools" / "test_images" / "ai_forged_copyright.jpg",
    ROOT / ".cache" / "datasets" / "genimage_mini" / "midjourney_oldtimer.png",
]


def _build_multipart(files: list[Path]) -> tuple[bytes, str]:
    """Build a multipart/form-data body containing files[] + paths[] entries.

    Mirrors how the browser drag-and-drop sends payloads to /api/scan_upload.
    """
    boundary = "----E2E" + uuid.uuid4().hex
    crlf = b"\r\n"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(b"--" + boundary.encode() + crlf)
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf
        )
        chunks.append(value.encode("utf-8") + crlf)

    def add_file(name: str, filename: str, payload: bytes, content_type: str) -> None:
        chunks.append(b"--" + boundary.encode() + crlf)
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
            + crlf
        )
        chunks.append(f"Content-Type: {content_type}".encode() + crlf + crlf)
        chunks.append(payload + crlf)

    # files[] + paths[] interleaved in upload order
    for p in files:
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        add_file("files", p.name, p.read_bytes(), ctype)
        add_field("paths", p.name)

    add_field("workers", "1")
    add_field("recursive", "true")

    chunks.append(b"--" + boundary.encode() + b"--" + crlf)
    body = b"".join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def http_request(
    url: str, *, method: str = "GET", body: bytes | None = None,
    content_type: str | None = None, timeout: float = 60.0,
) -> tuple[int, bytes, dict]:
    headers = {"Accept": "application/json, text/html"}
    if content_type:
        headers["Content-Type"] = content_type
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})


def upload(base_url: str, files: list[Path]) -> str:
    body, ctype = _build_multipart(files)
    status, raw, _ = http_request(
        f"{base_url}/api/scan_upload", method="POST", body=body,
        content_type=ctype, timeout=120.0,
    )
    if status != 200:
        raise RuntimeError(f"scan_upload failed: status={status} body={raw[:300]!r}")
    data = json.loads(raw.decode("utf-8"))
    if "job_id" not in data:
        raise RuntimeError(f"scan_upload missing job_id: {data}")
    return data["job_id"]


def poll_done(base_url: str, job_id: str, *, timeout_s: float = 300.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        status, raw, _ = http_request(f"{base_url}/api/jobs/{job_id}", timeout=10.0)
        if status != 200:
            raise RuntimeError(f"job status http={status}: {raw[:200]!r}")
        last = json.loads(raw.decode("utf-8"))
        s = last.get("status")
        if s == "done":
            return last
        if s == "error":
            raise RuntimeError(f"job error: {last.get('error')}")
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_s}s; last={last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:5057")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    # 0) sanity: every input image must exist
    missing = [p for p in IMAGES if not p.exists()]
    if missing:
        print(f"FAIL: missing inputs: {missing}")
        return 1

    print(f"[step 2] uploading {len(IMAGES)} files to {base}/api/scan_upload ...")
    job_id = upload(base, IMAGES)
    print(f"  job_id = {job_id}")

    print(f"[step 3] polling /api/jobs/{job_id} until status=done ...")
    job = poll_done(base, job_id)
    print(f"  done: total={job.get('total')} done={job.get('done')}")

    print(f"[step 4] fetching /api/jobs/{job_id}/summary ...")
    status, raw, _ = http_request(f"{base}/api/jobs/{job_id}/summary", timeout=15.0)
    if status != 200:
        print(f"FAIL: summary http={status}: {raw[:200]!r}")
        return 1
    summary = json.loads(raw.decode("utf-8"))
    results = summary.get("results") or []
    print(f"  summary.results count = {len(results)}")
    if len(results) != len(IMAGES):
        print(f"FAIL: expected {len(IMAGES)} results, got {len(results)}")
        return 1

    # 5) per-image report assertions
    failures: list[str] = []
    per_image_stats: list[dict] = []
    for r in results:
        out_dir = r.get("output_dir") or ""
        slug = os.path.basename(out_dir.rstrip("/\\"))
        img_name = os.path.basename(r.get("image_path") or "")
        print(f"[step 5] checking image {img_name} (slug={slug})")
        s, raw_rep, _ = http_request(
            f"{base}/api/jobs/{job_id}/image/{slug}/report", timeout=15.0
        )
        if s != 200:
            failures.append(f"{img_name}: report http={s}")
            continue
        report = json.loads(raw_rep.decode("utf-8"))
        ext = report.get("external_steganalysis")
        if ext is None:
            failures.append(f"{img_name}: external_steganalysis missing")
            per_image_stats.append({"image": img_name, "ok": False})
            continue
        risk = ext.get("risk_level")
        tools = ext.get("tools") or []
        tool_statuses = [t.get("tool_status") for t in tools]
        ok_risk = risk == "UNKNOWN"
        ok_len = len(tools) == 4
        ok_skipped = all(
            isinstance(st, str) and st.startswith("SKIPPED_") for st in tool_statuses
        )
        per_image_stats.append({
            "image": img_name,
            "slug": slug,
            "risk_level": risk,
            "tool_statuses": tool_statuses,
            "ok": ok_risk and ok_len and ok_skipped,
        })
        if not ok_risk:
            failures.append(f"{img_name}: risk_level={risk!r} != 'UNKNOWN'")
        if not ok_len:
            failures.append(f"{img_name}: tools length={len(tools)} != 4")
        if not ok_skipped:
            failures.append(
                f"{img_name}: tool_statuses={tool_statuses} not all SKIPPED_*"
            )

        # 6) image.html must contain "reverse-search-card"
        s2, html_raw, _ = http_request(
            f"{base}/jobs/{job_id}/image/{slug}", timeout=15.0
        )
        if s2 != 200:
            failures.append(f"{img_name}: image.html http={s2}")
        elif b"reverse-search-card" not in html_raw:
            failures.append(f"{img_name}: image.html missing 'reverse-search-card'")

    print()
    print("=" * 60)
    print("E2E SUMMARY")
    print("=" * 60)
    for s in per_image_stats:
        print(json.dumps(s, ensure_ascii=False))
    print("-" * 60)
    print(f"images_checked = {len(per_image_stats)}")
    print(f"images_passed  = {sum(1 for s in per_image_stats if s['ok'])}")
    print(f"images_failed  = {sum(1 for s in per_image_stats if not s['ok'])}")
    print(f"failure_count  = {len(failures)}")
    for f in failures:
        print(f"  - {f}")

    if failures:
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
