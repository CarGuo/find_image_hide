"""Download a curated set of real-world public images for demo / regression.

All sources below are either public-domain (Wikimedia Commons / NASA) or
explicitly free-to-use (picsum.photos / Unsplash hot-linked sample).  We keep
the list small so a fresh checkout can populate ``tools/test_images`` in a
few seconds.

The downloader is best-effort and skips any image that fails (offline, DNS,
mirror down).  The synthetic generator in ``make_test_images.py`` always
provides the deterministic baseline samples regardless of network state.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "test_images"
OUT.mkdir(parents=True, exist_ok=True)

# (filename, url, short description)
URLS: list[tuple[str, str, str]] = [
    # picsum.photos -- free, deterministic seeds, real photographs
    ("picsum_landscape.jpg",
     "https://picsum.photos/id/1018/640/426",
     "picsum #1018 mountain landscape (free use)"),
    ("picsum_portrait.jpg",
     "https://picsum.photos/id/1027/512/768",
     "picsum #1027 portrait (free use)"),
    ("picsum_grayscale.jpg",
     "https://picsum.photos/id/1062/640/426?grayscale",
     "picsum #1062 grayscale (free use)"),
    ("picsum_city.jpg",
     "https://picsum.photos/id/1043/800/533",
     "picsum #1043 city street (free use)"),
    ("picsum_food.jpg",
     "https://picsum.photos/id/292/640/480",
     "picsum #292 food photo (free use)"),

    # Wikimedia Commons -- public domain / CC0 / CC-BY
    # NOTE: Wikimedia rejects arbitrary thumbnail sizes; use canonical full URLs.
    ("commons_lenna.png",
     "https://upload.wikimedia.org/wikipedia/en/7/7d/Lenna_%28test_image%29.png",
     "Classic Lenna 512x512 test image"),
    ("commons_baboon.png",
     "https://upload.wikimedia.org/wikipedia/commons/8/8c/Mandrill.png",
     "Mandrill / Baboon -- another classic test image (PD)"),
    ("commons_tulips.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/4/41/Sunflower_from_Silesia2.jpg",
     "Sunflower close-up with EXIF (CC-BY-SA)"),

    # NASA -- always public domain (use the full-res JPEG, no thumbnail trick)
    ("nasa_earth.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg",
     "NASA Earth from Apollo 17 (public domain)"),
]


def download(name: str, url: str) -> bool:
    dst = OUT / name
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  skip (exists): {name}")
        return True
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ImageForensicsInspector/0.2 (+demo)"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        dst.write_bytes(data)
        print(f"  ok:   {name}  ({len(data):,} bytes)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {name}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    print(f"Downloading real-world demo images into {OUT}")
    ok = 0
    for name, url, desc in URLS:
        print(f"- {desc}")
        if download(name, url):
            ok += 1
    print(f"\nDownloaded / verified {ok}/{len(URLS)} images.")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
