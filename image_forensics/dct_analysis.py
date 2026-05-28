"""DCT 8x8 block analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .utils import safe_open_rgb, to_numpy_rgb


def _block_dct(channel: np.ndarray) -> np.ndarray:
    h, w = channel.shape
    h8, w8 = h - h % 8, w - w % 8
    channel = channel[:h8, :w8]
    blocks = channel.reshape(h8 // 8, 8, w8 // 8, 8).swapaxes(1, 2).reshape(-1, 8, 8)
    blocks = blocks.astype(np.float32) - 128.0
    try:
        from scipy.fftpack import dct
        d = dct(dct(blocks, axis=1, norm="ortho"), axis=2, norm="ortho")
    except Exception:
        n = 8
        k = np.arange(n)
        c = np.cos(np.pi * (2 * k[:, None] + 1) * k[None, :] / (2 * n))
        scale = np.ones(n)
        scale[0] = 1 / np.sqrt(2)
        m = scale[:, None] * c.T * np.sqrt(2 / n)
        d = np.einsum("ij,bjk,kl->bil", m, blocks, m.T)
    return d


def _save_heatmap(matrix: np.ndarray, out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(matrix, cmap="viridis")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _save_histogram(values: np.ndarray, out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(5, 3))
    clip = np.clip(values, -50, 50)
    ax.hist(clip.ravel(), bins=101, color="#4C7CFF")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def analyze_dct(path: Path, vis_dir: Path) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img).astype(np.float32)
    y = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]

    if y.shape[0] < 16 or y.shape[1] < 16:
        return {
            "dct_mean_heatmap": None,
            "dct_histogram": None,
            "low_frequency_stats": {},
            "mid_frequency_stats": {},
            "high_frequency_stats": {},
            "dct_anomaly_score": 0.0,
            "risk_level": "UNKNOWN",
            "evidence_items": [],
            "limitations": ["图像太小，不足以做 8x8 DCT 分析。"],
        }

    blocks = _block_dct(y)

    abs_mean = np.abs(blocks).mean(axis=0)
    _save_heatmap(abs_mean, vis_dir / "dct_mean_heatmap.png", "8x8 DCT |coef| mean")

    mid_band = blocks[:, 2:6, 2:6]
    _save_histogram(mid_band, vis_dir / "dct_histogram.png", "Mid-frequency DCT histogram")

    coords = np.indices((8, 8)).sum(axis=0)
    low_mask = coords <= 2
    high_mask = coords >= 10
    mid_mask = ~low_mask & ~high_mask

    def stats(mask: np.ndarray) -> dict[str, float]:
        sel = blocks[:, mask]
        return {
            "mean": float(sel.mean()),
            "std": float(sel.std()),
            "abs_mean": float(np.abs(sel).mean()),
            "zero_ratio": float((np.abs(sel) < 0.5).mean()),
        }

    low = stats(low_mask)
    mid = stats(mid_mask)
    high = stats(high_mask)

    mid_high_concentration = abs_mean[mid_mask].mean()
    high_flatness = abs_mean[high_mask].mean()
    expected_high = max(0.05, low["abs_mean"] * 0.05)
    high_suppress_ratio = float(min(1.0, expected_high / max(0.001, high_flatness)))

    # K-S test of mid-band coefficients against a Laplace distribution.
    # Natural-image AC DCT coefficients are very well modelled by Laplace
    # (Reininger & Gibson, 1983; used by Fridrich and others to detect
    # additive / spread-spectrum watermarks). A large K-S statistic means
    # the empirical distribution does not look natural, which is one of
    # the few signals robust to JPEG re-compression.
    ks_stat = 0.0
    ks_p = 1.0
    try:
        from scipy import stats as _sps  # type: ignore
        sample = mid_band.ravel()
        if sample.size > 4096:
            rng = np.random.default_rng(0)
            sample = rng.choice(sample, size=4096, replace=False)
        scale = float(np.mean(np.abs(sample))) or 1.0
        ks_res = _sps.kstest(sample, "laplace", args=(0.0, scale))
        ks_stat = float(ks_res.statistic)
        ks_p = float(ks_res.pvalue)
    except Exception:
        pass

    score = 0.0
    if mid["zero_ratio"] < 0.15:
        score += 0.3
    if mid_high_concentration > low["abs_mean"] * 0.8:
        score += 0.4
    if high_suppress_ratio > 0.95:
        score += 0.3
    if ks_stat > 0.15:           # noticeable deviation from Laplace
        score += 0.2
    score = float(min(1.0, score))

    if ks_stat > 0.20 and score > 0.5:
        risk = "MEDIUM"
    elif score > 0.85:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence = []
    if score > 0.3:
        evidence.append({
            "module": "dct",
            "severity": "info",
            "title": "DCT 中频异常启发式被触发",
            "description": "中频 DCT 统计量与典型自然图像存在偏差。这可能意味着图像被加入了水印、经过大量编辑，或仅仅是图像内容比较特殊。",
            "confidence": 0.4,
        })
    if ks_stat > 0.15:
        evidence.append({
            "module": "dct",
            "severity": "info",
            "title": f"DCT 中频段 K-S 检验偏离拉普拉斯分布（D={ks_stat:.3f}, p={ks_p:.3g}）",
            "description": "自然图像的 AC DCT 系数服从拉普拉斯分布。K-S 统计量偏大提示可能存在加性 / 扩频水印，或经过大量编辑。",
            "confidence": float(min(0.8, ks_stat * 2.0)),
        })

    return {
        "dct_mean_heatmap": "visualizations/dct_mean_heatmap.png",
        "dct_histogram": "visualizations/dct_histogram.png",
        "low_frequency_stats": low,
        "mid_frequency_stats": mid,
        "high_frequency_stats": high,
        "dct_ks_statistic": ks_stat,
        "dct_ks_p_value": ks_p,
        "dct_anomaly_score": score,
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "这里的 DCT 是从像素重新计算的；对非 JPEG 输入，它不等于编码器原生的 DCT 系数。",
            "JPEG 压缩本身就会让中 / 高频统计偏移，不一定是隐写造成的。",
            "K-S 与拉普拉斯分布的对比只是启发式方法；某些自然图像（例如纯文字截图、低细节图）也会显著偏离。",
        ],
    }
