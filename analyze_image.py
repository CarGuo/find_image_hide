"""Command-line entry point.

Usage:
    python analyze_image.py --input <image-or-dir> --output <out-dir> [--recursive] [--workers N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from image_forensics.analyzer import analyze_image
from image_forensics.batch import analyze_directory
from image_forensics.utils import is_supported_image


def main() -> int:
    p = argparse.ArgumentParser(description="Image Forensics Inspector CLI")
    p.add_argument("--input", required=True, help="Input image file or directory")
    p.add_argument("--output", required=True, help="Output directory")
    p.add_argument("--recursive", action="store_true", help="Recurse into subdirectories")
    p.add_argument("--workers", type=int, default=2, help="Worker processes for batch mode")
    args = p.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if inp.is_file() and is_supported_image(inp):
        report = analyze_image(inp, out)
        print(json.dumps({
            "report": str((out / "report.json").resolve()),
            "risk_level": report.get("overall", {}).get("risk_level"),
            "confidence": report.get("overall", {}).get("confidence"),
        }, indent=2))
        return 0

    if inp.is_dir():
        def cb(done: int, total: int, res: dict) -> None:
            print(f"[{done}/{total}] {res.get('image_path')} -> {res.get('risk_level') or 'ERROR'}", flush=True)

        summary = analyze_directory(
            inp, out,
            recursive=args.recursive,
            workers=max(1, args.workers),
            progress_cb=cb,
        )
        print(json.dumps({
            "summary": str((out / "summary.json").resolve()),
            "total": summary.get("total"),
            "stats": summary.get("stats"),
        }, indent=2))
        return 0

    print(f"Input not a supported image or directory: {inp}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
