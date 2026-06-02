"""Download a curated set of real-world public images for demo / regression.

All sources below are either public-domain (Wikimedia Commons / NASA) or
explicitly free-to-use (picsum.photos / Unsplash hot-linked sample).  We keep
the list small so a fresh checkout can populate ``tools/test_images`` in a
few seconds.

The downloader is best-effort and skips any image that fails (offline, DNS,
mirror down).  The synthetic generator in ``make_test_images.py`` always
provides the deterministic baseline samples regardless of network state.

Layout
------
::

    tools/test_images/
        <legacy flat files>          # backwards compat with old regression
        clean_real/                  # untouched real photos (negative class)
        ai_generated/                # AI-generated (Wikimedia public-domain)
        c2pa_signed/                 # Content Credentials demo (if reachable)
        format_zoo/                  # WebP / TIFF / GIF format showcase

Each row in ``URLS`` carries a ``category`` field; legacy rows use
``category=""`` and stay in the flat ``test_images/`` root for backwards
compatibility with the existing regression scripts.
"""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "test_images"
OUT.mkdir(parents=True, exist_ok=True)

# (category, filename, url, short description)
# category="" means legacy flat layout (kept for backwards compatibility).
URLS: list[tuple[str, str, str, str]] = [
    # ---------------- legacy flat layout (kept) ----------------
    ("", "picsum_landscape.jpg",
     "https://picsum.photos/id/1018/640/426",
     "picsum #1018 mountain landscape (free use)"),
    ("", "picsum_portrait.jpg",
     "https://picsum.photos/id/1027/512/768",
     "picsum #1027 portrait (free use)"),
    ("", "picsum_grayscale.jpg",
     "https://picsum.photos/id/1062/640/426?grayscale",
     "picsum #1062 grayscale (free use)"),
    ("", "picsum_city.jpg",
     "https://picsum.photos/id/1043/800/533",
     "picsum #1043 city street (free use)"),
    ("", "picsum_food.jpg",
     "https://picsum.photos/id/292/640/480",
     "picsum #292 food photo (free use)"),

    ("", "commons_lenna.png",
     "https://upload.wikimedia.org/wikipedia/en/7/7d/Lenna_%28test_image%29.png",
     "Classic Lenna 512x512 test image"),
    ("", "commons_baboon.png",
     "https://upload.wikimedia.org/wikipedia/commons/2/29/Mandrill-yuv.png",
     "Mandrill / Baboon -- another classic test image (PD)"),
    ("", "commons_tulips.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/4/41/Sunflower_from_Silesia2.jpg",
     "Sunflower close-up with EXIF (CC-BY-SA)"),

    ("", "nasa_earth.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg",
     "NASA Earth from Apollo 17 (public domain)"),

    # ---------------- clean_real/ : negative class ----------------
    # Real photos with rich EXIF from a variety of cameras / phones.
    # Picks are short, license-clear, and span lighting conditions.
    ("clean_real", "canon_eos_landscape.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg",
     "Cat photo with Canon EOS EXIF (CC-BY-SA)"),
    ("clean_real", "iphone_indoor.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png",
     "PNG demonstration with metadata (PD)"),
    ("clean_real", "kodak_lossless_kodim23.png",
     "https://r0k.us/graphics/kodak/kodak/kodim23.png",
     "Kodak Lossless suite kodim23 -- standard reference (research-use)"),
    ("clean_real", "kodak_lossless_kodim07.png",
     "https://r0k.us/graphics/kodak/kodak/kodim07.png",
     "Kodak Lossless suite kodim07 -- standard reference (research-use)"),
    ("clean_real", "wikimedia_phone_snapshot.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/9/9a/Gull_portrait_ca_usa.jpg",
     "Gull portrait with full EXIF (CC-BY-SA)"),

    # ---------------- ai_generated/ : positive class for AI provenance ----------------
    # Verified Wikimedia Commons files (CC-BY-SA 4.0).  The previous
    # set used speculative paths which 404'd; these are confirmed live.
    ("ai_generated", "wikimedia_dalle3_example.png",
     "https://upload.wikimedia.org/wikipedia/commons/a/ad/DALL-E_3_Wikipedia_Example.png",
     "DALL-E 3 example image (CC-BY-SA via Wikimedia)"),
    ("ai_generated", "wikimedia_dalle2_shiba.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/2/2b/A_Shiba_Inu_dog_wearing_a_beret_and_black_turtleneck_DALLE2.jpg",
     "DALL-E 2 -- Shiba Inu dog with beret (CC-BY-SA)"),
    ("ai_generated", "wikimedia_midjourney_oldtimer.png",
     "https://upload.wikimedia.org/wikipedia/commons/3/33/Midjourney_-_Oldtimer.png",
     "Midjourney v4 -- vintage car (CC-BY-SA)"),
    ("ai_generated", "wikimedia_midjourney_castle.png",
     "https://upload.wikimedia.org/wikipedia/commons/8/8c/Midjourney_-_Dark_Castle_with_Dragon.png",
     "Midjourney v4 -- castle with dragon (CC-BY-SA)"),
    ("ai_generated", "wikimedia_sdxl_poisoned.png",
     "https://upload.wikimedia.org/wikipedia/commons/2/20/Example_images_generated_by_SD-XL_when_poisoned_with_data_poisoning_samples_according_to_a_study.png",
     "SD-XL examples (data-poisoning study) -- multi-grid (CC-BY-SA)"),

    # ---------------- c2pa_signed/ : Content Credentials demo ----------------
    # Adobe's Content Authenticity Initiative hosts a handful of demo assets but
    # the canonical URLs change frequently.  We deliberately leave this empty
    # for now -- a stable demo asset will be added together with the P1
    # ``c2pa_check`` detector (see docs/ROADMAP.md).

    # ---------------- format_zoo/ : format compatibility showcase ----------------
    # WebP / GIF keep our metadata + format readers honest.
    ("format_zoo", "wikimedia_sample.webp",
     "https://upload.wikimedia.org/wikipedia/commons/7/74/Buzz_and_the_Bulk_Sample_Area.webp",
     "Buzz Aldrin sample area on the Moon (PD via NASA)"),
    ("format_zoo", "wikimedia_sample.gif",
     "https://upload.wikimedia.org/wikipedia/commons/2/2c/Rotating_earth_%28large%29.gif",
     "Rotating Earth animated GIF (CC-BY-SA)"),
]


def download(category: str, name: str, url: str) -> bool:
    sub = OUT if not category else (OUT / category)
    sub.mkdir(parents=True, exist_ok=True)
    dst = sub / name
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  skip (exists): {category or '.'}/{name}")
        return True
    try:
        req = urllib.request.Request(
            url,
            headers={
                # Wikimedia's UA policy asks for an identifying string + URL/email.
                # See https://meta.wikimedia.org/wiki/User-Agent_policy
                "User-Agent": (
                    "ImageForensicsInspector/0.3 "
                    "(+https://github.com/CarGuo/find_image_hide; demo)"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        dst.write_bytes(data)
        print(f"  ok:   {category or '.'}/{name}  ({len(data):,} bytes)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {category or '.'}/{name}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    print(f"Downloading real-world demo images into {OUT}")
    ok = 0
    for cat, name, url, desc in URLS:
        tag = f"[{cat or 'flat'}]"
        print(f"- {tag} {desc}")
        if download(cat, name, url):
            ok += 1
        # Wikimedia caps anonymous downloads at ~1/s; play nice across the batch.
        time.sleep(0.5)
    print(f"\nDownloaded / verified {ok}/{len(URLS)} images.")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
