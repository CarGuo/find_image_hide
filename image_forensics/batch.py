"""Batch directory analyzer with concurrency."""
from __future__ import annotations

import hashlib
import json
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .analyzer import analyze_image
from .utils import iter_images


def _slug_for_image(image_path: Path, root: Path) -> str:
    try:
        rel = image_path.resolve().relative_to(root.resolve())
        rel_str = rel.as_posix()
    except Exception:
        rel_str = image_path.name
    h = hashlib.sha1(str(image_path.resolve()).encode("utf-8")).hexdigest()[:10]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in rel_str)
    return f"{safe}__{h}"


def _analyze_one(args: tuple[str, str]) -> dict[str, Any]:
    image_path, output_dir = args
    try:
        report = analyze_image(image_path, output_dir)
        ext = report.get("extraction", {}) or {}
        steg = report.get("steganalysis", {}) or {}
        return {
            "image_path": image_path,
            "output_dir": output_dir,
            "ok": True,
            "risk_level": report.get("overall", {}).get("risk_level"),
            "confidence": report.get("overall", {}).get("confidence"),
            "summary": report.get("overall", {}).get("summary"),
            "format": report.get("input", {}).get("format"),
            "width": report.get("input", {}).get("width"),
            "height": report.get("input", {}).get("height"),
            "sha256": report.get("input", {}).get("sha256"),
            "ai_status": report.get("ai_provenance", {}).get("status"),
            "module_scores": report.get("overall", {}).get("module_scores", {}),
            "extraction_findings": {
                "trailing_bytes": (ext.get("trailing_data") or {}).get("trailing_bytes", 0),
                "trailing_magics": [m["format"] for m in (ext.get("trailing_data") or {}).get("magic_in_trailing", [])],
                "lsb_streams": len(ext.get("lsb_streams_with_findings") or []),
            },
            "steg_findings": {
                "chi_square_p": steg.get("chi_square_max_p_embed", 0.0),
                "spa_rate": steg.get("spa_max_embedding_rate", 0.0),
            },
        }
    except Exception as exc:
        return {
            "image_path": image_path,
            "output_dir": output_dir,
            "ok": False,
            "error": f"{exc}\n{traceback.format_exc()}",
        }


def analyze_directory(
    root_dir: str | Path,
    output_dir: str | Path,
    recursive: bool = True,
    workers: int = 2,
    progress_cb: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    root_dir = Path(root_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = list(iter_images(root_dir, recursive=recursive))
    total = len(images)

    tasks = []
    for img in images:
        slug = _slug_for_image(img, root_dir)
        per_out = output_dir / slug
        per_out.mkdir(parents=True, exist_ok=True)
        tasks.append((str(img), str(per_out)))

    results: list[dict[str, Any]] = []
    if total == 0:
        summary = {
            "tool_name": "Image Forensics Inspector",
            "schema_version": "0.1.0",
            "root_dir": str(root_dir),
            "output_dir": str(output_dir),
            "recursive": recursive,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total": 0,
            "results": [],
            "stats": {},
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_analyze_one, t): t for t in tasks}
            done = 0
            for fut in as_completed(futures):
                res = fut.result()
                done += 1
                results.append(res)
                if progress_cb:
                    progress_cb(done, total, res)
    else:
        done = 0
        for t in tasks:
            res = _analyze_one(t)
            done += 1
            results.append(res)
            if progress_cb:
                progress_cb(done, total, res)

    risk_counts: dict[str, int] = {}
    for r in results:
        rl = r.get("risk_level") or ("ERROR" if not r.get("ok") else "UNKNOWN")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1

    summary = {
        "tool_name": "Image Forensics Inspector",
        "schema_version": "0.1.0",
        "root_dir": str(root_dir),
        "output_dir": str(output_dir),
        "recursive": recursive,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "results": results,
        "stats": {
            "risk_counts": risk_counts,
            "errors": sum(1 for r in results if not r.get("ok")),
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
