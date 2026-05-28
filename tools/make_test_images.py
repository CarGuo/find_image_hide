"""Generate a small set of test images to exercise the analyzer.

Produces:
  test_images/
    normal_jpeg.jpg          -- natural-ish gradient + noise JPEG
    normal_png.png           -- same content as PNG
    lsb_steg.png             -- PNG with a clearly random LSB plane (mimics LSB stego)
    ai_metadata.png          -- PNG with text chunks containing AI keywords
    tiny.png                 -- very small image (edge case)
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin


OUT = Path(__file__).resolve().parent / "test_images"
OUT.mkdir(parents=True, exist_ok=True)


def make_natural(w=512, h=384, seed=1):
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((h, w)).astype(np.float32)
    r = (xx / w * 200 + 30).astype(np.float32)
    g = (yy / h * 200 + 40).astype(np.float32)
    b = (((xx + yy) / (w + h)) * 200 + 50).astype(np.float32)
    img = np.stack([r, g, b], axis=-1)
    img += rng.normal(0, 4.0, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img)


def make_smooth_clean(w=512, h=384, seed=1):
    """A 'clean' image whose LSB plane is structured (low-entropy) -> good as a
    negative control for LSB steganalysis. Uses a quantized gradient instead of
    additive noise so LSBs follow a deterministic pattern.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((h, w)).astype(np.float32)
    r = (xx / w * 200 + 30)
    g = (yy / h * 200 + 40)
    b = (((xx + yy) / (w + h)) * 200 + 50)
    img = np.stack([r, g, b], axis=-1)
    img = (np.round(img / 4.0) * 4.0)
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img)


def make_lsb_steg(base: Image.Image, seed=42) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = np.asarray(base, dtype=np.uint8).copy()
    h, w, _ = arr.shape
    rand_bits = rng.integers(0, 2, size=(h, w, 3), dtype=np.uint8)
    arr = (arr & 0xFE) | rand_bits
    return Image.fromarray(arr)


def make_trailing_zip(base: Image.Image, out_path: Path) -> None:
    import zipfile
    base.save(out_path, format="PNG")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("secret.txt", "TOP SECRET: the password is hunter2\nflag{hidden_in_png_trailer}\n")
    with open(out_path, "ab") as fh:
        fh.write(zip_buf.getvalue())


def make_trailing_text(base: Image.Image, out_path: Path) -> None:
    base.save(out_path, format="JPEG", quality=88)
    with open(out_path, "ab") as fh:
        fh.write(b"\n----- HIDDEN MESSAGE -----\n")
        fh.write(b"flag{appended_after_jpeg_eoi_marker}\n")
        fh.write(b"contact: secret-agent@example.com\n")


def make_lsb_text_payload(base: Image.Image, out_path: Path, message: bytes) -> None:
    arr = np.asarray(base, dtype=np.uint8).copy()
    h, w, _ = arr.shape
    flat = arr.reshape(-1)
    payload = message + b"\x00" * 8
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    nbits = min(bits.size, flat.size)
    flat[:nbits] = (flat[:nbits] & 0xFE) | bits[:nbits]
    Image.fromarray(flat.reshape(arr.shape)).save(out_path)


def make_visible_watermark(base: Image.Image, out_path: Path, text: str = "Getty Images") -> None:
    """Burn a visible English watermark into the bottom-right corner."""
    from PIL import ImageDraw, ImageFont
    img = base.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
    w, h = img.size
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * 14, 28
    x, y = w - tw - 12, h - th - 12
    d.rectangle([x - 6, y - 4, x + tw + 6, y + th + 6], fill=(0, 0, 0, 200))
    d.text((x, y), text, font=font, fill=(255, 255, 255))
    img.save(out_path, format="JPEG", quality=92)


