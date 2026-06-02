"""Fetch a tiny CASIA-v2 style sample (image splicing forgery).

CASIA Image Tampering Detection Evaluation Database v2.0 contains 7491
authentic + 5123 spliced images, but it's distributed only via an email
request to the National Lab of Pattern Recognition, China, and we are
not allowed to mirror or hot-link individual files.

Therefore this fetcher does **not** download anything by default; it
prints the access URL and exits cleanly so the regression keeps moving.
If you have your own legally-obtained CASIA-v2 archive, point us at it
via the ``CASIA_V2_DIR`` environment variable and the build_dataset_index
will pick the images up automatically.

Reference (gated)::

    Dong, J., Wang, W., Tan, T., 2013. CASIA Image Tampering Detection
    Evaluation Database. IEEE ChinaSIP 2013.
    Access form: http://forensics.idealtest.org/

For a fully open, redistribution-friendly splicing dataset, consider
``CoMoFoD`` (handled by ``fetch_comofod_mini.py``) or Columbia Uncomp.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from _common import cache_dir  # type: ignore[import-not-found]


def main() -> int:
    print("[casia_v2_mini] Official CASIA-v2 access (email request required):")
    print("                http://forensics.idealtest.org/")
    print("[casia_v2_mini] No public mirror is provided -- nothing downloaded.")

    # Honour optional CASIA_V2_DIR pointing at a locally-extracted archive.
    custom = os.environ.get("CASIA_V2_DIR")
    if custom:
        src = Path(custom)
        if src.is_dir():
            dst = cache_dir("casia_v2_mini")
            count = 0
            for fp in src.rglob("*"):
                if fp.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
                    target = dst / fp.name
                    if not target.exists():
                        shutil.copy2(fp, target)
                        count += 1
                    if count >= 8:
                        break
            print(f"[casia_v2_mini] copied {count} local samples from {src}")
        else:
            print(f"[casia_v2_mini] CASIA_V2_DIR={src} is not a directory; skip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
