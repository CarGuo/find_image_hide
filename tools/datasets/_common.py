"""Helpers shared by ``tools/datasets/fetch_*_mini.py``.

The mini-fetchers are intentionally lightweight: each pulls 5-10 example
files, just enough to **demonstrate** the dataset's content and feed our
regression harness.  The real datasets (CASIA, CoMoFoD, GenImage,
Chameleon) require either email access requests, Kaggle API keys, or
multi-GB downloads -- none of which we want in a clean checkout.

So instead, every fetcher here does one of:

  1. Download a tiny representative subset hosted on Wikimedia / GitHub
     mirrors that DO expose direct URLs (this is the common case here).
  2. Skip silently with a clear message pointing the user at the upstream
     access form (for CASIA-style gated datasets).

Cache layout::

    .cache/datasets/<dataset_name>/<filename>

The cache lives in :data:`CACHE_ROOT` which is on the project root and
already covered by ``.gitignore`` -- the binaries never end up in git.
"""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

# Resolve to <project_root>/.cache/datasets ; this file lives at
# tools/datasets/_common.py so two .parents go up to project root.
CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache" / "datasets"

USER_AGENT = (
    "ImageForensicsInspector-DatasetMini/0.1 "
    "(+https://github.com/CarGuo/find_image_hide; demo)"
)


def cache_dir(dataset: str) -> Path:
    p = CACHE_ROOT / dataset
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch(url: str, dst: Path, *, timeout: float = 20.0) -> bool:
    """Download ``url`` to ``dst`` if not already present. Best-effort."""
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  skip (cached): {dst.name}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        print(f"  ok:   {dst.name}  ({len(data):,} bytes)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {dst.name}: {exc}", file=sys.stderr)
        return False


def fetch_all(items: list[tuple[str, str]], dataset: str) -> int:
    """Download ``[(filename, url), ...]`` into ``cache_dir(dataset)``.

    Returns the count of successful downloads.  Sleeps 0.5s between requests
    to stay friendly with Wikimedia's anonymous-traffic rate limit.
    """
    out = cache_dir(dataset)
    print(f"[{dataset}] -> {out}")
    ok = 0
    for name, url in items:
        if fetch(url, out / name):
            ok += 1
        time.sleep(0.5)
    print(f"[{dataset}] {ok}/{len(items)} ok")
    return ok