def make_full_iptc_copyright(base: Image.Image, out_path: Path) -> None:
    """JPEG with a full IPTC IIM copyright record (CopyrightNotice / Creator /
    Credit / Source / RightsUsageTerms / Contact). Demonstrates a properly
    licensed stock photo's metadata."""
    # 先写入一个带 EXIF 占位的 JPEG，iptcinfo3 在带元数据段的 JPEG 上才能稳定写入
    base.convert("RGB").save(out_path, format="JPEG", quality=92)
    try:
        import piexif  # type: ignore
        zeroth = {
            piexif.ImageIFD.Software: b"Acme Stock Library 1.0",
            piexif.ImageIFD.Artist: b"Jane Photographer",
            piexif.ImageIFD.Copyright: b"(C) 2024 Acme Studio. All rights reserved.",
        }
        piexif.insert(piexif.dump({"0th": zeroth, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}), str(out_path))
    except Exception:
        pass
    try:
        from iptcinfo3 import IPTCInfo  # type: ignore
        info = IPTCInfo(str(out_path), force=True)
        # 注意：iptcinfo3 的 key 必须是 IIM 标准小写字段名，下面这些都是它支持的：
        # 'copyright notice'、'by-line'、'by-line title'、'credit'、'source'、
        # 'caption/abstract'、'object name'、'keywords'、'special instructions'。
        # 'contact'、'rights usage terms' 不在 IIM IIM 标准里 → iptcinfo3 会抛
        # KeyError。版权用法条款放到 'special instructions' 里写更兼容；
        # 联系方式放到 'caption/abstract' 末尾。
        info["copyright notice"] = "(C) 2024 Acme Studio. All rights reserved."
        info["by-line"] = "Jane Photographer"
        info["by-line title"] = "Senior Photographer"
        info["credit"] = "Acme Stock"
        info["source"] = "AcmeStock.com"
        info["special instructions"] = (
            "Editorial use only. No commercial use without written permission. "
            "Contact: license@acmestock.com"
        )
        info["object name"] = "Sunset over the bay"
        info["caption/abstract"] = (
            "Properly licensed stock photo. Demonstrates a complete IPTC IIM record."
        )
        info["keywords"] = ["editorial", "licensed", "acmestock", "demo"]
        info.save_as(str(out_path))
        bak = Path(str(out_path) + "~")
        if bak.exists():
            try:
                bak.unlink()
            except Exception:
                pass
    except Exception as exc:
        # 没装 iptcinfo3 时降级：直接打印警告 + 保留 EXIF 占位，不再污染文件尾部
        # （之前会 append `[IPTC fallback] ...` 到 JPEG EOI 之后，反而被 extraction
        # 模块当成尾部隐藏内容报警，违背"测试样本"的语义。）
        print(f"[warn] iptcinfo3 unavailable, skipped IPTC for {out_path.name}: {exc}")


