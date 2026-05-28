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


def _high_texture_ratio(arr: np.ndarray) -> float:
    """估算高纹理像素占比。

    现代手机原片（高 ISO、AI 锐化、人脸毛孔、织物、植物）在每个 8x8 块上
    的高频能量很高，量化反量化后 LSB 平面会呈现接近白噪声的统计特征 ——
    这是 Westfeld 1999 论文里就警告过的"natural smooth image"反例的反面：
    高频图像同样会让 LSB 平面"看起来像被随机替换了"。

    返回 0..1，>0.5 表示整图高频占比已经很高，此时 LSB 白噪声判据应失效。
    """
    if arr.ndim != 3 or arr.shape[0] < 4 or arr.shape[1] < 4:
        return 0.0
    gray = arr.mean(axis=-1).astype(np.int32)
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    # 大于 5 灰阶的像素差视为"非平滑边/纹理"
    high = (dx[:-1, :] > 5) | (dy[:, :-1] > 5)
    return float(high.mean())


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
    texture_ratio = _high_texture_ratio(arr)

    randomness_score = float(min(1.0, avg_entropy * (1.0 - avg_balance_diff * 2.0)))
    randomness_score = max(0.0, randomness_score)

    suspicious = (avg_entropy > 0.999) and (avg_corr < 0.505) and (avg_balance_diff < 0.005)
    # Very strong signal: LSB plane is statistically white noise on ALL three
    # channels. This is the unmistakable footprint of full-LSB replacement
    # steganography (or LSB-randomization), and is what tools like StegSecret
    # / stegdetect's basic LSB test flag.
    #
    # 然而 —— 真实手机原片（尤其 1024 缩图后的高 ISO / 高纹理图）也能轻松
    # 同时踩进这三个区间：传感器残余噪声 + JPEG 量化误差就能让 LSB ≈ 噪声。
    # 所以这里再加两个"否决条件"来杀 false positive：
    #   - corr 上限收紧到 0.502（真正的随机 LSB 期望 corr=0.500，自然图像
    #     即便看起来很随机也通常 >0.503）。
    #   - 高纹理占比 > 0.5 时，整张图 LSB 本来就接近噪声，white_noise 判据失效。
    all_channels_white_noise = (
        all(e > 0.9999 for e in entropy.values())
        and all(0.495 <= c <= 0.502 for c in corr.values())
        and all(abs(v - 0.5) < 0.005 for v in balance.values())
        and texture_ratio < 0.5
    )
    base_anomaly = 0.0
    if all_channels_white_noise:
        base_anomaly = 0.95
    elif suspicious and texture_ratio < 0.4:
        base_anomaly = 0.6
    elif avg_entropy > 0.99 and avg_corr < 0.51 and avg_balance_diff < 0.01:
        base_anomaly = 0.35

    if is_lossy:
        # 软衰减不够 —— JPEG/MPO/HEIC 高纹理图能让 base_anomaly=0.95，乘 0.3
        # 之后还有 0.285，配合 scoring.full_lsb_replacement 的 chi-square 共识
        # 就直接 HIGH 了。这里改成"软衰减 + 硬封顶"双保险：lossy 路径下永远
        # 不允许 LSB 单模块独立给出 HIGH。
        base_anomaly = min(base_anomaly * 0.3, 0.5)

    if base_anomaly > 0.85 and not is_lossy:
        risk = "HIGH"
    elif base_anomaly > 0.55:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence = []
    if suspicious and not is_lossy and texture_ratio < 0.4:
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
            "description": "图像为有损格式（JPEG / MPO / HEIC / AVIF / WEBP-lossy 等）。此情况下 LSB 分析不可靠：压缩量化本身就会把最低位随机化。",
            "confidence": 0.2,
        })
    if texture_ratio >= 0.5:
        evidence.append({
            "module": "lsb",
            "severity": "info",
            "title": f"图像高纹理占比 {texture_ratio*100:.0f}%，LSB 白噪声判据已自动失效",
            "description": "高 ISO 手机原片、织物、毛发、密集树叶等画面本身就让 LSB 接近噪声，这与隐写造成的白噪声无法在统计上区分。",
            "confidence": 0.2,
        })

    return {
        "lsb_r_image": "visualizations/lsb_r.png",
        "lsb_g_image": "visualizations/lsb_g.png",
        "lsb_b_image": "visualizations/lsb_b.png",
        "lsb_entropy": entropy,
        "lsb_balance": balance,
        "lsb_neighborhood_correlation": corr,
        "lsb_high_texture_ratio": texture_ratio,
        "lsb_randomness_score": randomness_score,
        "lsb_anomaly_score": float(base_anomaly),
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "JPEG / MPO / HEIC / AVIF / WEBP-lossy 等有损格式会破坏或随机化 LSB，对它们做 LSB 评分并不可靠。",
            "高熵本身并不能证明存在隐写：带抖动的平滑渐变、高频纹理、高 ISO 噪声都会让 LSB 熵显得很高。",
            "整图位平面统计无法发现「只藏在前 N 个像素里」的小 payload —— 那是 zsteg 风格的 magic-header 扫描的目标，详见隐藏内容提取页。",
        ],
    }
