"""LSB bit-plane analysis."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .utils import safe_open_rgb, to_numpy_rgb


def _shannon_entropy(bits: np.ndarray) -> float:
    if bits.size == 0:
        return 0.0
    p1 = float(bits.mean())
    p0 = 1.0 - p1
    h = 0.0
    for p in (p0, p1):
        if p > 0:
            h -= p * math.log2(p)
    return h


def _neighborhood_correlation(bits: np.ndarray) -> float:
    if bits.shape[0] < 2 or bits.shape[1] < 2:
        return 0.0
    a = bits[:, :-1].astype(np.int8)
    b = bits[:, 1:].astype(np.int8)
    same = (a == b).mean()
    return float(same)


def analyze_lsb(path: Path, vis_dir: Path, is_lossy: bool) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img)

    bits_r = arr[..., 0] & 1
    bits_g = arr[..., 1] & 1
    bits_b = arr[..., 2] & 1

    Image.fromarray((bits_r * 255).astype(np.uint8)).save(vis_dir / "lsb_r.png")
    Image.fromarray((bits_g * 255).astype(np.uint8)).save(vis_dir / "lsb_g.png")
    Image.fromarray((bits_b * 255).astype(np.uint8)).save(vis_dir / "lsb_b.png")

    entropy = {
        "r": _shannon_entropy(bits_r),
        "g": _shannon_entropy(bits_g),
        "b": _shannon_entropy(bits_b),
    }
    balance = {
        "r": float(bits_r.mean()),
        "g": float(bits_g.mean()),
        "b": float(bits_b.mean()),
    }
    corr = {
        "r": _neighborhood_correlation(bits_r),
        "g": _neighborhood_correlation(bits_g),
        "b": _neighborhood_correlation(bits_b),
    }

    avg_entropy = sum(entropy.values()) / 3.0
    avg_balance_diff = sum(abs(v - 0.5) for v in balance.values()) / 3.0
    avg_corr = sum(corr.values()) / 3.0

    randomness_score = float(min(1.0, avg_entropy * (1.0 - avg_balance_diff * 2.0)))
    randomness_score = max(0.0, randomness_score)

    suspicious = (avg_entropy > 0.999) and (avg_corr < 0.505) and (avg_balance_diff < 0.005)
    # Very strong signal: LSB plane is statistically white noise on ALL three
    # channels. This is the unmistakable footprint of full-LSB replacement
    # steganography (or LSB-randomization), and is what tools like StegSecret
    # / stegdetect's basic LSB test flag.
    all_channels_white_noise = (
        all(e > 0.9999 for e in entropy.values())
        and all(0.495 <= c <= 0.510 for c in corr.values())
        and all(abs(v - 0.5) < 0.005 for v in balance.values())
    )
    base_anomaly = 0.0
    if all_channels_white_noise:
        base_anomaly = 0.95
    elif suspicious:
        base_anomaly = 0.6
    elif avg_entropy > 0.99 and avg_corr < 0.51 and avg_balance_diff < 0.01:
        base_anomaly = 0.35

    if is_lossy:
        base_anomaly *= 0.3

    if base_anomaly > 0.85 and not is_lossy:
        risk = "HIGH"
    elif base_anomaly > 0.55:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence = []
    if suspicious and not is_lossy:
        evidence.append({
            "module": "lsb",
            "severity": "warning",
            "title": "LSB 位平面呈现高度随机",
            "description": "最低有效位平面的熵接近最大值，且空间相关性非常低，这在自然图像中并不常见。此现象是无损格式（PNG/BMP）中 LSB 隐写的经典启发式特征。",
            "confidence": 0.55,
        })
    if is_lossy:
        evidence.append({
            "module": "lsb",
            "severity": "info",
            "title": "在有损格式上做 LSB 分析",
            "description": "图像为有损格式（如 JPEG）。此情况下 LSB 分析不可靠，因为压缩本身已经会随机化低位比特。",
            "confidence": 0.2,
        })

    return {
        "lsb_r_image": "visualizations/lsb_r.png",
        "lsb_g_image": "visualizations/lsb_g.png",
        "lsb_b_image": "visualizations/lsb_b.png",
        "lsb_entropy": entropy,
        "lsb_balance": balance,
        "lsb_neighborhood_correlation": corr,
        "lsb_randomness_score": randomness_score,
        "lsb_anomaly_score": float(base_anomaly),
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "JPEG / WebP-lossy 等有损格式会破坏或随机化 LSB，对它们做 LSB 评分并不可靠。",
            "高熵本身并不能证明存在隐写：带抖动的平滑渐变或高频噪声纹理也会让 LSB 熵显得很高。",
        ],
    }
