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

from .utils import to_numpy_rgb, is_lossy_format


# Magic prefixes worth checking when reading the *first N pixels' LSB* of an
# image. This is exactly how zsteg / stegoVeritas treats sequential-LSB
# payloads: small payloads (a few dozen bytes) hidden in the leading pixels
# can never be seen on a global LSB bit-plane image, but they can be detected
# in a few microseconds by reading the first 128-512 pixels' LSB and matching
# a magic prefix.
LSB_HEADER_MAGICS: list[tuple[bytes, str]] = [
    (b"GSY", "GSY (custom marker)"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"PK\x03\x04", "ZIP"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"%PDF-", "PDF"),
    (b"GIF87a", "GIF87a"),
    (b"GIF89a", "GIF89a"),
    (b"BM", "BMP"),
    (b"MZ", "MZ/PE"),
    (b"\x7fELF", "ELF"),
    (b"flag{", "flag{...}"),
    (b"FLAG{", "FLAG{...}"),
    (b"-----BEGIN ", "PEM/Key block"),
]


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


def _detect_mpf_container(data: bytes) -> dict[str, Any] | None:
    """识别 CIPA MPF / MPO 多帧 JPEG 容器。

    华为 / 三星 / iPhone 双摄、人像景深、Apple LivePhoto 第一帧等都会产生
    MPF (Multi-Picture Format, CIPA DC-007)：在 APP2 段塞一个 'MPF\\x00' 头，
    紧接着一个或多个完整的 JPEG（FFD8...FFD9）首尾相接。

    很多取证工具（包括我们之前的实现）会把第一个 EOI 之后的 'FFD8FF' 当成
    "trailing JPEG" 报警，但这其实是合法的 MPO 多帧。这里检测 MPF 标识 +
    第二帧 SOI 紧跟首 EOI，命中即视为合法多帧容器，不应升级风险。
    """
    if not (data.startswith(b"\xff\xd8\xff")):
        return None
    has_mpf = b"MPF\x00" in data[:65536]
    first_eoi = data.find(b"\xff\xd9")
    second_soi = -1
    if first_eoi >= 0 and first_eoi + 2 < len(data):
        # 允许 MPF 索引段与 padding 出现在 EOI 与第二个 SOI 之间。
        nxt = data.find(b"\xff\xd8\xff", first_eoi + 2)
        if 0 <= nxt - (first_eoi + 2) <= 4096:
            second_soi = nxt
    if not (has_mpf or second_soi >= 0):
        return None
    # 找到所有 SOI/EOI 对，统计帧数
    frames: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(data):
        soi = data.find(b"\xff\xd8\xff", cursor)
        if soi < 0:
            break
        eoi = data.find(b"\xff\xd9", soi + 3)
        if eoi < 0:
            break
        frames.append((soi, eoi + 2))
        cursor = eoi + 2
        if len(frames) >= 8:
            break
    return {
        "is_mpf": True,
        "has_mpf_marker": has_mpf,
        "frame_count": len(frames),
        "frames": [{"start": s, "end": e, "size": e - s} for s, e in frames],
    }


def _scan_lsb_magic_header(arr: np.ndarray, n_pixels: int = 256) -> list[dict[str, Any]]:
    """读取前 n_pixels 像素的 RGB 最低位，按 zsteg 风格的多种顺序匹配 magic 头。

    动机：用户场景里"把 GSY\\0 写进图片前 11 个像素的 RGB LSB"这种顺序 bit
    payload，整图 LSB 位平面图根本看不出来（32 bit / 千万像素 ≈ 0），但用
    代码顺序读前 N 像素 LSB → packbits → 匹配 magic prefix，可以瞬间命中。

    这正是 zsteg 默认会做的 b1, lsb, xy / yx 等多种轨道扫描的最小子集。
    """
    if arr.ndim != 3 or arr.shape[2] < 3:
        return []
    h, w, _ = arr.shape
    n_pixels = min(n_pixels, h * w)
    flat = arr.reshape(-1, 3)[:n_pixels]
    rgb_interleave = flat.reshape(-1) & 1            # R0,G0,B0,R1,G1,B1,...
    bgr_interleave = flat[:, ::-1].reshape(-1) & 1   # B0,G0,R0,B1,...
    r_only = flat[:, 0] & 1
    g_only = flat[:, 1] & 1
    b_only = flat[:, 2] & 1

    tracks: list[tuple[str, np.ndarray]] = [
        ("RGB-interleave / MSB-first", rgb_interleave),
        ("BGR-interleave / MSB-first", bgr_interleave),
        ("R-only / MSB-first", r_only),
        ("G-only / MSB-first", g_only),
        ("B-only / MSB-first", b_only),
    ]

    hits: list[dict[str, Any]] = []
    for label, bits in tracks:
        for bitorder in ("big", "little"):
            buf = np.packbits(bits.astype(np.uint8), bitorder=bitorder).tobytes()
            for sig, name in LSB_HEADER_MAGICS:
                if buf.startswith(sig):
                    hits.append({
                        "track": f"{label} ({bitorder}-endian)",
                        "magic": name,
                        "head_hex": buf[:32].hex(),
                        "head_text": buf[:32].decode("latin-1", errors="replace"),
                    })
                    break
    return hits


