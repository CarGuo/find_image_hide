"""AI-image colour & high-frequency heuristics.

Three lightweight, training-free signals inspired by recent forensics
literature, in particular the CVPR'25 paper *Secret Lies in Color: Detecting
Diffusion-Generated Images via Channel Statistics*.  The paper shows that
diffusion models leak distinctive **inter-channel correlations** and an
**unnaturally smooth high-frequency residual**: real photos retain Bayer
demosaic / sensor read-noise that drifts the per-channel histograms apart,
while diffusion samples are "too clean" and "too aligned" across R/G/B.

We compute three cheap features:

1. **Channel correlation excess (`corr_excess`)**
   Pearson correlation between each pair of channels (R-G, R-B, G-B).
   Real photos: ~0.85-0.95, but the per-pair *spread* is wider because
   sensor noise + colour-filter array imbalance breaks symmetry. Diffusion
   samples tend to push all three pair-correlations to >=0.97 and very
   close to each other -- this excess is the strongest single signal.

2. **High-frequency residual flatness (`hf_flatness`)**
   Subtract a 3x3 box blur from luminance to get the high-pass residual,
   then measure its *standard deviation*. Real photos at base ISO carry a
   small but consistent residual (~3-7 in 0..255 units); diffusion samples
   are either suspiciously low (<1.5, "AI smoothing") or suspiciously high
   with periodic structure. We flag the low end -- it's the more common
   failure mode of large diffusion models.

3. **Saturation / hue concentration (`hue_peak`)**
   Modern aesthetic-tuned diffusion checkpoints concentrate the hue
   histogram around 2-4 narrow peaks (the "studio palette" effect noted
   in the paper). We compute the top-bin ratio of a 36-bin hue histogram
   over saturated (S>=0.2) pixels. Real photos rarely exceed 0.18; AI
   art often goes to 0.30+.

None of the three is decisive alone. We combine them into a soft anomaly
score and only escalate to MEDIUM (never HIGH) -- HIGH is reserved for
cryptographic / metadata evidence elsewhere in the pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .utils import safe_open_rgb, to_numpy_rgb


def _pair_correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64).ravel()
    b = b.astype(np.float64).ravel()
    a -= a.mean()
    b -= b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom < 1e-9:
        return 0.0
    return float((a * b).sum() / denom)


def _box_blur_3(arr: np.ndarray) -> np.ndarray:
    """3x3 box blur via separable convolution. Float32 in/out."""
    if arr.shape[0] < 3 or arr.shape[1] < 3:
        return arr.copy()
    kernel = np.ones(3, dtype=np.float32) / 3.0
    # horizontal
    pad = np.pad(arr, ((0, 0), (1, 1)), mode="edge")
    h = (pad[:, :-2] + pad[:, 1:-1] + pad[:, 2:]) / 3.0
    # vertical
    pad = np.pad(h, ((1, 1), (0, 0)), mode="edge")
    v = (pad[:-2, :] + pad[1:-1, :] + pad[2:, :]) / 3.0
    return v.astype(np.float32)


def _hue_saturation(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute hue (0..1) and saturation (0..1) HSV components."""
    rgb = arr.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    sat = np.where(cmax > 1e-6, delta / np.maximum(cmax, 1e-6), 0.0)

    hue = np.zeros_like(cmax)
    # avoid divide-by-zero on grey pixels
    mask = delta > 1e-6
    rmax = mask & (cmax == r)
    gmax = mask & (cmax == g) & ~rmax
    bmax = mask & (cmax == b) & ~rmax & ~gmax
    hue_r = ((g - b) / np.maximum(delta, 1e-6)) % 6.0
    hue_g = ((b - r) / np.maximum(delta, 1e-6)) + 2.0
    hue_b = ((r - g) / np.maximum(delta, 1e-6)) + 4.0
    hue = np.where(rmax, hue_r, hue)
    hue = np.where(gmax, hue_g, hue)
    hue = np.where(bmax, hue_b, hue)
    hue = (hue / 6.0) % 1.0
    return hue.astype(np.float32), sat.astype(np.float32)


