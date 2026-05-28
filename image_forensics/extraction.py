"""Hidden-content extraction.

This module attempts to *show what is hidden in the image* using techniques
adopted from zsteg, stegsolve, binwalk, and Foremost:

  1. LSB bit-stream extraction in multiple bit/channel/order combinations,
     followed by:
       - Printable ASCII string scanning (>=6 chars), and
       - Magic-number scanning (PNG, JPEG, ZIP, RAR, PDF, GIF, ELF, MZ).
  2. Trailing data detection: bytes after the format's end-of-image marker
     (PNG IEND + CRC, JPEG EOI 0xFFD9). This is a very common low-effort
     'hide a ZIP after the picture' trick.
  3. Embedded magic-number scan over the *entire raw file* to find foreign
     formats appended or injected.
  4. Quick polyglot detection: file shows valid headers for multiple formats.

Output is human-readable so users can immediately *see* what was hidden.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .utils import to_numpy_rgb


PRINTABLE = re.compile(rb"[\x20-\x7e\t]{6,}")

MAGICS: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"PK\x03\x04", "ZIP/JAR/DOCX/XLSX"),
    (b"PK\x05\x06", "ZIP (empty)"),
    (b"Rar!\x1a\x07\x00", "RAR (v1.5)"),
    (b"Rar!\x1a\x07\x01\x00", "RAR (v5)"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (b"%PDF-", "PDF"),
    (b"GIF87a", "GIF87a"),
    (b"GIF89a", "GIF89a"),
    (b"BM", "BMP"),
    (b"RIFF", "RIFF (WebP/WAV/AVI)"),
    (b"\x1f\x8b\x08", "GZIP"),
    (b"BZh", "BZIP2"),
    (b"\x7fELF", "ELF"),
    (b"MZ", "MZ/PE (Windows EXE)"),
    (b"OggS", "OGG"),
    (b"ID3", "MP3 (ID3v2)"),
    (b"-----BEGIN ", "PEM/Key block"),
    (b"SSH PRIVATE KEY", "SSH key"),
]

# A subset of MAGICS that are long enough (>=6 bytes of content or strong
# distinctive prefix) that a random match is statistically very unlikely.
# Used in noisy contexts (LSB streams, in-file scan) to avoid false positives
# from e.g. a stray "BM" or "MZ" appearing in random pixel data.
STRONG_MAGICS: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"PK\x03\x04", "ZIP/JAR/DOCX/XLSX"),
    (b"PK\x05\x06", "ZIP (empty)"),
    (b"Rar!\x1a\x07\x00", "RAR (v1.5)"),
    (b"Rar!\x1a\x07\x01\x00", "RAR (v5)"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (b"%PDF-", "PDF"),
    (b"GIF87a", "GIF87a"),
    (b"GIF89a", "GIF89a"),
    (b"\x7fELF", "ELF"),
    (b"-----BEGIN ", "PEM/Key block"),
    (b"SSH PRIVATE KEY", "SSH key"),
]


def _scan_magic(buf: bytes, max_hits: int = 32, strong_only: bool = False) -> list[dict[str, Any]]:
    table = STRONG_MAGICS if strong_only else MAGICS
    hits: list[dict[str, Any]] = []
    for sig, name in table:
        start = 0
        while True:
            idx = buf.find(sig, start)
            if idx < 0:
                break
            hits.append({"format": name, "offset": idx, "signature": sig.hex()})
            start = idx + 1
            if len(hits) >= max_hits:
                return hits
    return hits


def _scan_strings(buf: bytes, min_len: int = 6, max_results: int = 200) -> list[str]:
    out = []
    for m in PRINTABLE.finditer(buf):
        s = m.group(0).decode("latin-1", errors="replace")
        out.append(s)
        if len(out) >= max_results:
            break
    return out


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = bits.astype(np.uint8).ravel()
    n = (bits.size // 8) * 8
    bits = bits[:n]
    packed = np.packbits(bits, bitorder="big")
    return packed.tobytes()


def _channel_orderings(arr: np.ndarray) -> dict[str, np.ndarray]:
    h, w, _ = arr.shape
    rgb = arr.transpose(2, 0, 1).reshape(3, -1)
    return {
        "R": rgb[0],
        "G": rgb[1],
        "B": rgb[2],
        "RGB": arr.reshape(-1),
        "BGR": arr[..., ::-1].reshape(-1),
    }


def _extract_lsb_streams(
    arr: np.ndarray,
    bits: tuple[int, ...] = (0, 1, 2),
    max_bytes_per_stream: int = 8192,
) -> list[dict[str, Any]]:
    streams: list[dict[str, Any]] = []
    chans = _channel_orderings(arr)
    for ch_name, data in chans.items():
        for b in bits:
            bit_plane = ((data >> b) & 1).astype(np.uint8)
            for bitorder in ("big", "little"):
                packed = np.packbits(bit_plane, bitorder=bitorder)
                buf = packed.tobytes()[:max_bytes_per_stream]
                strings = _scan_strings(buf, min_len=8, max_results=20)
                magics = _scan_magic(buf, max_hits=8, strong_only=True)
                if strings or magics:
                    streams.append({
                        "channel_order": ch_name,
                        "bit_index": b,
                        "bit_order": bitorder,
                        "strings_sample": strings[:10],
                        "magic_hits": magics,
                        "extracted_bytes": len(buf),
                    })
    return streams


def _detect_trailing_data(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    n = len(data)
    fmt = None
    eoi_offset = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt = "PNG"
        idx = data.rfind(b"IEND")
        if idx >= 0:
            eoi_offset = idx + 4 + 4
    elif data[:3] == b"\xff\xd8\xff":
        fmt = "JPEG"
        idx = data.rfind(b"\xff\xd9")
        if idx >= 0:
            eoi_offset = idx + 2
    elif data[:4] == b"GIF8":
        fmt = "GIF"
        idx = data.rfind(b"\x3b")
        if idx >= 0:
            eoi_offset = idx + 1

    if eoi_offset is None or eoi_offset >= n:
        return {"format": fmt, "trailing_bytes": 0, "preview_hex": "", "preview_text": "", "magic_in_trailing": []}

    trailing = data[eoi_offset:]
    return {
        "format": fmt,
        "image_end_offset": eoi_offset,
        "file_size": n,
        "trailing_bytes": len(trailing),
        "preview_hex": trailing[:64].hex(),
        "preview_text": trailing[:120].decode("latin-1", errors="replace"),
        "magic_in_trailing": _scan_magic(trailing, max_hits=8),
        "strings_in_trailing": _scan_strings(trailing[:65536], min_len=6, max_results=20),
    }


def analyze_extraction(path: Path) -> dict[str, Any]:
    path = Path(path)
    data = path.read_bytes()
    file_magic_hits = _scan_magic(data, max_hits=32, strong_only=True)
    trailing = _detect_trailing_data(path)

    img = Image.open(path)
    img.load()
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = to_numpy_rgb(img)
    fmt = (path.suffix.lower())
    is_lossy = fmt in {".jpg", ".jpeg"}
    streams = [] if is_lossy else _extract_lsb_streams(arr)

    score = 0.0
    evidence: list[dict[str, Any]] = []

    if trailing.get("trailing_bytes", 0) > 16:
        score = max(score, 0.85)
        evidence.append({
            "module": "extraction",
            "severity": "warning",
            "title": f"图像数据结束后存在 {trailing['trailing_bytes']} 字节的尾随数据",
            "description": (
                f"{trailing.get('format')} 数据流在偏移 {trailing.get('image_end_offset')} 处结束，"
                f"但整个文件大小为 {trailing['file_size']} 字节。"
                f"多出的数据可能隐藏了被附加的载荷（zip、压缩包、密钥或文本）。"
                f"起始字节（十六进制）：{trailing['preview_hex'][:80]}"
            ),
            "confidence": 0.85,
        })
        if trailing["magic_in_trailing"]:
            evidence.append({
                "module": "extraction",
                "severity": "error",
                "title": "图像结尾之后检测到外来文件格式",
                "description": "在尾随数据中发现了文件魔数：" 
                               + ", ".join(f"{h['format']}@+{h['offset']}" for h in trailing["magic_in_trailing"]),
                "confidence": 0.95,
            })
            score = 1.0
        if trailing.get("strings_in_trailing"):
            sample_text = "\n".join(trailing["strings_in_trailing"][:5])
            evidence.append({
                "module": "extraction",
                "severity": "info",
                "title": "图像结尾之后存在隐藏的可打印文本",
                "description": "从尾随区域恢复出的明文：\n" + sample_text[:400],
                "confidence": 0.7,
            })

    interesting_streams = []
    SECRET_KEYWORDS = re.compile(rb"(flag\{|password|secret|BEGIN |api[_-]?key|token|private)", re.IGNORECASE)
    for s in streams:
        if s.get("magic_hits"):
            score = max(score, 0.9)
            evidence.append({
                "module": "extraction",
                "severity": "warning",
                "title": f"LSB 位流中含有外来文件魔数（通道 {s['channel_order']}，第 {s['bit_index']} 位，{s['bit_order']} 字节序）",
                "description": "在 LSB 提取的位流中发现了文件格式签名：" 
                               + ", ".join(f"{h['format']}@+{h['offset']}" for h in s["magic_hits"]),
                "confidence": 0.8,
            })
            interesting_streams.append(s)
        elif s.get("strings_sample"):
            long_strings = [t for t in s["strings_sample"] if len(t) >= 20]
            looks_meaningful = any(
                sum(c.isalpha() for c in t) >= len(t) * 0.6 for t in long_strings
            )
            sensitive = any(SECRET_KEYWORDS.search(t.encode("latin-1", errors="ignore")) for t in long_strings)
            if sensitive:
                sample = next(t for t in long_strings if SECRET_KEYWORDS.search(t.encode("latin-1", errors="ignore")))
                score = max(score, 0.85)
                evidence.append({
                    "module": "extraction",
                    "severity": "warning",
                    "title": f"LSB 位流中发现敏感关键词（通道 {s['channel_order']}，第 {s['bit_index']} 位，{s['bit_order']} 字节序）",
                    "description": "隐藏的文本载荷中包含敏感关键词（flag{}、password、BEGIN、api_key 等）：" 
                                   + (sample[:200] + ("..." if len(sample) > 200 else "")),
                    "confidence": 0.75,
                })
                interesting_streams.append(s)
            elif looks_meaningful:
                sample = long_strings[0]
                score = max(score, 0.5)
                evidence.append({
                    "module": "extraction",
                    "severity": "info",
                    "title": f"LSB 位流中发现可打印字符串（通道 {s['channel_order']}，第 {s['bit_index']} 位，{s['bit_order']} 字节序）",
                    "description": "可能的文本载荷：" + (sample[:160] + ("..." if len(sample) > 160 else "")),
                    "confidence": 0.4,
                })
                interesting_streams.append(s)

    extra_magic_in_file = [h for h in file_magic_hits if h["offset"] not in (0,)]
    if any(h["format"].startswith("ZIP") for h in extra_magic_in_file):
        score = max(score, 0.85)
        evidence.append({
            "module": "extraction",
            "severity": "warning",
            "title": "文件主体内部发现 ZIP 签名",
            "description": "在文件内部发现了 'PK\\x03\\x04' 头，这通常意味着嵌入了 zip / docx / jar 载荷（多格式拼接文件或被附加的压缩包）。",
            "confidence": 0.7,
        })

    if score > 0.6:
        risk = "HIGH"
    elif score > 0.3:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "trailing_data": trailing,
        "file_magic_hits": file_magic_hits,
        "lsb_streams_with_findings": interesting_streams[:20],
        "extraction_score": float(score),
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "LSB 提取尝试了 zsteg 风格的常见 比特位 / 通道 / 字节序 组合，但并不穷尽所有方案。",
            "如果隐藏数据被加密或压缩，将不会出现可读字符串或文件魔数，本工具检测不到。",
            "JPEG 等有损格式不在 LSB 提取范围内（压缩本身就会破坏 LSB）。",
        ],
    }
