"""FFT spectrum analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .utils import clamp_to_uint8, safe_open_rgb, to_numpy_rgb


def _fft_log_spectrum(channel: np.ndarray) -> np.ndarray:
    f = np.fft.fft2(channel.astype(np.float32))
    fshift = np.fft.fftshift(f)
    mag = np.log1p(np.abs(fshift))
    return mag


def _detect_peaks(spec: np.ndarray, k: float = 8.0, ignore_radius_ratio: float = 0.06) -> dict[str, Any]:
    h, w = spec.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.indices(spec.shape)
    r2 = (yy - cy) ** 2 + (xx - cx) ** 2
    ignore_r = int(min(h, w) * ignore_radius_ratio)
    mask = r2 >= ignore_r * ignore_r
    vals = spec[mask]
    if vals.size == 0:
        return {"peak_count": 0, "peak_strength_mean": 0.0, "symmetric_peak_pairs": []}
    mean = float(vals.mean())
    std = float(vals.std() + 1e-9)
    threshold = mean + k * std
    peak_mask = (spec > threshold) & mask
    coords = np.argwhere(peak_mask)
    strengths = spec[peak_mask]

    pairs: list[dict[str, Any]] = []
    used = np.zeros(len(coords), dtype=bool)
    for i, (y1, x1) in enumerate(coords):
        if used[i]:
            continue
        sy, sx = 2 * cy - y1, 2 * cx - x1
        for j in range(i + 1, len(coords)):
            if used[j]:
                continue
            y2, x2 = coords[j]
            if abs(int(y2) - int(sy)) <= 2 and abs(int(x2) - int(sx)) <= 2:
                pairs.append({
                    "p1": [int(y1), int(x1)],
                    "p2": [int(y2), int(x2)],
                    "strength": float((spec[y1, x1] + spec[y2, x2]) / 2),
                })
                used[i] = used[j] = True
                break
    return {
        "peak_count": int(coords.shape[0]),
        "peak_strength_mean": float(strengths.mean()) if strengths.size else 0.0,
        "symmetric_peak_pairs": pairs[:32],
        "background_mean": mean,
        "background_std": std,
        "threshold": threshold,
    }


def _save_spectrum(spec: np.ndarray, out_path: Path) -> None:
    img = Image.fromarray(clamp_to_uint8(spec))
    img.save(out_path)


def analyze_fft(path: Path, vis_dir: Path) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img).astype(np.float32)
    gray = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])

    gray_spec = _fft_log_spectrum(gray)
    r_spec = _fft_log_spectrum(arr[..., 0])
    g_spec = _fft_log_spectrum(arr[..., 1])
    b_spec = _fft_log_spectrum(arr[..., 2])

    _save_spectrum(gray_spec, vis_dir / "spectrum.png")
    _save_spectrum(r_spec, vis_dir / "r_spectrum.png")
    _save_spectrum(g_spec, vis_dir / "g_spectrum.png")
    _save_spectrum(b_spec, vis_dir / "b_spectrum.png")

    peaks = _detect_peaks(gray_spec)
    chan_peaks = [
        _detect_peaks(r_spec)["peak_count"],
        _detect_peaks(g_spec)["peak_count"],
        _detect_peaks(b_spec)["peak_count"],
    ]

    pc = peaks["peak_count"]
    sp = len(peaks["symmetric_peak_pairs"])
    spectrum_anomaly_score = float(min(1.0, (pc / 2000.0) * 0.4 + (sp / 20.0) * 0.6))
    channel_anomaly = float(min(1.0, sum(chan_peaks) / 6000.0))

    if (spectrum_anomaly_score > 0.85 and sp >= 10) or sp >= 16:
        risk = "MEDIUM"
    elif spectrum_anomaly_score > 0.6 or sp >= 6:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence: list[dict[str, Any]] = []
    if sp >= 3:
        evidence.append({
            "module": "fft",
            "severity": "warning",
            "title": f"发现 {sp} 对对称尖峰",
            "description": "FFT 频谱中的对称高能尖峰可能表明存在周期性信号（例如扫描莫尔条纹、半色调，或可能的频域水印）。自然纹理和 JPEG 伪影也可能产生此类模式。",
            "confidence": 0.5,
        })
    if pc > 1000:
        evidence.append({
            "module": "fft",
            "severity": "info",
            "title": f"检测到 {pc} 个高频离群点",
            "description": "高于背景+6\u03c3 的频率离群点数量超出正常水平。该判断为启发式结果，可能由锐利边缘、重复图案或压缩伪影引起。",
            "confidence": 0.3,
        })

    return {
        "spectrum_image": "visualizations/spectrum.png",
        "r_spectrum_image": "visualizations/r_spectrum.png",
        "g_spectrum_image": "visualizations/g_spectrum.png",
        "b_spectrum_image": "visualizations/b_spectrum.png",
        "peak_count": pc,
        "symmetric_peak_pairs": peaks["symmetric_peak_pairs"],
        "peak_strength_mean": peaks["peak_strength_mean"],
        "spectrum_anomaly_score": spectrum_anomaly_score,
        "channel_frequency_anomaly_score": channel_anomaly,
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "FFT 频谱中的尖峰可能由自然纹理、扫描莫尔条纹、JPEG 块效应或真实水印引起，无法仅凭尖峰断定来源。",
            "没有看到尖峰也并不能证明图像没有水印。",
        ],
    }