def analyze_ai_heuristics(path: Path) -> dict[str, Any]:
    """Run colour + high-frequency AI heuristics. No visualisation written."""
    # Read original size first so we can detect "we had to downscale heavily"
    # cases. Heavy downscaling kills the HF residual and narrows the hue
    # histogram -- both of which are exactly the signals we read. We MUST
    # discount them in that case, otherwise every large phone shot scores
    # high from sheer interpolation smoothing.
    from PIL import Image as _Image
    try:
        with _Image.open(path) as _probe:
            orig_w, orig_h = _probe.size
    except Exception:
        orig_w, orig_h = 0, 0

    img = safe_open_rgb(Path(path), max_side=768)
    arr = to_numpy_rgb(img)
    if arr.ndim != 3 or arr.shape[-1] < 3:
        return {
            "risk_level": "UNKNOWN",
            "ai_heuristics_score": 0.0,
            "evidence_items": [],
            "error": "non-RGB image",
        }

    work_max = max(arr.shape[0], arr.shape[1])
    orig_max = max(orig_w, orig_h, work_max)
    downscale_ratio = float(orig_max) / float(work_max) if work_max else 1.0
    # >=2x downscaling kills the HF residual signal (LANCZOS averages
    # ~7-bit of HF energy at 2x, almost everything at 4x+).
    hf_signal_trustworthy = downscale_ratio < 1.5
    hue_signal_trustworthy = downscale_ratio < 2.0

    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]

    # --- 1) channel correlations ----
    rg = _pair_correlation(r, g)
    rb = _pair_correlation(r, b)
    gb = _pair_correlation(g, b)
    corr_min = min(rg, rb, gb)
    corr_spread = max(rg, rb, gb) - corr_min
    # "Excess": all three pair-correlations are simultaneously > 0.97 AND
    # the spread between them is < 0.015.  Natural photos rarely hit both.
    corr_excess = float(max(0.0, corr_min - 0.96)) * float(max(0.0, 0.02 - corr_spread)) * 50.0

    # --- 2) HF residual flatness ----
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    luma = luma.astype(np.float32)
    blur = _box_blur_3(luma)
    hf = luma - blur
    hf_std = float(hf.std())
    # A diffusion sample tends to land in [0.4, 1.8]; real photos at low
    # ISO sit in [3, 8].  We flag the low side: hf_flatness in [0..1].
    hf_flatness = float(max(0.0, min(1.0, (2.5 - hf_std) / 2.5)))

    # --- 3) hue peak concentration ----
    hue, sat = _hue_saturation(arr)
    sat_mask = sat >= 0.2
    if int(sat_mask.sum()) >= 200:
        bins = 36
        hist, _ = np.histogram(hue[sat_mask], bins=bins, range=(0.0, 1.0))
        total = float(hist.sum())
        hue_peak = float(hist.max() / total) if total > 0 else 0.0
    else:
        # too few saturated pixels (e.g. greyscale-ish image): not a usable signal
        hue_peak = 0.0

    # --- combine into soft score (0..1) ----
    # weights chosen so any single signal alone tops at ~0.45,
    # any two signals together can reach ~0.75.
    hf_term = hf_flatness if hf_signal_trustworthy else 0.0
    hue_term = max(0.0, (hue_peak - 0.18) / 0.20) if hue_signal_trustworthy else 0.0
    score = float(min(1.0,
                      0.45 * corr_excess
                      + 0.35 * hf_term
                      + 0.30 * hue_term))
    score = max(0.0, score)

    # Risk: never HIGH from heuristics alone. We deliberately keep the
    # MEDIUM threshold high (>=0.55) -- AI heuristics is the noisiest of
    # all our signals and we don't want it to drive overall risk on its
    # own.
    if score >= 0.55:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence: list[dict[str, Any]] = []
    if corr_excess > 0.5:
        evidence.append({
            "module": "ai_heuristics",
            "severity": "info",
            "title": f"通道相关性异常一致（R-G={rg:.3f}、R-B={rb:.3f}、G-B={gb:.3f}）",
            "description": (
                "扩散模型生成图常出现三对通道相关系数同时 > 0.97 且彼此差异极小的"
                "统计特征（参考 CVPR'25 *Secret Lies in Color*）；自然摄影由于传感器噪声 "
                "+ 拜耳滤波器的非对称性，这三个值的差异通常更大。"
            ),
            "confidence": 0.4,
        })
    if hf_flatness > 0.5 and hf_signal_trustworthy:
        evidence.append({
            "module": "ai_heuristics",
            "severity": "info",
            "title": f"高频残差异常平滑（HF std={hf_std:.2f}）",
            "description": (
                "亮度通道的 3×3 高通残差标准差远低于自然摄影（一般 3-8），与扩散 / GAN "
                "模型常见的「过度平滑」表现一致；但相机 AI 降噪、强对焦、纯色背景也会"
                "造成相同效果，本指标只作为辅助信号。"
            ),
            "confidence": 0.35,
        })
    if hue_peak > 0.25 and hue_signal_trustworthy:
        evidence.append({
            "module": "ai_heuristics",
            "severity": "info",
            "title": f"色相分布高度集中（top-bin 占比 {hue_peak*100:.0f}%）",
            "description": (
                "饱和像素的 36-bin 色相直方图存在异常单峰，类似于美学微调过的扩散模型 "
                "「调色板风格」。自然摄影的色相分布通常较为分散。"
            ),
            "confidence": 0.3,
        })

    return {
        "risk_level": risk,
        "ai_heuristics_score": score,
        "channel_correlations": {"rg": rg, "rb": rb, "gb": gb},
        "channel_correlation_spread": corr_spread,
        "channel_correlation_excess": corr_excess,
        "hf_residual_std": hf_std,
        "hf_flatness": hf_flatness,
        "hue_top_bin_ratio": hue_peak,
        "downscale_ratio": downscale_ratio,
        "hf_signal_trustworthy": hf_signal_trustworthy,
        "hue_signal_trustworthy": hue_signal_trustworthy,
        "evidence_items": evidence,
        "limitations": [
            "本模块只是启发式提示，**不构成 AI 生成的认定**；任何高风险结论需要结合 C2PA 凭证、SynthID、metadata 关键字综合判断。",
            "相机内置 AI 降噪、HDR、人像虚化都会让 HF 残差变低，可能造成假阳性。",
            "纯色 / 极简构图（白底产品图、剪影）会让色相直方图天然集中，需要排除。",
            "极小尺寸图像（<256px）可能让通道相关系数估计不稳定。",
            "原图被强力缩放（>1.5×）时 HF 残差不可信，本模块自动屏蔽该信号；缩放 >2× 时连带屏蔽色相直方图信号。",
        ],
    }
