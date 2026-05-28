"""Basic image information module."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import imagehash
from PIL import Image

from .utils import guess_mime, sha256_of_file


def collect_basic_info(path: Path) -> dict[str, Any]:
    path = Path(path)
    size_bytes = path.stat().st_size
    info: dict[str, Any] = {
        "file_name": path.name,
        "file_path": str(path),
        "file_size_bytes": int(size_bytes),
        "mime_type": guess_mime(path),
        "format": None,
        "width": 0,
        "height": 0,
        "mode": None,
        "channels": 0,
        "has_alpha": False,
        "sha256": sha256_of_file(path),
        "perceptual_hash": None,
    }
    try:
        with Image.open(path) as img:
            img.load()
            info["format"] = img.format
            info["width"], info["height"] = img.size
            info["mode"] = img.mode
            info["channels"] = len(img.getbands())
            info["has_alpha"] = "A" in img.getbands()
            try:
                phash = imagehash.phash(img.convert("RGB"))
                info["perceptual_hash"] = str(phash)
            except Exception:
                info["perceptual_hash"] = None
    except Exception as exc:
        info["error"] = f"basic_info_failed: {exc}"
    return info
