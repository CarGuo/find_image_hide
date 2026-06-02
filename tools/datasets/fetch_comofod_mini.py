"""Fetch a tiny CoMoFoD-style sample (copy-move forgery).

CoMoFoD (Tralic et al., IWSSIP 2013) is a public copy-move forgery
benchmark with 260 base images x ~5 transformations each (translate,
rotate, scale, JPEG, brightness...).  It's hosted at:

    https://www.vcl.fer.hr/comofod/comofod.html

The download is a single ~1.5 GB ZIP that we don't auto-fetch, and the
authors politely ask researchers not to hot-link individual sample files.

So this fetcher follows the same "soft pointer" pattern as
fetch_casia_v2_mini.py:

  * by default, just print the access URL and exit cleanly;
  * if ``COMOFOD_DIR`` env var points at a locally-extracted archive,
    copy up to 8 representative samples into ``.cache/datasets/comofod_mini``.

Citation::

    Tralic, D., Zupancic, I., Grgic, S., Grgic, M., 2013.
    CoMoFoD - New Database for Copy-Move Forgery Detection.
    Proc. 55th International Symposium ELMAR-2013.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from _common import cache_dir  # type: ignore[import-not-found]


def main() -> int:
    print("[comofod_mini] Official CoMoFoD download (~1.5 GB ZIP):")
    print("                https://www.vcl.fer.hr/comofod/comofod.html")
    print("[comofod_mini] No public mirror provided -- nothing downloaded.")

    custom = os.environ.get("COMOFOD_DIR")
    if custom:
        src = Path(custom)
        if src.is_dir():
            dst = cache_dir("comofod_mini")
            count = 0
            for fp in src.rglob("*"):
                if fp.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    target = dst / fp.name
                    if not target.exists():
                        shutil.copy2(fp, target)
                        count += 1
                    if count >= 8:
                        break
            print(f"[comofod_mini] copied {count} local samples from {src}")
        else:
            print(f"[comofod_mini] COMOFOD_DIR={src} is not a directory; skip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
