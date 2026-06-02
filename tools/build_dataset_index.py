"""Scan ``tools/test_images/`` and ``.cache/datasets/`` and emit a single
``dataset_index.json`` summarising every sample with its expected label.

The index is consumed by future regression scripts to:
  * iterate over a stable per-category sample list
  * assert "AI provenance must trip on ai_generated/*"
  * assert "no false positive on clean_real/*"
  * assert "phash match holds across social_laundered/*"

JSON shape::

    {
        "generated_at": "2026-06-02T...",
        "totals": { "test_images": 24, "datasets": 17, ... },
        "entries": [
            {
                "path": "tools/test_images/clean_real/canon_eos_landscape.jpg",
                "category": "clean_real",
                "source": "test_images",
                "size_bytes": 12345,
                "expected": {
                    "ai_generated": false,
                    "tampered": false,
                    "stego": false
                }
            },
            ...
        ]
    }

The index is regenerated each run; it lives at the project root and is
*not* gitignored -- it is small JSON and useful as a CI artefact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_IMAGES = PROJECT_ROOT / "tools" / "test_images"
DATASETS_CACHE = PROJECT_ROOT / ".cache" / "datasets"
INDEX_OUT = PROJECT_ROOT / "dataset_index.json"

# Category -> expected detector behaviour.  ``True`` means the named
# detector *should* fire on this category; ``False`` means it should NOT.
CATEGORY_EXPECTATIONS: dict[str, dict[str, bool]] = {
    # tools/test_images/<sub>
    "clean_real":         {"ai_generated": False, "tampered": False, "stego": False},
    "ai_generated":       {"ai_generated": True,  "tampered": False, "stego": False},
    "c2pa_signed":        {"ai_generated": False, "tampered": False, "stego": False},
    "format_zoo":         {"ai_generated": False, "tampered": False, "stego": False},
    "social_laundered":   {"ai_generated": False, "tampered": False, "stego": False},
    # .cache/datasets/<sub>
    "genimage_mini":      {"ai_generated": True,  "tampered": False, "stego": False},
    "chameleon_mini":     {"ai_generated": True,  "tampered": False, "stego": False},
    "casia_v2_mini":      {"ai_generated": False, "tampered": True,  "stego": False},
    "comofod_mini":       {"ai_generated": False, "tampered": True,  "stego": False},
}

LEGACY_EXPECTATION = {"ai_generated": False, "tampered": False, "stego": False}

VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff",
              ".gif", ".bmp", ".heic", ".heif", ".avif"}


def scan_root(root: Path, source: str) -> list[dict]:
    if not root.exists():
        return []
    rows: list[dict] = []
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in VALID_EXTS:
            continue
        try:
            rel = fp.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            rel = fp.as_posix()
        # Determine category: subdir name relative to root if any, else "flat".
        try:
            rel_to_root = fp.relative_to(root)
        except ValueError:
            continue
        parts = rel_to_root.parts
        category = parts[0] if len(parts) > 1 else "flat"
        expected = CATEGORY_EXPECTATIONS.get(category, LEGACY_EXPECTATION)
        rows.append({
            "path": rel,
            "category": category,
            "source": source,
            "size_bytes": fp.stat().st_size,
            "expected": dict(expected),
        })
    return rows


def main() -> int:
    test_rows = scan_root(TEST_IMAGES, source="test_images")
    cache_rows = scan_root(DATASETS_CACHE, source="datasets_cache")
    entries = test_rows + cache_rows

    by_category: dict[str, int] = {}
    for r in entries:
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "test_images": len(test_rows),
            "datasets_cache": len(cache_rows),
            "total": len(entries),
            "by_category": by_category,
        },
        "entries": entries,
    }
    INDEX_OUT.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {INDEX_OUT}  ({len(entries)} entries, {len(by_category)} categories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
