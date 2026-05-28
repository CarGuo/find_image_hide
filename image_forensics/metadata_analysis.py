"""Metadata analysis (EXIF, XMP, IPTC, PNG chunks, JPEG comment)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

AI_KEYWORDS = [
    "OpenAI", "ChatGPT", "DALL-E", "DALL\u00b7E", "GPT-4o", "GPT Image",
    "Google", "Gemini", "Imagen", "DeepMind", "SynthID",
    "C2PA", "Content Credentials", "contentauthenticity",
    "Adobe Firefly", "Firefly", "Photoshop", "Lightroom",
    "Midjourney", "Stable Diffusion", "ComfyUI",
    "Automatic1111", "AUTOMATIC1111", "InvokeAI", "Leonardo", "Ideogram",
    "stealth_pnginfo", "parameters",
]

STOCK_KEYWORDS = [
    "Getty Images", "gettyimages", "iStockphoto", "iStock",
    "Shutterstock", "Shutterstock Inc", "shutterstock.com",
    "Adobe Stock", "Fotolia", "stock.adobe.com",
    "Alamy", "alamy.com",
    "Depositphotos", "depositphotos.com",
    "Dreamstime", "dreamstime.com",
    "123RF", "123rf.com",
    "Pond5", "Bigstock", "BigStockPhoto", "Canva",
    "Pixabay", "Pexels", "Unsplash",
    "AP Images", "Reuters", "AFP", "Bloomberg",
    "Photodisc", "Stockbyte", "Hemera",
    "Picfair", "Westend61", "Cavan Images", "Offset",
    "Imatag", "Digimarc", "DigimarcWatermark",
]

SUSPICIOUS_FIELDS = {
    "Software", "ProcessingSoftware", "CreatorTool", "Comment",
    "ImageDescription", "UserComment", "Make", "Model", "Artist",
    "Copyright", "DateTime", "DateTimeOriginal", "GPSInfo",
    "XMLPacket", "Description", "parameters",
}


def _stringify(v: Any) -> Any:
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return v.hex()
    if isinstance(v, dict):
        return {str(k): _stringify(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_stringify(x) for x in v]
    try:
        import json
        json.dumps(v)
        return v
    except Exception:
        return str(v)


def _read_exif(img: Image.Image) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    try:
        exif = img.getexif()
        if not exif:
            return raw
        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, str(tag_id))
            raw[tag] = _stringify(value)
        try:
            ifd = exif.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(ExifTags, "IFD") else {}
            if ifd:
                gps = {}
                for k, v in ifd.items():
                    name = ExifTags.GPSTAGS.get(k, str(k))
                    gps[name] = _stringify(v)
                raw["GPSInfo"] = gps
        except Exception:
            pass
    except Exception:
        pass
    return raw


def _read_xmp(img: Image.Image) -> str | None:
    try:
        if hasattr(img, "getxmp"):
            xmp = img.getxmp()
            if xmp:
                return _stringify(xmp)
    except Exception:
        pass
    info = getattr(img, "info", {}) or {}
    for k, v in info.items():
        if isinstance(v, (bytes, str)) and "xmpmeta" in str(v).lower():
            return _stringify(v)
    return None


def _read_png_text(img: Image.Image) -> dict[str, Any]:
    out: dict[str, Any] = {}
    info = getattr(img, "info", {}) or {}
    for k, v in info.items():
        if isinstance(v, (str, bytes)):
            out[str(k)] = _stringify(v)
    text = getattr(img, "text", None)
    if isinstance(text, dict):
        for k, v in text.items():
            out[str(k)] = _stringify(v)
    return out


def _read_jpeg_comment(img: Image.Image) -> str | None:
    info = getattr(img, "info", {}) or {}
    com = info.get("comment")
    if com:
        return _stringify(com)
    return None


def _scan_keywords(blob: str) -> list[str]:
    found: list[str] = []
    low = blob.lower()
    for kw in AI_KEYWORDS:
        if kw.lower() in low:
            found.append(kw)
    seen: list[str] = []
    for f in found:
        if f not in seen:
            seen.append(f)
    return seen


def _walk_fields(node: Any, prefix: str = ""):
    """Yield (field_path, str_value) for every leaf in a nested dict/list."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_fields(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _walk_fields(v, f"{prefix}[{i}]")
    else:
        try:
            yield prefix, str(node)
        except Exception:
            pass


def _scan_stock_hits(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Find stock-photo / watermarking-vendor signatures in metadata.

    Returns a list of evidences with field path, hit keyword, and value
    preview so the user can see *why* a copyrighted image was flagged.
    """
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path, value in _walk_fields(raw):
        if not value:
            continue
        low = value.lower()
        for kw in STOCK_KEYWORDS:
            if kw.lower() in low:
                key = (path, kw, value[:120])
                if key in seen:
                    continue
                seen.add(key)
                hits.append({
                    "field": path,
                    "keyword": kw,
                    "value_preview": value[:240],
                })
    return hits


def collect_metadata(path: Path) -> dict[str, Any]:
    path = Path(path)
    result: dict[str, Any] = {
        "has_exif": False,
        "has_xmp": False,
        "has_iptc": False,
        "has_png_text": False,
        "has_jpeg_comment": False,
        "raw": {},
        "suspicious_fields": [],
        "metadata_ai_keywords": [],
    }
    try:
        with Image.open(path) as img:
            img.load()
            exif = _read_exif(img)
            if exif:
                result["has_exif"] = True
                result["raw"]["exif"] = exif
            xmp = _read_xmp(img)
            if xmp:
                result["has_xmp"] = True
                result["raw"]["xmp"] = xmp
            png_text = _read_png_text(img) if img.format == "PNG" else {}
            if png_text:
                result["has_png_text"] = True
                result["raw"]["png_text"] = png_text
            jpeg_com = _read_jpeg_comment(img)
            if jpeg_com:
                result["has_jpeg_comment"] = True
                result["raw"]["jpeg_comment"] = jpeg_com
            try:
                iptc = getattr(img, "info", {}).get("photoshop") or getattr(img, "info", {}).get("iptc")
                if iptc:
                    result["has_iptc"] = True
                    result["raw"]["iptc"] = _stringify(iptc)
            except Exception:
                pass
    except Exception as exc:
        result["error"] = f"metadata_failed: {exc}"

    blob = str(result["raw"])
    suspicious: list[str] = []
    if "exif" in result["raw"]:
        for k in result["raw"]["exif"].keys():
            if k in SUSPICIOUS_FIELDS:
                suspicious.append(f"exif.{k}")
    if result["has_png_text"]:
        for k in result["raw"]["png_text"].keys():
            suspicious.append(f"png_text.{k}")
    result["suspicious_fields"] = suspicious
    result["metadata_ai_keywords"] = _scan_keywords(blob)
    stock_hits = _scan_stock_hits(result["raw"])
    result["metadata_stock_hits"] = stock_hits
    result["metadata_stock_keywords"] = sorted({h["keyword"] for h in stock_hits})
    result["stock_image_match"] = "HIGH" if stock_hits else "NONE"
    return result
