"""隐形水印（invisible-watermark / DwtDct）检测模块。

背景：
  Stable Diffusion XL / 一些版权保护工具默认会在出图时通过频域 DWT+DCT 嵌入
  32-bit 隐形水印（典型字符串如 "SDV2"、"OK"、自定义 UUID 等）。
  invisible-watermark 库 (github.com/ShieldMnt/invisible-watermark) 是这类
  水印的事实标准。

本模块做了什么：
  - 优先用 imwatermark.WatermarkDecoder 在 dwtDct 频域解 32-bit；
  - 解码出来的字节如果是可打印文本 / 与已知水印字典匹配 → 高置信版权信号；
  - 否则保留 raw_bytes_hex + 熵 + ASCII 比例，做 medium 提示；
  - 失败 / 库不可用 → 优雅降级 status=UNAVAILABLE / NO_HIT。

局限：
  - dwtDct 对 resize/crop 鲁棒性弱，攻击者改尺寸即可破坏；
  - 32-bit 容量小，碰撞误报存在，所以本模块只在解出**可打印文本**或匹配已知字典时
    给 high；其它视为弱信号；
  - 解码代价 ~150ms / 1080p 图，CPU 直跑可接受。
"""
from __future__ import annotations

import importlib.util
import math
import re
import string
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# 已知水印文本字典（社区常见 + Stability AI 官方）
_KNOWN_INVISIBLE_WATERMARKS = {
    "sdv2": "Stable Diffusion v2.x 默认水印",
    "ok": "invisible-watermark 测试默认值",
    "test": "invisible-watermark 文档示例水印",
    "stably": "Stability AI",
    "sdxl": "Stable Diffusion XL 系列",
    "ai": "通用 AI 出图水印",
    "imatag": "ImaTag 商业水印",
    "shieldmnt": "ShieldMnt invisible-watermark 项目自检",
    "acme": "演示用自定义水印（ACME 测试样例）",
}

# 二进制片段（ASCII / UTF-8 编码后的 bytes 子串）—— 即使 payload 因为 JPEG 重压缩
# 不是规整可打印的整段文本，只要 raw bytes 里含有这些子串，也认定为命中。
_KNOWN_BINARY_FRAGMENTS = {
    key.encode("ascii"): (key, label)
    for key, label in _KNOWN_INVISIBLE_WATERMARKS.items()
    if len(key) >= 3
}

# 候选解码方法：顺序很重要，dwtDct 最快
_METHODS = ["dwtDct", "dwtDctSvd"]
# 候选位长，覆盖 SDV2(48) / SDXL(48) / 标准 32 / 64
_BIT_LENS = [32, 48, 64]

_PRINTABLE = set(string.printable) - set("\t\n\r\x0b\x0c")


def _imwatermark_available():
    if importlib.util.find_spec("imwatermark") is None:
        return None
    if importlib.util.find_spec("cv2") is None:
        return None
    try:
        from imwatermark import WatermarkDecoder  # type: ignore
        import cv2  # type: ignore
        return WatermarkDecoder, cv2
    except Exception:
        return None


def _printable_ratio(bs: bytes) -> float:
    if not bs:
        return 0.0
    return sum(1 for b in bs if chr(b) in _PRINTABLE) / len(bs)


def _shannon_entropy(bs: bytes) -> float:
    if not bs:
        return 0.0
    counts = np.bincount(np.frombuffer(bs, dtype=np.uint8), minlength=256)
    probs = counts / counts.sum()
    nz = probs[probs > 0]
    return float(-(nz * np.log2(nz)).sum())


def _try_decode_text(raw: bytes) -> tuple[str | None, float]:
    """尝试把 raw bytes 解释成 ASCII / UTF-8 文本，返回 (text or None, printable_ratio).

    阈值收紧（避免短噪声误报）：
      - printable_ratio ≥ 0.8（更严格）
      - cleaned 至少 4 个字符
      - cleaned 至少包含 2 个字母（纯数字 / 单字母不算）
      - 32-bit 解码出来全 0 / 全 0xFF 这类显然伪随机的字节直接丢弃
    """
    if not raw:
        return None, 0.0
    if len(set(raw)) <= 1:
        return None, 0.0
    pr = _printable_ratio(raw)
    if pr < 0.8:
        return None, pr
    try:
        txt = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            txt = raw.decode("ascii", errors="strict")
        except Exception:
            return None, pr
    cleaned = "".join(ch for ch in txt if ch in _PRINTABLE).strip()
    if len(cleaned) < 4:
        return None, pr
    letter_count = sum(1 for ch in cleaned if ch.isalpha())
    if letter_count < 2:
        return None, pr
    return cleaned, pr


def _match_known(text: str) -> tuple[str, str] | None:
    low = (text or "").strip().lower()
    if not low:
        return None
    for key, label in _KNOWN_INVISIBLE_WATERMARKS.items():
        if key in low:
            return key, label
    if re.fullmatch(r"[A-Za-z0-9_\-]{3,16}", text or ""):
        return None
    return None


