"""Visible watermark OCR detector.

Detects visible copyright / stock-photo watermarks burned into the pixels
(e.g. "Getty Images", "Shutterstock", "©", "Alamy", small logos with text)
which survive most "image laundering" operations (resize, recompress,
slight crop, color shift). This is one of the few signals that survives
JPEG re-saving.

OCR backends, tried in this order:
  1. pytesseract  (light, free, fast, must have tesseract binary on PATH)
  2. paddleocr    (heavier but better on stylized fonts; optional)

If neither is installed, the module degrades gracefully: returns
status=OCR_UNAVAILABLE with no risk escalation.

We only care about a short, well-known watermark vocabulary, so even an
imperfect OCR result is enough to raise an alert.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

WATERMARK_KEYWORDS = [
    "getty", "gettyimages", "getty images",
    "istock", "istockphoto",
    "shutterstock",
    "adobe stock", "stock.adobe", "fotolia",
    "alamy",
    "depositphotos",
    "dreamstime",
    "123rf",
    "pond5", "bigstock", "canva",
    "pixabay", "pexels", "unsplash",
    "ap images", "reuters", "afp", "bloomberg",
    "imatag", "digimarc",
    "westend61", "offset", "picfair",
    "stock photo", "rights managed",
]

COPYRIGHT_GLYPHS = ["\u00a9", "\u00ae", "\u2122", "(c)"]


def _ocr_available() -> tuple[str, Any] | None:
    """Return (backend_name, callable) or None if no OCR is available."""
    try:
        import pytesseract  # type: ignore
        # Also probe the binary - the import will succeed even without it.
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return None
        return "pytesseract", pytesseract
    except Exception:
        pass
    try:
        from paddleocr import PaddleOCR  # type: ignore
        ocr = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        return "paddleocr", ocr
    except Exception:
        pass
    return None


def _crop_regions(img: Image.Image) -> list[tuple[str, Image.Image]]:
    """Watermarks live mostly in corners + bottom strip + center. Cropping
    to those regions improves OCR recall on small overlays."""
    w, h = img.size
    cw, ch = max(80, w // 3), max(40, h // 4)
    regions: list[tuple[str, Image.Image]] = [
        ("full", img),
        ("bottom_strip", img.crop((0, max(0, h - ch), w, h))),
        ("top_strip", img.crop((0, 0, w, ch))),
        ("bottom_left", img.crop((0, max(0, h - ch), cw, h))),
        ("bottom_right", img.crop((max(0, w - cw), max(0, h - ch), w, h))),
        ("top_left", img.crop((0, 0, cw, ch))),
        ("top_right", img.crop((max(0, w - cw), 0, w, ch))),
        ("center", img.crop((max(0, (w - cw) // 2), max(0, (h - ch) // 2),
                              min(w, (w + cw) // 2), min(h, (h + ch) // 2)))),
    ]
    return regions


def _preprocess(region: Image.Image) -> list[Image.Image]:
    """Watermarks are often semi-transparent, so we run OCR on multiple
    contrast / inversion variants."""
    g = region.convert("L")
    g = ImageOps.autocontrast(g, cutoff=2)
    out = [g]
    try:
        out.append(ImageOps.invert(g))
    except Exception:
        pass
    return out


def _ocr_pytesseract(pyt, region: Image.Image) -> str:
    text_parts: list[str] = []
    for variant in _preprocess(region):
        try:
            txt = pyt.image_to_string(variant, config="--psm 6")
            if txt:
                text_parts.append(txt)
        except Exception:
            continue
    return "\n".join(text_parts)


def _ocr_paddle(ocr, region: Image.Image) -> str:
    import numpy as np  # type: ignore
    arr = np.array(region.convert("RGB"))
    try:
        result = ocr.ocr(arr, cls=False)
    except Exception:
        return ""
    out: list[str] = []
    if result and result[0]:
        for line in result[0]:
            try:
                out.append(line[1][0])
            except Exception:
                continue
    return "\n".join(out)


def _scan_text(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    low = text.lower()
    hits: list[dict[str, str]] = []
    for kw in WATERMARK_KEYWORDS:
        if kw in low:
            hits.append({"keyword": kw, "match_type": "stock_brand"})
    for g in COPYRIGHT_GLYPHS:
        if g in text:
            hits.append({"keyword": g, "match_type": "copyright_glyph"})
    # © followed by a word (©2024 Foo)
    m = re.search(r"\(c\)\s*\d{4}|\u00a9\s*\d{4}|copyright\s*\d{4}", low)
    if m:
        hits.append({"keyword": m.group(0), "match_type": "copyright_notice"})
    # de-dupe
    seen: set[tuple[str, str]] = set()
    out = []
    for h in hits:
        key = (h["keyword"], h["match_type"])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def analyze_visible_watermark(path: Path, vis_dir: Path) -> dict[str, Any]:
    path = Path(path)
    backend = _ocr_available()
    if backend is None:
        return {
            "status": "OCR_UNAVAILABLE",
            "risk_level": "UNKNOWN",
            "ocr_score": 0.0,
            "backend": None,
            "hits": [],
            "regions_scanned": [],
            "evidence_items": [],
            "note": "Install pytesseract (+ tesseract binary) or paddleocr to enable visible watermark detection.",
        }

    backend_name, engine = backend

    try:
        img = Image.open(path)
        img.load()
        img = img.convert("RGB")
    except Exception as exc:
        return {
            "status": "ERROR",
            "risk_level": "UNKNOWN",
            "ocr_score": 0.0,
            "backend": backend_name,
            "hits": [],
            "regions_scanned": [],
            "evidence_items": [],
            "error": f"open_failed: {exc}",
        }

    regions_scanned: list[dict[str, Any]] = []
    aggregated_hits: list[dict[str, Any]] = []
    raw_text_total: list[str] = []

    for region_name, region_img in _crop_regions(img):
        if backend_name == "pytesseract":
            text = _ocr_pytesseract(engine, region_img)
        else:
            text = _ocr_paddle(engine, region_img)
        if text:
            raw_text_total.append(f"[{region_name}]\n{text}")
            hits = _scan_text(text)
            for h in hits:
                aggregated_hits.append({
                    **h,
                    "region": region_name,
                    "context": text.strip()[:160],
                })
        regions_scanned.append({"region": region_name, "had_text": bool(text)})

    score = 0.0
    risk = "LOW"
    if aggregated_hits:
        # Stock-brand or copyright-notice = direct evidence
        has_brand = any(h["match_type"] in ("stock_brand", "copyright_notice") for h in aggregated_hits)
        score = 0.95 if has_brand else 0.55
        risk = "HIGH" if has_brand else "MEDIUM"

    # Save a small annotated preview
    overlay_path: str | None = None
    try:
        if aggregated_hits:
            overlay = img.copy()
            d = ImageDraw.Draw(overlay)
            d.text((8, 8), f"OCR hits: {len(aggregated_hits)}", fill=(255, 0, 0))
            overlay_file = vis_dir / "visible_watermark_overlay.jpg"
            overlay.save(overlay_file, quality=85)
            overlay_path = str(overlay_file)
    except Exception:
        overlay_path = None

    evidence_items: list[dict[str, Any]] = []
    for h in aggregated_hits:
        evidence_items.append({
            "module": "visible_watermark",
            "severity": "warning" if h["match_type"] in ("stock_brand", "copyright_notice") else "info",
            "title": f"可见水印关键词：{h['keyword']}",
            "description": f"区域={h['region']}，上下文={h.get('context','')}",
            "confidence": 0.9 if h["match_type"] == "stock_brand" else 0.6,
        })

    return {
        "status": "OK" if aggregated_hits else "NO_HIT",
        "risk_level": risk,
        "ocr_score": round(score, 3),
        "backend": backend_name,
        "hits": aggregated_hits,
        "regions_scanned": regions_scanned,
        "raw_text_excerpt": "\n---\n".join(raw_text_total)[:4000],
        "overlay_path": overlay_path,
        "evidence_items": evidence_items,
    }
