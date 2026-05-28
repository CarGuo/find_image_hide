"""Metadata analysis (EXIF, XMP, IPTC, PNG chunks, JPEG comment)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

from .psd_metadata import parse_psd_metadata

try:
    from iptcinfo3 import IPTCInfo  # type: ignore
    _HAS_IPTC = True
except Exception:
    _HAS_IPTC = False

# IPTC IIM 数字 tag → 语义名
_IPTC_TAG_MAP = {
    "by-line": "Creator",
    "by-line title": "CreatorJobTitle",
    "credit": "Credit",
    "source": "Source",
    "copyright notice": "CopyrightNotice",
    "rights usage terms": "RightsUsageTerms",
    "contact": "Contact",
    "object name": "Title",
    "caption/abstract": "Description",
    "keywords": "Keywords",
    "special instructions": "Instructions",
}

# XMP-PLUS / dc / xmpRights / Photoshop 关心的版权字段（小写匹配）
_XMP_COPYRIGHT_KEYS = {
    "rights": "dc:rights",
    "creator": "dc:creator",
    "usageterms": "xmpRights:UsageTerms",
    "webstatement": "xmpRights:WebStatement",
    "marked": "xmpRights:Marked",
    "credit": "photoshop:Credit",
    "source": "photoshop:Source",
    "copyrightowner": "plus:CopyrightOwner",
    "licensorurl": "plus:LicensorURL",
    "licensor": "plus:Licensor",
    "imagecreator": "plus:ImageCreator",
    "modelreleasestatus": "plus:ModelReleaseStatus",
    "minorrelevantmodelagedisclosure": "plus:MinorRelevantModelAgeDisclosure",
}

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


def _read_iptc_full(path: Path) -> dict[str, Any]:
    """Read full IPTC IIM block via iptcinfo3 if available."""
    out: dict[str, Any] = {}
    if not _HAS_IPTC:
        return out
    try:
        info = IPTCInfo(str(path), force=True)
        for raw_key, semantic in _IPTC_TAG_MAP.items():
            try:
                v = info[raw_key]
            except Exception:
                continue
            if not v:
                continue
            if isinstance(v, list):
                vals = [_stringify(x) for x in v if x]
                if vals:
                    out[semantic] = vals if len(vals) > 1 else vals[0]
            else:
                s = _stringify(v)
                if s:
                    out[semantic] = s
    except Exception:
        pass
    return out


def _extract_xmp_copyright(xmp_blob: Any) -> dict[str, Any]:
    """Pull the dc:rights / xmpRights:* / photoshop:* / plus:* copyright fields
    out of a XMP packet (string or nested dict from PIL.getxmp())."""
    out: dict[str, Any] = {}
    blob_text = ""
    if isinstance(xmp_blob, dict):
        for path, value in _walk_fields(xmp_blob):
            tail = path.split(".")[-1].lower().strip()
            if tail in _XMP_COPYRIGHT_KEYS and value:
                out.setdefault(_XMP_COPYRIGHT_KEYS[tail], value)
        blob_text = str(xmp_blob)
    else:
        blob_text = str(xmp_blob or "")

    if blob_text:
        # 兜底：用正则从 XMP 文本里抓 dc:rights/xmpRights:UsageTerms 等
        patterns = {
            "dc:rights": r"<dc:rights>.*?<rdf:li[^>]*>(.*?)</rdf:li>",
            "dc:creator": r"<dc:creator>.*?<rdf:li[^>]*>(.*?)</rdf:li>",
            "xmpRights:UsageTerms": r"<xmpRights:UsageTerms>.*?<rdf:li[^>]*>(.*?)</rdf:li>",
            "xmpRights:WebStatement": r'xmpRights:WebStatement="([^"]+)"',
            "xmpRights:Marked": r'xmpRights:Marked="([^"]+)"',
            "photoshop:Credit": r'photoshop:Credit="([^"]+)"',
            "photoshop:Source": r'photoshop:Source="([^"]+)"',
            "plus:LicensorURL": r"<plus:LicensorURL[^>]*>([^<]+)</plus:LicensorURL>",
            "plus:CopyrightOwnerName": r"<plus:CopyrightOwnerName[^>]*>([^<]+)</plus:CopyrightOwnerName>",
        }
        for label, pat in patterns.items():
            try:
                m = re.search(pat, blob_text, flags=re.IGNORECASE | re.DOTALL)
                if m:
                    val = m.group(1).strip()
                    if val and label not in out:
                        out[label] = val
            except Exception:
                pass
    return out


def _build_copyright_summary(
    exif: dict[str, Any], iptc: dict[str, Any], xmp_cr: dict[str, Any]
) -> dict[str, Any]:
    """Aggregate the canonical copyright fields across EXIF + IPTC + XMP-PLUS
    into a single, easy-to-render summary."""
    summary: dict[str, Any] = {}
    # EXIF Copyright / Artist
    if exif:
        for key in ("Copyright", "Artist"):
            v = exif.get(key)
            if v:
                summary.setdefault(f"exif.{key}", v)
    # IPTC
    for key in ("CopyrightNotice", "Creator", "Credit", "Source", "RightsUsageTerms", "Contact"):
        v = iptc.get(key)
        if v:
            summary[f"iptc.{key}"] = v
    # XMP-PLUS
    for k, v in xmp_cr.items():
        if v:
            summary[f"xmp.{k}"] = v
    has_explicit = any(
        k.endswith(".CopyrightNotice")
        or k.endswith(".Copyright")
        or k.endswith(":rights")
        or k.endswith(":UsageTerms")
        or k.endswith(":CopyrightOwnerName")
        or k.endswith(":LicensorURL")
        for k in summary.keys()
    )
    return {
        "fields": summary,
        "has_explicit_copyright": has_explicit,
        "field_count": len(summary),
    }


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

    # --- PSD 专用分支：直接读 Image Resources Block ---
    psd_meta: dict[str, Any] = {}
    if path.suffix.lower() == ".psd":
        try:
            psd_meta = parse_psd_metadata(path) or {}
        except Exception as exc:
            psd_meta = {"error": f"psd_parse_failed: {exc}"}
        if psd_meta:
            result["raw"]["psd"] = psd_meta
            # PSD 里的 XMP 是文本，直接覆盖（PIL 在 PSD 上很多版本不导出 XMP）
            xmp_text = psd_meta.get("xmp")
            if xmp_text and not result["raw"].get("xmp"):
                result["has_xmp"] = True
                result["raw"]["xmp"] = xmp_text
            # PSD 里的 IPTC IIM 已经被解析成语义名 dict，直接合并到 iptc_full
            psd_iptc = psd_meta.get("iptc_iim") or {}
            if psd_iptc:
                result["has_iptc"] = True
                merged = dict(result["raw"].get("iptc_full") or {})
                for k, v in psd_iptc.items():
                    merged.setdefault(k, v)
                result["raw"]["iptc_full"] = merged

    # --- IPTC IIM 完整字段（iptcinfo3） ---
    iptc_full: dict[str, Any] = {}
    try:
        iptc_full = _read_iptc_full(path)
    except Exception:
        iptc_full = {}
    if iptc_full:
        result["has_iptc"] = True
        merged = dict(result["raw"].get("iptc_full") or {})
        for k, v in iptc_full.items():
            merged.setdefault(k, v)
        result["raw"]["iptc_full"] = merged
    iptc_full = result["raw"].get("iptc_full") or {}

    # --- XMP-PLUS / dc / xmpRights / photoshop 版权字段 ---
    xmp_copyright: dict[str, Any] = {}
    try:
        xmp_copyright = _extract_xmp_copyright(result["raw"].get("xmp"))
    except Exception:
        xmp_copyright = {}
    if xmp_copyright:
        result["raw"]["xmp_copyright"] = xmp_copyright

    # --- 版权字段汇总 ---
    exif_block = result["raw"].get("exif", {}) if isinstance(result["raw"].get("exif"), dict) else {}
    result["copyright_summary"] = _build_copyright_summary(exif_block, iptc_full, xmp_copyright)

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