def _detect_trailing_data(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    n = len(data)
    fmt = None
    eoi_offset = None
    mpf_info = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt = "PNG"
        idx = data.rfind(b"IEND")
        if idx >= 0:
            eoi_offset = idx + 4 + 4
    elif data[:3] == b"\xff\xd8\xff":
        fmt = "JPEG"
        mpf_info = _detect_mpf_container(data)
        if mpf_info and mpf_info.get("frame_count", 0) >= 2:
            # 合法多帧 MPO/MPF 容器：用最后一帧的 EOI 作为 image-end，
            # trailing 区只统计最后一帧之后的内容。
            last_frame_end = mpf_info["frames"][-1]["end"]
            eoi_offset = last_frame_end
        else:
            idx = data.rfind(b"\xff\xd9")
            if idx >= 0:
                eoi_offset = idx + 2
    elif data[:4] == b"GIF8":
        fmt = "GIF"
        idx = data.rfind(b"\x3b")
        if idx >= 0:
            eoi_offset = idx + 1

    if eoi_offset is None or eoi_offset >= n:
        return {
            "format": fmt,
            "trailing_bytes": 0,
            "preview_hex": "",
            "preview_text": "",
            "magic_in_trailing": [],
            "mpf_container": mpf_info,
        }

    trailing = data[eoi_offset:]
    return {
        "format": fmt,
        "image_end_offset": eoi_offset,
        "file_size": n,
        "trailing_bytes": len(trailing),
        "preview_hex": trailing[:64].hex(),
        "preview_text": trailing[:120].decode("latin-1", errors="replace"),
        # strong_only=True：尾随区里的 'BM' / 'MZ' 这种 2 字节短 magic 在
        # 1MB 随机字节中期望命中 ≈ 16 次，纯统计噪声，不应作为证据。
        "magic_in_trailing": _scan_magic(trailing, max_hits=8, strong_only=True),
        "strings_in_trailing": _scan_strings(trailing[:65536], min_len=6, max_results=20),
        "mpf_container": mpf_info,
    }


def analyze_extraction(path: Path) -> dict[str, Any]:
    path = Path(path)
    data = path.read_bytes()
    file_magic_hits = _scan_magic(data, max_hits=32, strong_only=True)
    trailing = _detect_trailing_data(path)
    mpf_info = trailing.get("mpf_container")

    img = Image.open(path)
    img.load()
    pil_format = (img.format or "").upper()
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = to_numpy_rgb(img)
    # 用 PIL 探测出的真实格式，而不是仅凭后缀。MPO/HEIC/AVIF 一律视为 lossy。
    is_lossy = is_lossy_format(pil_format)
    streams = [] if is_lossy else _extract_lsb_streams(arr)
    # 即使是 lossy 容器，也对前 256 像素做"小 payload magic 头扫描"——
    # 因为前 N 像素的 LSB 在大多数 JPEG quality≥85 下还能保留少量原始信息，
    # 且这种扫描成本极低、误报极低（要求恰好以已知 magic 起头）。
    lsb_header_hits = _scan_lsb_magic_header(arr, n_pixels=256)

    score = 0.0
    evidence: list[dict[str, Any]] = []

    # MPO/MPF 合法多帧：把"trailing JPEG"提示降为 info，并避免升级。
    is_mpf = bool(mpf_info and mpf_info.get("frame_count", 0) >= 2)
    if is_mpf:
        evidence.append({
            "module": "extraction",
            "severity": "info",
            "title": (
                f"识别为 CIPA MPF / MPO 多帧 JPEG 容器（共 {mpf_info['frame_count']} 帧）"
            ),
            "description": (
                "这是华为/三星/iPhone 双摄、人像景深、Apple LivePhoto 等设备产生的合法标准容器，"
                "其内部 'FFD8FF...FFD9 + FFD8FF...FFD9' 结构不是隐写或附加文件，"
                "已自动从 trailing-data 升级判定中排除。"
            ),
            "confidence": 0.9,
        })

    if trailing.get("trailing_bytes", 0) > 16 and not is_mpf:
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
            seen: set[tuple[str, int]] = set()
            unique_hits = []
            for h in trailing["magic_in_trailing"]:
                key = (h["format"], h["offset"])
                if key in seen:
                    continue
                seen.add(key)
                unique_hits.append(h)
            evidence.append({
                "module": "extraction",
                "severity": "error",
                "title": "图像结尾之后检测到外来文件格式",
                "description": "在尾随数据中发现了文件魔数："
                               + ", ".join(f"{h['format']}@+{h['offset']}" for h in unique_hits),
                "confidence": 0.95,
            })
            # 之前直接 score = 1.0 会无条件覆盖更可靠的低分判据；改为 max。
            score = max(score, 0.95)
        if trailing.get("strings_in_trailing"):
            sample_text = "\n".join(trailing["strings_in_trailing"][:5])
            evidence.append({
                "module": "extraction",
                "severity": "info",
                "title": "图像结尾之后存在隐藏的可打印文本",
                "description": "从尾随区域恢复出的明文：\n" + sample_text[:400],
                "confidence": 0.7,
            })

    # 顺序 LSB header 扫描——专治"小 payload 藏在前 N 像素 LSB"
    if lsb_header_hits:
        # 去重（同一 magic 多种轨道命中只保留首条最显著的）
        seen_magic: set[str] = set()
        unique_lsb_hits = []
        for h in lsb_header_hits:
            if h["magic"] in seen_magic:
                continue
            seen_magic.add(h["magic"])
            unique_lsb_hits.append(h)
        score = max(score, 0.9)
        evidence.append({
            "module": "extraction",
            "severity": "warning",
            "title": "图像前若干像素的 LSB 中检测到已知文件 / 标志魔数",
            "description": (
                "顺序读取前 256 像素的 RGB 最低位、按 zsteg 风格的多种轨道拼接为字节流后，"
                "在某些轨道的开头匹配到已知 magic，强烈提示存在『顺序 bit LSB 隐写』。"
                "命中详情：\n"
                + "\n".join(
                    f"- 轨道 {h['track']}：识别为 {h['magic']}；前 32 字节 hex={h['head_hex']}；text={h['head_text']}"
                    for h in unique_lsb_hits
                )
            ),
            "confidence": 0.9,
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

    # 文件主体内的 ZIP 签名：MPF 容器内允许 (APP2/属性段会带 PK)，但仍提示
    extra_magic_in_file = [h for h in file_magic_hits if h["offset"] not in (0,)]
    if any(h["format"].startswith("ZIP") for h in extra_magic_in_file) and not is_mpf:
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
        "lsb_header_magic_hits": lsb_header_hits,
        "mpf_container": mpf_info,
        "extraction_score": float(score),
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "LSB 提取尝试了 zsteg 风格的常见 比特位 / 通道 / 字节序 组合，但并不穷尽所有方案。",
            "如果隐藏数据被加密或压缩，将不会出现可读字符串或文件魔数，本工具检测不到。",
            "JPEG / MPO / HEIC / AVIF 等有损格式不会做整图 LSB 位流提取（压缩本身就会破坏 LSB），但仍会做前 N 像素的 magic-header 顺序扫描。",
            "MPO / MPF 多帧容器（华为 / 三星 / iPhone 双摄、人像景深）已识别为合法标准结构，不会作为 trailing-data 升级风险。",
        ],
    }
