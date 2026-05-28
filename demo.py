"""One-click demo runner for Image Forensics Inspector.

Usage:
    python demo.py                # prepare data + run analysis on tools/test_images
    python demo.py --serve        # also start the Flask Web UI and open the browser
    python demo.py --no-download  # skip the network step (use only synthetic samples)
    python demo.py --port 5050    # custom port for --serve

The demo prepares a deterministic test corpus, runs the batch analyzer,
and prints both a CLI summary table and the URL to inspect each image
in the Web UI.  Cross-platform: works on Windows + macOS + Linux.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# --- helpers ----------------------------------------------------------------

def _hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _run_module(mod_path: str) -> None:
    """Run another script from this repo as if it were ``python <mod_path>``."""
    import runpy
    runpy.run_path(str(ROOT / mod_path), run_name="__main__")


# --- demo phases ------------------------------------------------------------

def step_prepare_images(skip_download: bool) -> Path:
    images_dir = ROOT / "tools" / "test_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if not skip_download:
        _hr("[1/4] Downloading real-world demo images")
        try:
            _run_module("tools/download_test_images.py")
        except SystemExit:
            pass
        except Exception as exc:
            print(f"  (download skipped due to error: {exc})")
    else:
        _hr("[1/4] Skipping download (--no-download)")

    _hr("[2/4] Generating synthetic + copyright-laundered samples")
    _run_module("tools/make_test_images.py")
    return images_dir


def step_run_analysis(images_dir: Path) -> tuple[Path, dict]:
    out_dir = ROOT / "analysis_output" / "demo_run"
    if out_dir.exists():
        # keep previous output but always overwrite summary
        pass
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_dir = ROOT / "tools" / "phash_reference"
    if ref_dir.exists():
        os.environ["FORENSICS_PHASH_REFERENCE_DIR"] = str(ref_dir)

    _hr("[3/4] Running batch forensic analysis")
    print(f"  input : {images_dir}")
    print(f"  output: {out_dir}")
    print(f"  phash_reference: {os.environ.get('FORENSICS_PHASH_REFERENCE_DIR', '(none)')}")
    print()

    from image_forensics.batch import analyze_directory  # imported here so env var is set

    def _cb(done: int, total: int, res: dict) -> None:
        rl = res.get("risk_level") or ("ERROR" if not res.get("ok") else "?")
        name = Path(res.get("image_path", "")).name
        print(f"  [{done:>2}/{total}] {name:<40s} -> {rl}")

    summary = analyze_directory(
        images_dir, out_dir, recursive=True, workers=1, progress_cb=_cb,
    )
    return out_dir, summary


def step_print_report(out_dir: Path, summary: dict) -> None:
    _hr("[4/4] Demo run complete")
    stats = summary.get("stats", {})
    print(f"  Total images analysed : {summary.get('total', 0)}")
    print(f"  Risk breakdown        : {stats.get('risk_counts', {})}")
    print(f"  Errors                : {stats.get('errors', 0)}")
    print(f"  Summary JSON          : {out_dir / 'summary.json'}")
    print()
    print("  Per-image reports (top-level):")
    for r in summary.get("results", [])[:20]:
        if not r.get("ok"):
            continue
        per = Path(r["output_dir"])
        print(f"    - {Path(r['image_path']).name:<40s}  -> {per / 'report.json'}")


# --- optional Flask launcher ------------------------------------------------

def step_serve(port: int, open_browser: bool) -> None:
    _hr("[bonus] Launching Web UI")
    from webapp import app  # noqa: WPS433  -- intentional late import

    url = f"http://127.0.0.1:{port}/"
    print(f"  Web UI  : {url}")
    print(f"  Tip     : paste tools/test_images path or click the demo button on the home page")
    print(f"  Stop    : Ctrl+C")

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open_new_tab(url)).start()

    # Disable reloader so it works in subprocess on Windows
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


# --- entry ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="One-click demo for Image Forensics Inspector")
    p.add_argument("--no-download", action="store_true",
                   help="Skip downloading real-world images (use only synthetic ones)")
    p.add_argument("--serve", action="store_true",
                   help="After preparing the demo, start the Flask Web UI")
    p.add_argument("--no-browser", action="store_true",
                   help="When --serve is on, do not auto-open the browser")
    p.add_argument("--port", type=int, default=5050,
                   help="Web UI port (default: 5050)")
    args = p.parse_args(argv)

    t0 = time.time()
    images_dir = step_prepare_images(args.no_download)
    out_dir, summary = step_run_analysis(images_dir)
    step_print_report(out_dir, summary)
    print(f"\n  Elapsed: {time.time() - t0:.1f}s")

    if args.serve:
        step_serve(args.port, open_browser=not args.no_browser)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