def make_invisible_watermark(base: Image.Image, out_path: Path, payload: str = "ACME") -> None:
    """Embed a real DwtDct invisible watermark via the invisible-watermark
    library. The decoder in invisible_watermark_detect.py should later
    surface the payload string as evidence."""
    try:
        import cv2  # type: ignore
        from imwatermark import WatermarkEncoder  # type: ignore
    except Exception as exc:
        # 没装库时降级：保存普通 JPEG 并提示
        base.convert("RGB").save(out_path, format="JPEG", quality=92)
        with open(out_path, "ab") as fh:
            fh.write(b"\n[invisible_watermark fallback] missing imwatermark/cv2: ")
            fh.write(str(exc).encode("utf-8", errors="replace"))
        return

    rgb = np.asarray(base.convert("RGB"), dtype=np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if min(bgr.shape[:2]) < 256:
        # invisible-watermark 对小图不稳定，必要时放大
        h, w = bgr.shape[:2]
        scale = max(1.0, 256.0 / float(min(h, w)))
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_LANCZOS4)
    enc = WatermarkEncoder()
    payload_bytes = payload.encode("utf-8")[:4]  # 32-bit
    if len(payload_bytes) < 4:
        payload_bytes = payload_bytes + b"\x00" * (4 - len(payload_bytes))
    enc.set_watermark("bytes", payload_bytes)
    out = enc.encode(bgr, "dwtDct")
    cv2.imwrite(str(out_path), out, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def make_ai_forged_copyright(base: Image.Image, out_path: Path) -> None:
    """Worst case: AI-generated image that *also* claims a fake copyright.
    EXIF/IPTC/XMP all assert ownership, but PNG text chunks reveal
    AI-generation parameters. The analyzer should flag both copyright fields
    AND AI-keywords, demonstrating that copyright metadata is forgeable."""
    img = base.convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=92)
    # 写假版权声明
    try:
        import piexif  # type: ignore
        zeroth = {
            piexif.ImageIFD.Artist: b"Totally Real Human Photographer",
            piexif.ImageIFD.Copyright: b"(C) 2024 Definitely-Not-AI Studio. All rights reserved.",
            piexif.ImageIFD.ImageDescription: (
                b"Original photograph, hand-shot on Canon EOS R5. Not AI generated. "
                b"prompt: cinematic landscape, masterpiece, Stable Diffusion XL, "
                b"Steps: 30, Sampler: DPM++ 2M Karras"
            ),
            piexif.ImageIFD.Software: b"Adobe Photoshop 25.0",
        }
        exif_dict = {"0th": zeroth, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        piexif.insert(piexif.dump(exif_dict), str(out_path))
    except Exception:
        pass
    # 再叠一层 IPTC 假版权
    try:
        from iptcinfo3 import IPTCInfo  # type: ignore
        info = IPTCInfo(str(out_path), force=True)
        info["copyright notice"] = "(C) 2024 Definitely-Not-AI Studio."
        info["by-line"] = "Totally Real Human Photographer"
        info["credit"] = "Original Work"
        info["caption/abstract"] = (
            "Cinematic landscape (prompt leaked: Stable Diffusion XL, Midjourney v6)."
        )
        info.save_as(str(out_path))
        bak = Path(str(out_path) + "~")
        if bak.exists():
            try:
                bak.unlink()
            except Exception:
                pass
    except Exception:
        pass


def make_stock_metadata(base: Image.Image, out_path: Path) -> None:
    """JPEG with EXIF Artist/Copyright/Software pointing to a stock photo
    library - the *most* common copyright signature."""
    from PIL import Image as _Image
    import piexif  # type: ignore  # optional

    base.convert("RGB").save(out_path, format="JPEG", quality=90)
    try:
        zeroth = {
            piexif.ImageIFD.Artist: b"Shutterstock contributor John Doe",
            piexif.ImageIFD.Copyright: b"(C) 2024 Shutterstock Inc. All rights reserved.",
            piexif.ImageIFD.Software: b"Adobe Photoshop 25.0 (Adobe Stock)",
            piexif.ImageIFD.ImageDescription: b"Editorial use only - Getty Images stock photo",
        }
        exif_dict = {"0th": zeroth, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(out_path))
    except Exception:
        # Fallback: write XMP-like sidecar inside JPEG comment via Pillow
        img = _Image.open(out_path)
        img.save(out_path, format="JPEG", quality=90,
                 comment=b"Shutterstock Inc. | Getty Images | (C) 2024 Adobe Stock")


def make_phash_reference_set(out_dir: Path) -> None:
    """A small reference library used by phash_match.

    We prefer real, textured photos (picsum) when available because pHash
    on flat/synthetic gradients can produce unstable hashes. Falls back to
    synthetic gradients if picsum images aren't on disk yet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    picsum = OUT / "picsum_landscape.jpg"
    if picsum.exists():
        # Use a real photo as a reference
        Image.open(picsum).convert("RGB").save(out_dir / "ref_real_landscape.jpg",
                                              quality=92)
    for i, seed in enumerate([101, 202, 303]):
        img = make_natural(seed=seed)
        img.save(out_dir / f"ref_stock_{i:02d}.png")


def make_phash_laundered(reference: Image.Image, out_path: Path) -> None:
    """Simulate 'image laundering': light resize + JPEG recompress.

    pHash is invariant to recompression and small resizes but breaks under
    significant cropping, so we keep the crop minimal."""
    img = reference.convert("RGB")
    w, h = img.size
    img = img.resize((int(w * 0.95), int(h * 0.95)))
    img.save(out_path, format="JPEG", quality=78)


def main() -> None:
    nat = make_natural()
    nat.save(OUT / "normal_jpeg.jpg", quality=88)

    clean = make_smooth_clean()
    clean.save(OUT / "normal_png.png")

    steg = make_lsb_steg(clean)
    steg.save(OUT / "lsb_steg.png")

    ai_meta = make_natural(seed=7)
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text(
        "parameters",
        "score_9, masterpiece, generated by Stable Diffusion + ComfyUI; "
        "Negative prompt: blurry; Steps: 30; Sampler: Euler a; Seed: 12345; "
        "claim_generator: OpenAI ChatGPT (DALL-E 3)",
    )
    pnginfo.add_text("Software", "Adobe Firefly 1.0")
    ai_meta.save(OUT / "ai_metadata.png", pnginfo=pnginfo)

    Image.fromarray(np.full((4, 4, 3), 128, dtype=np.uint8)).save(OUT / "tiny.png")

    make_trailing_zip(make_smooth_clean(seed=11), OUT / "trailing_zip.png")
    make_trailing_text(make_natural(seed=12), OUT / "trailing_text.jpg")
    make_lsb_text_payload(
        make_smooth_clean(seed=13),
        OUT / "lsb_text_payload.png",
        b"BEGIN_HIDDEN flag{lsb_payload_demo} contact=agent@example.com END_HIDDEN",
    )

    # Copyright / stock-image scenarios -- prefer real photos as the base
    # when they are already on disk (downloaded by download_test_images.py)
    real_for_wm = OUT / "picsum_city.jpg"
    if real_for_wm.exists():
        wm_base = Image.open(real_for_wm).convert("RGB")
    else:
        wm_base = make_natural(seed=21)
    make_visible_watermark(wm_base, OUT / "visible_watermark_getty.jpg",
                           text="Getty Images")
    # 5 张主流图库品牌可见水印
    brand_pairs = [
        ("visible_watermark_shutterstock.jpg", "Shutterstock", 31),
        ("visible_watermark_istock.jpg", "iStock by Getty Images", 32),
        ("visible_watermark_unsplash.jpg", "Unsplash", 33),
        ("visible_watermark_adobestock.jpg", "Adobe Stock", 34),
        ("visible_watermark_alamy.jpg", "Alamy", 35),
    ]
    for fname, brand, seed in brand_pairs:
        bb = Image.open(real_for_wm).convert("RGB") if real_for_wm.exists() else make_natural(seed=seed)
        make_visible_watermark(bb, OUT / fname, text=brand)

    real_for_stock = OUT / "picsum_food.jpg"
    if real_for_stock.exists():
        stock_base = Image.open(real_for_stock).convert("RGB")
    else:
        stock_base = make_natural(seed=22)
    make_stock_metadata(stock_base, OUT / "stock_metadata_shutterstock.jpg")

    # IPTC 完整版权例：合法授权图库的「正面教材」
    iptc_base = (
        Image.open(OUT / "picsum_landscape.jpg").convert("RGB")
        if (OUT / "picsum_landscape.jpg").exists()
        else make_natural(seed=41)
    )
    make_full_iptc_copyright(iptc_base, OUT / "iptc_full_copyright.jpg")

    # invisible-watermark 真实嵌入例：DwtDct 32-bit "ACME" payload
    inv_base = (
        Image.open(OUT / "picsum_city.jpg").convert("RGB")
        if (OUT / "picsum_city.jpg").exists()
        else make_natural(seed=42)
    )
    make_invisible_watermark(inv_base, OUT / "invisible_watermark_dwtdct.jpg", payload="ACME")

    # AI 改图后伪造版权声明攻击例：版权字段说"是我拍的"，但描述里漏了 prompt
    ai_attack_base = (
        Image.open(OUT / "picsum_portrait.jpg").convert("RGB")
        if (OUT / "picsum_portrait.jpg").exists()
        else make_natural(seed=43)
    )
    make_ai_forged_copyright(ai_attack_base, OUT / "ai_forged_copyright.jpg")

    ref_dir = OUT.parent / "phash_reference"
    make_phash_reference_set(ref_dir)
    picsum = OUT / "picsum_landscape.jpg"
    if picsum.exists():
        # Real-photo case: launder the picsum that the reference set also has
        ref_img = Image.open(picsum)
    else:
        ref_img = make_natural(seed=101)
    make_phash_laundered(ref_img, OUT / "phash_laundered_match.jpg")

    print("Wrote test images to", OUT)
    for p in sorted(OUT.iterdir()):
        print(" -", p.name, "(", p.stat().st_size, "bytes )")


if __name__ == "__main__":
    main()
