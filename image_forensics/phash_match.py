"""Perceptual-hash (pHash) match against a local reference library.

Use case: you have a folder of "known stock / paid / leaked" images. New
incoming images are compared against this library using a pHash; near
duplicates (Hamming distance <= threshold) are flagged regardless of
re-compression, slight crop, color shift, or resize.

This catches the *most common image-laundering* attack: take a stock
image, run a slight edit, and pretend it is original.

Backend: imagehash + Pillow. If imagehash is unavailable the module
degrades to status=PHASH_UNAVAILABLE.

Reference library is built lazily and cached at <reference_dir>/.phash_index.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

DEFAULT_THRESHOLD = 8        # Hamming distance for "very likely the same image"
SUSPICIOUS_THRESHOLD = 16    # 8..16 = "looks similar"

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}


def _imagehash_available():
    try:
        import imagehash  # type: ignore
        return imagehash
    except Exception:
        return None


def _list_images(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in _IMG_EXTS:
            out.append(p)
    return out


def _build_index(reference_dir: Path) -> dict[str, str]:
    """Compute (or load cached) {phash_hex: relative_path} for every image
    in reference_dir."""
    cache = reference_dir / ".phash_index.json"
    imagehash = _imagehash_available()
    if imagehash is None:
        return {}
    images = _list_images(reference_dir)
    cache_data: dict[str, dict[str, Any]] = {}
    if cache.exists():
        try:
            cache_data = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            cache_data = {}

    index: dict[str, str] = {}
    dirty = False
    for p in images:
        rel = str(p.relative_to(reference_dir))
        try:
            mtime = p.stat().st_mtime_ns
        except Exception:
            mtime = 0
        prior = cache_data.get(rel)
        if prior and prior.get("mtime") == mtime and prior.get("phash"):
            index[prior["phash"]] = rel
            continue
        try:
            with Image.open(p) as img:
                img.load()
                ph = str(imagehash.phash(img.convert("RGB")))
            cache_data[rel] = {"phash": ph, "mtime": mtime}
            index[ph] = rel
            dirty = True
        except Exception:
            continue
    if dirty:
        try:
            cache.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except Exception:
            pass
    return index


def _hamming(a: str, b: str) -> int:
    """Hamming distance between two hex pHash strings."""
    try:
        ai = int(a, 16)
        bi = int(b, 16)
        return bin(ai ^ bi).count("1")
    except Exception:
        return 64


def analyze_phash_match(path: Path, reference_dir: Path | None) -> dict[str, Any]:
    if reference_dir is None or not Path(reference_dir).is_dir():
        return {
            "status": "DISABLED",
            "risk_level": "LOW",
            "phash_score": 0.0,
            "matches": [],
            "evidence_items": [],
            "note": "phash_match disabled (no reference dir provided).",
        }
    imagehash = _imagehash_available()
    if imagehash is None:
        return {
            "status": "PHASH_UNAVAILABLE",
            "risk_level": "UNKNOWN",
            "phash_score": 0.0,
            "matches": [],
            "evidence_items": [],
            "note": "Install `imagehash` to enable perceptual-hash match (`pip install imagehash`).",
        }

    reference_dir = Path(reference_dir)
    try:
        index = _build_index(reference_dir)
    except Exception as exc:
        return {
            "status": "ERROR",
            "risk_level": "UNKNOWN",
            "phash_score": 0.0,
            "matches": [],
            "evidence_items": [],
            "error": f"index_build_failed: {exc}",
        }

    if not index:
        return {
            "status": "EMPTY_REFERENCE",
            "risk_level": "LOW",
            "phash_score": 0.0,
            "matches": [],
            "evidence_items": [],
            "note": f"No images found in reference directory: {reference_dir}",
        }

    try:
        with Image.open(path) as img:
            img.load()
            cand_ph = str(imagehash.phash(img.convert("RGB")))
    except Exception as exc:
        return {
            "status": "ERROR",
            "risk_level": "UNKNOWN",
            "phash_score": 0.0,
            "matches": [],
            "evidence_items": [],
            "error": f"hash_failed: {exc}",
        }

    matches: list[dict[str, Any]] = []
    try:
        cand_resolved = Path(path).resolve()
        ref_resolved = reference_dir.resolve()
    except Exception:
        cand_resolved = Path(path)
        ref_resolved = reference_dir
    for ref_ph, rel in index.items():
        # Skip self-match: if the candidate file lives inside the reference
        # directory or is byte-identical to a reference, distance=0 is not
        # informative.
        try:
            ref_full = (ref_resolved / rel).resolve()
            if ref_full == cand_resolved:
                continue
        except Exception:
            pass
        d = _hamming(cand_ph, ref_ph)
        if d <= SUSPICIOUS_THRESHOLD:
            matches.append({"reference": rel, "distance": d, "phash": ref_ph})
    matches.sort(key=lambda m: m["distance"])

    best = matches[0]["distance"] if matches else 64
    if best <= DEFAULT_THRESHOLD:
        risk = "HIGH"
        score = 1.0 - (best / 64.0)
    elif best <= SUSPICIOUS_THRESHOLD:
        risk = "MEDIUM"
        score = 0.5
    else:
        risk = "LOW"
        score = 0.0

    evidence_items: list[dict[str, Any]] = []
    for m in matches[:5]:
        evidence_items.append({
            "module": "phash_match",
            "severity": "warning" if m["distance"] <= DEFAULT_THRESHOLD else "info",
            "title": f"Near-duplicate of reference: {m['reference']}",
            "description": f"Hamming distance = {m['distance']} (<= {DEFAULT_THRESHOLD} considered the same image after laundering)",
            "confidence": round(1.0 - m["distance"] / 64.0, 3),
        })

    return {
        "status": "OK",
        "risk_level": risk,
        "phash_score": round(score, 3),
        "candidate_phash": cand_ph,
        "reference_dir": str(reference_dir),
        "reference_count": len(index),
        "matches": matches[:25],
        "best_distance": best,
        "default_threshold": DEFAULT_THRESHOLD,
        "evidence_items": evidence_items,
    }
