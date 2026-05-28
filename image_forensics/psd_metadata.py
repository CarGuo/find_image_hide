"""Adobe Photoshop (PSD/PSB) metadata extractor.

PSD 文件结构：
  - File header (26 bytes, magic "8BPS")
  - Color mode data section: u32 length + data
  - **Image Resources section**: u32 length + 一组 Image Resource Blocks (IRB)
  - Layer & Mask info section
  - Image Data section

每个 IRB:
  - signature (4 bytes) = "8BIM"
  - id (u16, big-endian)
  - pascal_name (1 byte length + name + pad to even)
  - size (u32, big-endian)
  - data (size bytes, padded to even)

我们关心的 IRB ID：
  0x0404 (1028) = IPTC-NAA (IPTC IIM block)
  0x0424 (1060) = XMP metadata (UTF-8 XML)
  0x040B (1035) = URL (UTF-16BE)
  0x040F (1039) = ICC profile
  0x041A (1050) = Slices
  0x0421 (1057) = Version Info（含 Photoshop 版本字符串）
  0x0426 (1062) = Print scale
  0x0428 (1064) = Pixel Aspect Ratio
  0x040A (1034) = Copyright flag (1 byte: 0/1, 是否有版权)
  0x03ED (1005) = Resolution info

IPTC IIM 块进一步用 record/dataset 编码：
  每个 dataset:
    0x1C marker (1 byte)
    record (u8)  -- record 1=Envelope, 2=Application
    dataset (u8) -- 数据集 ID（例如 116=CopyrightNotice）
    length (u16 big-endian, 高位 bit=1 时为扩展长度)
    payload (length bytes)
  我们只关心 record=2 的部分（Application Record）。
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

# IPTC IIM Application Record（record 2）里我们关心的 dataset → 语义名
_IPTC_DATASETS = {
    5:   "Title",                  # Object Name
    25:  "Keywords",
    40:  "Instructions",           # Special Instructions
    55:  "DateCreated",
    80:  "Creator",                # By-line
    85:  "CreatorJobTitle",        # By-line Title
    90:  "City",
    92:  "Sublocation",
    95:  "ProvinceState",
    101: "Country",
    103: "TransmissionReference",
    105: "Headline",
    110: "Credit",
    115: "Source",
    116: "CopyrightNotice",
    118: "Contact",
    120: "Description",            # Caption / Abstract
    122: "DescriptionWriter",
}


def _read_pascal(buf: bytes, off: int) -> tuple[str, int]:
    """Read 1-byte-length Pascal string with padding to even-byte boundary."""
    n = buf[off]
    raw = buf[off + 1: off + 1 + n]
    consumed = 1 + n
    # 整体长度（含 length 字节）必须 padding 到偶数
    if consumed % 2 != 0:
        consumed += 1
    try:
        s = raw.decode("utf-8", errors="replace")
    except Exception:
        s = raw.decode("latin-1", errors="replace")
    return s, off + consumed


def _is_psd(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"8BPS"
    except Exception:
        return False


def _parse_header(f) -> dict[str, Any] | None:
    head = f.read(26)
    if len(head) < 26 or head[:4] != b"8BPS":
        return None
    # signature(4) + version(2) + reserved(6) + channels(2)
    # + height(4) + width(4) + depth(2) + color_mode(2)
    version = struct.unpack(">H", head[4:6])[0]
    channels, height, width, depth, color_mode = struct.unpack(
        ">HIIHH", head[12:26]
    )
    color_mode_name = {
        0: "Bitmap", 1: "Grayscale", 2: "Indexed", 3: "RGB",
        4: "CMYK", 7: "Multichannel", 8: "Duotone", 9: "Lab",
    }.get(color_mode, f"Unknown({color_mode})")
    return {
        "is_psb": version == 2,                # PSB（>30000 px / 2 GB）
        "channels": channels,
        "width": width,
        "height": height,
        "depth": depth,                          # 1/8/16/32 bits per channel
        "color_mode": color_mode_name,
    }


def _parse_iptc_iim(blob: bytes) -> dict[str, Any]:
    """Parse a IPTC-IIM Application Record buffer into {semantic: value}."""
    out: dict[str, list[str]] = {}
    i = 0
    n = len(blob)
    while i + 5 <= n:
        if blob[i] != 0x1C:
            i += 1
            continue
        record = blob[i + 1]
        dataset = blob[i + 2]
        length = struct.unpack(">H", blob[i + 3: i + 5])[0]
        i += 5
        # 扩展长度：最高 bit 置位时，length 字段实际是后续长度字节数
        if length & 0x8000:
            ext_len = length & 0x7FFF
            if i + ext_len > n:
                break
            length = int.from_bytes(blob[i: i + ext_len], "big")
            i += ext_len
        payload = blob[i: i + length]
        i += length
        if record != 2:
            continue
        name = _IPTC_DATASETS.get(dataset)
        if not name:
            continue
        try:
            text = payload.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception:
            text = payload.decode("latin-1", errors="replace").strip("\x00").strip()
        if not text:
            continue
        out.setdefault(name, []).append(text)
    # 归一：单值字段去掉 list
    flat: dict[str, Any] = {}
    for k, vs in out.items():
        flat[k] = vs[0] if len(vs) == 1 else vs
    return flat


def _parse_version_info(blob: bytes) -> dict[str, Any]:
    """Image Resource ID 0x0421: Version Info.

    Layout (big-endian):
      version (u32)
      hasRealMergedData (u8)
      writer name (Unicode string: u32 len + UTF-16BE chars)
      reader name (Unicode string: u32 len + UTF-16BE chars)
      file version (u32)
    """
    out: dict[str, Any] = {}
    try:
        if len(blob) < 9:
            return out
        out["version"] = struct.unpack(">I", blob[:4])[0]
        out["has_real_merged_data"] = bool(blob[4])
        i = 5

        def read_unicode(buf: bytes, off: int) -> tuple[str, int]:
            n = struct.unpack(">I", buf[off: off + 4])[0]
            off += 4
            raw = buf[off: off + n * 2]
            try:
                s = raw.decode("utf-16-be", errors="replace").rstrip("\x00")
            except Exception:
                s = raw.decode("latin-1", errors="replace")
            return s, off + n * 2

        writer, i = read_unicode(blob, i)
        reader, i = read_unicode(blob, i)
        out["writer"] = writer
        out["reader"] = reader
        if i + 4 <= len(blob):
            out["file_version"] = struct.unpack(">I", blob[i: i + 4])[0]
    except Exception:
        pass
    return out


def _parse_resolution_info(blob: bytes) -> dict[str, Any]:
    """ID 0x03ED: ResolutionInfo, 16 bytes (big-endian fixed-point + units)."""
    out: dict[str, Any] = {}
    try:
        if len(blob) < 16:
            return out
        h_res = struct.unpack(">i", blob[0:4])[0] / 65536.0
        h_unit, h_disp_unit = struct.unpack(">HH", blob[4:8])
        v_res = struct.unpack(">i", blob[8:12])[0] / 65536.0
        v_unit, v_disp_unit = struct.unpack(">HH", blob[12:16])
        out = {
            "h_res": h_res, "h_unit": h_unit, "h_display_unit": h_disp_unit,
            "v_res": v_res, "v_unit": v_unit, "v_display_unit": v_disp_unit,
        }
    except Exception:
        pass
    return out


def parse_psd_metadata(path: str | Path) -> dict[str, Any]:
    """Read selected Image Resource Blocks from a PSD/PSB file.

    Returns a dict with keys:
      - header: parsed PSD header (width/height/depth/color_mode/is_psb)
      - iptc_iim: dict[semantic_name -> str|list[str]]  （来自 IRB 1028）
      - xmp: 完整 XMP XML 字符串（来自 IRB 1060）
      - url: 文档来源 URL（来自 IRB 1035）
      - has_icc_profile: bool（来自 IRB 1039）
      - copyright_flag: bool|None（来自 IRB 1034）
      - version_info: {writer, reader, version, file_version}（来自 IRB 1057）
      - resolution: ResolutionInfo（来自 IRB 1005）
      - resource_ids: list[int] 全部检测到的 IRB ID

    解析失败或非 PSD 时返回空 dict（caller 用 .get(...) 即可）。
    """
    path = Path(path)
    if not _is_psd(path):
        return {}

    try:
        with path.open("rb") as f:
            header = _parse_header(f)
            if not header:
                return {}

            # color mode data section
            cmd_len = struct.unpack(">I", f.read(4))[0]
            f.seek(cmd_len, 1)

            # image resources section
            irs_len = struct.unpack(">I", f.read(4))[0]
            irs = f.read(irs_len)
    except Exception:
        return {"header": None, "error": "psd_io_failed"}

    out: dict[str, Any] = {"header": header, "resource_ids": []}
    i = 0
    n = len(irs)
    while i + 12 <= n:
        if irs[i: i + 4] != b"8BIM":
            break
        rid = struct.unpack(">H", irs[i + 4: i + 6])[0]
        # Pascal name
        _name, after_name = _read_pascal(irs, i + 6)
        if after_name + 4 > n:
            break
        size = struct.unpack(">I", irs[after_name: after_name + 4])[0]
        data_off = after_name + 4
        data_end = data_off + size
        if data_end > n:
            break
        blob = irs[data_off: data_end]
        # 数据段 padding 到偶数
        next_off = data_end + (data_end % 2)
        out["resource_ids"].append(rid)

        if rid == 0x0404:  # IPTC-NAA
            try:
                out["iptc_iim"] = _parse_iptc_iim(blob)
            except Exception:
                pass
        elif rid == 0x0424:  # XMP
            try:
                out["xmp"] = blob.decode("utf-8", errors="replace")
            except Exception:
                out["xmp"] = blob.decode("latin-1", errors="replace")
        elif rid == 0x040B:  # URL (UTF-16BE)
            try:
                out["url"] = blob.decode("utf-16-be", errors="replace").rstrip("\x00")
            except Exception:
                pass
        elif rid == 0x040F:  # ICC profile
            out["has_icc_profile"] = True
            out["icc_profile_size"] = len(blob)
        elif rid == 0x040A:  # Copyright flag
            out["copyright_flag"] = bool(blob[0]) if blob else None
        elif rid == 0x0421:  # Version Info
            try:
                out["version_info"] = _parse_version_info(blob)
            except Exception:
                pass
        elif rid == 0x03ED:  # Resolution Info
            try:
                out["resolution"] = _parse_resolution_info(blob)
            except Exception:
                pass

        i = next_off

    return out
