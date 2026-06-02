"""Generate "social media laundered" variants of an image.

Real-world adversaries rarely send pixel-perfect images: they get re-encoded
by Telegram / WeChat / Twitter / X / Weibo / WhatsApp before reaching us.
Each platform applies its own quality / dimension cap, strips most metadata
and re-encodes JPEG, which destroys fragile signals (LSB stego, invisible
watermarks, fine-grained ELA) but should NOT defeat perceptual hash
matching, copy-move detection, or content-credential C2PA verification when
the manifest is preserved.

This tool reproduces those re-encodes deterministically so we can build
"before vs after laundering" pairs and assert which detectors stay robust.

Profiles (best-effort approximations, not byte-perfect emulators):

  * telegram   : long edge <= 1280, JPEG q=80, EXIF stripped
  * wechat     : long edge <=  960, JPEG q=70, EXIF stripped, slight blur
  * twitter    : long edge <= 2048, JPEG q=85, EXIF stripped (preserves
                  most metadata since 2023, but re-encodes anyway)
  * weibo      : long edge <= 1080, JPEG q=75, EXIF stripped
  * whatsapp   : long edge <=  800, JPEG q=70, EXIF stripped (mobile cap)

Usage::

    python tools/launder_image.py path/to/source.jpg
    python tools/launder_image.py path/to/source.jpg --profiles telegram twitter
    python tools/launder_image.py path/to/source.jpg --out tools/test_images/social_laundered

"""
from __future__ import annotations

import argparse
import io
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter


@dataclass(frozen=True)
class LaunderProfile:
    name: str
    long_edge: int
    jpeg_quality: int
    blur_radius: float = 0.0  # 0 means no blur
    strip_metadata: bool = True


PROFILES: dict[str, LaunderProfile] = {
    "telegram": LaunderProfile("telegram", 1280, 80),
    "wechat":   LaunderProfile("wechat",    960, 70, blur_radius=0.3),
    "twitter":  LaunderProfile("twitter",  2048, 85),
    "weibo":    LaunderProfile("weibo",    1080, 75),
    "whatsapp": LaunderProfile("whatsapp",  800, 70),
}


def _resize_keep_aspect(img: Image.Image, long_edge: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= long_edge:
        return img
    if w >= h:
        new_w = long_edge
        new_h = max(1, round(h * long_edge / w))
    else:
        new_h = long_edge
        new_w = max(1, round(w * long_edge / h))
    return img.resize((new_w, new_h), Image.LANCZOS)


def launder(src: Path, profile: LaunderProfile, dst: Path) -> Path:
    """Apply the laundering profile and write a JPEG to ``dst``."""
    with Image.open(src) as im:
        im.load()
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im = _resize_keep_aspect(im, profile.long_edge)
        if profile.blur_radius > 0:
            im = im.filter(ImageFilter.GaussianBlur(radius=profile.blur_radius))

        save_kwargs: dict[str, object] = {
            "format": "JPEG",
            "quality": profile.jpeg_quality,
            "optimize": True,
            "progressive": True,
        }
        # When stripping metadata we explicitly avoid passing exif=
        # / icc_profile= so the output has no EXIF / ICC blob.
        if not profile.strip_metadata:
            exif = im.info.get("exif")
            icc = im.info.get("icc_profile")
            if exif:
                save_kwargs["exif"] = exif
            if icc:
                save_kwargs["icc_profile"] = icc

        buf = io.BytesIO()
        im.save(buf, **save_kwargs)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return dst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Social media re-encode emulator.")
    parser.add_argument("source", type=Path, help="Source image to launder.")
    parser.add_argument(
        "--profiles", nargs="+", default=list(PROFILES.keys()),
        choices=list(PROFILES.keys()),
        help="Which platforms to emulate (default: all).",
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path(__file__).resolve().parent / "test_images" / "social_laundered",
        help="Output directory.",
    )
    args = parser.parse_args(argv)

    src: Path = args.source.resolve()
    if not src.exists():
        print(f"source not found: {src}", file=sys.stderr)
        return 2

    out_dir: Path = args.out.resolve()
    print(f"Laundering {src.name} -> {out_dir}")
    for pname in args.profiles:
        profile = PROFILES[pname]
        dst = out_dir / f"{src.stem}__{profile.name}.jpg"
        launder(src, profile, dst)
        size = dst.stat().st_size
        print(f"  ok: {dst.name}  q={profile.jpeg_quality} edge<={profile.long_edge}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