def analyze_invisible_watermark(path: Path) -> dict[str, Any]:
    backend = _imwatermark_available()
    if backend is None:
        return {
            "status": "UNAVAILABLE",
            "risk_level": "UNKNOWN",
            "score": 0.0,
            "decoded": [],
            "evidence_items": [],
            "limitations": [
                "未安装 invisible-watermark 或 opencv-python，已跳过隐形水印检测；可执行 `pip install invisible-watermark opencv-python` 启用。",
            ],
            "note": "隐形水印解码需要 imwatermark + cv2，当前环境缺包。",
        }
    WatermarkDecoder, cv2 = backend

    try:
        with Image.open(path) as im:
            im.load()
            rgb = im.convert("RGB")
            arr = np.array(rgb)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        return {
            "status": "ERROR",
            "risk_level": "UNKNOWN",
            "score": 0.0,
            "decoded": [],
            "evidence_items": [],
            "error": f"open_failed: {exc}",
            "limitations": ["图像无法被 PIL/cv2 读取，已跳过。"],
        }

    h, w = bgr.shape[:2]
    if min(h, w) < 256:
        return {
            "status": "TOO_SMALL",
            "risk_level": "LOW",
            "score": 0.0,
            "decoded": [],
            "evidence_items": [],
            "limitations": [
                f"图像分辨率过小（{w}x{h}），dwtDct 至少要 256px 才能给出可信解码结果。",
            ],
        }

    decoded: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    best_text: str | None = None
    best_known: tuple[str, str] | None = None

    for method in _METHODS:
        for bits in _BIT_LENS:
            try:
                dec = WatermarkDecoder("bytes", bits)
                raw_bits = dec.decode(bgr, method)
            except Exception as exc:
                decoded.append({
                    "method": method,
                    "bit_len": bits,
                    "error": str(exc),
                })
                continue
            try:
                if isinstance(raw_bits, (bytes, bytearray)):
                    raw = bytes(raw_bits)
                else:
                    arr_bits = np.asarray(raw_bits, dtype=np.uint8).flatten()
                    if arr_bits.size and arr_bits.max() <= 1:
                        pad = (-arr_bits.size) % 8
                        if pad:
                            arr_bits = np.concatenate([arr_bits, np.zeros(pad, dtype=np.uint8)])
                        raw = bytes(np.packbits(arr_bits))
                    else:
                        raw = bytes(arr_bits.tolist())
            except Exception:
                raw = b""

            if not raw:
                continue

            text, pr = _try_decode_text(raw)
            entry: dict[str, Any] = {
                "method": method,
                "bit_len": bits,
                "raw_bytes_hex": raw.hex(),
                "printable_ratio": round(pr, 3),
                "shannon_entropy": round(_shannon_entropy(raw), 3),
                "text": text,
            }
            if text:
                known = _match_known(text)
                if known:
                    entry["known_match"] = {"key": known[0], "label": known[1]}
                    if best_known is None:
                        best_known = known
                if best_text is None and len(text) >= 2:
                    best_text = text
            else:
                # 文本通道没解出来，看二进制子串里是否藏了已知 payload
                # （JPEG 重压缩后 payload 可能不再整段对齐，但子串通常仍可见）
                for frag, (key, label) in _KNOWN_BINARY_FRAGMENTS.items():
                    if frag in raw:
                        entry["known_binary_match"] = {"key": key, "label": label}
                        if best_known is None:
                            best_known = (key, label)
                        if best_text is None:
                            best_text = key
                        break
            decoded.append(entry)

    score = 0.0
    risk = "LOW"
    if best_known:
        score = 0.95
        risk = "HIGH"
        evidence_items.append({
            "module": "invisible_watermark",
            "severity": "high",
            "title": f"隐形水印（DwtDct）命中已知字典：{best_known[0]}",
            "description": f"{best_known[1]}（解出文本：{best_text or best_known[0]}）。该图很可能由 invisible-watermark 体系嵌入版权 / 模型水印。",
            "confidence": 0.9,
        })
    elif best_text:
        score = 0.55
        risk = "MEDIUM"
        evidence_items.append({
            "module": "invisible_watermark",
            "severity": "medium",
            "title": "隐形水印（DwtDct）解出可打印文本",
            "description": f"解出文本：{best_text}。文本未匹配已知字典，可能为自定义版权 / 用户级水印，建议人工核对。",
            "confidence": 0.55,
        })

    return {
        "status": "OK" if best_text or best_known else "NO_HIT",
        "risk_level": risk,
        "score": round(score, 3),
        "decoded": decoded,
        "best_text": best_text,
        "best_known_match": ({"key": best_known[0], "label": best_known[1]} if best_known else None),
        "evidence_items": evidence_items,
        "limitations": [
            "DwtDct 隐形水印对 resize / 大幅 crop / 旋转鲁棒性弱，攻击者改尺寸即可破坏。",
            "32 / 48 bits 容量小，碰撞误报无法完全避免；本模块仅在解出可打印文本或命中字典时给中 / 高风险。",
            "若图片本身没有嵌入隐形水印，解码会得到伪随机字节，本模块会按熵 / 可打印率过滤掉。",
        ],
    }
