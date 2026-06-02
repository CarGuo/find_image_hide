"""LSB bit-plane analysis.

P1 expansion: this module now scans **all 8 bit-planes** per channel rather
than just the LSB (plane 0). The intuition is that natural images have a
strict "energy hierarchy" -- plane 0 looks noisy, plane 1 is slightly less
noisy, ..., plane 7 is essentially the high-order silhouette. Any
substitution-style steganography breaks that hierarchy on the planes it
touches: the affected planes' entropy jumps to ~1.0 and their neighbourhood
correlation drops to ~0.5, which is detectable as a *step* in an otherwise
monotone curve.

Backwards compatibility:
    The legacy top-level keys (`lsb_anomaly_score`, `lsb_entropy`,
    `lsb_balance`, `lsb_neighborhood_correlation`, `risk_level`) still refer
    to plane 0, so [scoring.py](image_forensics/scoring.py) keeps working
    untouched.
"""
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
    """Estimate the high-texture pixel ratio.

    Modern phone shots (high-ISO + AI sharpening + face pores + foliage)
    have a lot of high-frequency energy on every 8x8 block. After quant /
    dequant their LSB plane already looks nearly random -- this is the very
    failure mode Westfeld 1999 warned about. We use this as a kill-switch
    for the white-noise verdict.
    Returns 0..1; >0.5 means the whole image is texture-dense.
    """
    if arr.ndim != 3 or arr.shape[0] < 4 or arr.shape[1] < 4:
        return 0.0
    gray = arr.mean(axis=-1).astype(np.int32)
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    high = (dx[:-1, :] > 5) | (dy[:, :-1] > 5)
    return float(high.mean())


def _per_plane_stats(channel: np.ndarray) -> list[dict[str, float]]:
    """Compute (entropy, balance, corr) for plane 0..7 of one uint8 channel."""
    out: list[dict[str, float]] = []
    for k in range(8):
        bits = (channel >> k) & 1
        out.append({
            "plane": k,
            "entropy": _shannon_entropy(bits),
            "balance": float(bits.mean()),
            "corr": _neighborhood_correlation(bits),
        })
    return out


def _white_noise_planes(stats: list[dict[str, float]]) -> list[int]:
    """Return the indices of bit-planes that look like pure white noise.

    Threshold reasoning:
        entropy > 0.999 + 0.495 <= corr <= 0.502 + |balance-0.5| < 0.005
    This is the same triple-test the legacy logic uses for plane 0, applied
    plane-by-plane. The number of planes that match is itself the headline
    signal: natural images get 0-1 such planes (only plane 0, sometimes).
    A "deeply embedded" stego payload (e.g. F5 / LSB-matching with rate=1)
    pushes it to 2-3+.
    """
    hit: list[int] = []
    for s in stats:
        if (s["entropy"] > 0.999
                and 0.495 <= s["corr"] <= 0.502
                and abs(s["balance"] - 0.5) < 0.005):
            hit.append(int(s["plane"]))
    return hit


def _hierarchy_violation(stats: list[dict[str, float]]) -> float:
    """Score how badly the bit-planes break the natural entropy hierarchy.

    For natural images, entropy(plane k) should be roughly *monotonically
    non-increasing* from plane 0 down to plane 7 (LSB is the noisiest;
    high-order bits are most structured). A single "step down" in entropy
    on a low plane is the classic LSB-replacement footprint. We measure
    how many adjacent pairs (k, k+1) violate the non-increasing order
    significantly, weighted by the size of the violation.

    Returns 0..1; ~0 for natural photos, climbs as more planes get
    randomized.
    """
    if len(stats) < 2:
        return 0.0
    violations = 0.0
    for i in range(len(stats) - 1):
        e_lo = stats[i]["entropy"]
        e_hi = stats[i + 1]["entropy"]
        # natural: e_lo >= e_hi. Violation: e_hi > e_lo by a margin.
        diff = e_hi - e_lo
        if diff > 0.05:
            violations += diff
    return float(min(1.0, violations))


def _cross_channel_diff(plane_stats: dict[str, list[dict[str, float]]],
                        plane_idx: int) -> dict[str, float]:
    """Compare R/G/B at a given bit-plane.

    Truly random LSB substitution makes R/G/B planes statistically
    interchangeable -> tiny differences. Natural noise is correlated across
    channels (Bayer demosaic artefacts), so |entropy(R)-entropy(B)| etc.
    are small but non-zero. This is a weak supporting signal -- we only
    use it for evidence text, not for risk escalation.
    """
    rs = plane_stats["r"][plane_idx]
    gs = plane_stats["g"][plane_idx]
    bs = plane_stats["b"][plane_idx]
    return {
        "entropy_spread": float(max(rs["entropy"], gs["entropy"], bs["entropy"])
                                - min(rs["entropy"], gs["entropy"], bs["entropy"])),
        "balance_spread": float(max(rs["balance"], gs["balance"], bs["balance"])
                                - min(rs["balance"], gs["balance"], bs["balance"])),
        "corr_spread": float(max(rs["corr"], gs["corr"], bs["corr"])
                             - min(rs["corr"], gs["corr"], bs["corr"])),
    }


def analyze_lsb(path: Path, vis_dir: Path, is_lossy: bool) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img)

    # ---- per-plane stats for all 8 planes on each channel ----
    plane_stats = {
        "r": _per_plane_stats(arr[..., 0]),
        "g": _per_plane_stats(arr[..., 1]),
        "b": _per_plane_stats(arr[..., 2]),
    }

    # ---- visualisations: keep legacy plane-0 names + add plane-1..3 ----
    # (planes 4..7 are essentially copies of the original silhouette and
    # take a lot of disk for very little forensic value.)
    bits_r0 = arr[..., 0] & 1
    bits_g0 = arr[..., 1] & 1
    bits_b0 = arr[..., 2] & 1
    Image.fromarray((bits_r0 * 255).astype(np.uint8)).save(vis_dir / "lsb_r.png")
    Image.fromarray((bits_g0 * 255).astype(np.uint8)).save(vis_dir / "lsb_g.png")
    Image.fromarray((bits_b0 * 255).astype(np.uint8)).save(vis_dir / "lsb_b.png")
    plane_vis: dict[str, str] = {}
    for ch_name, ch_arr in (("r", arr[..., 0]), ("g", arr[..., 1]), ("b", arr[..., 2])):
        for k in range(0, 4):
            bits = (ch_arr >> k) & 1
            fname = f"lsb_{ch_name}_p{k}.png"
            Image.fromarray((bits * 255).astype(np.uint8)).save(vis_dir / fname)
            plane_vis[f"{ch_name}_p{k}"] = f"visualizations/{fname}"

    # ---- legacy plane-0 derived fields (scoring.py reads these) ----
    entropy = {ch: plane_stats[ch][0]["entropy"] for ch in "rgb"}
    balance = {ch: plane_stats[ch][0]["balance"] for ch in "rgb"}
    corr = {ch: plane_stats[ch][0]["corr"] for ch in "rgb"}

    avg_entropy = sum(entropy.values()) / 3.0
    avg_balance_diff = sum(abs(v - 0.5) for v in balance.values()) / 3.0
    avg_corr = sum(corr.values()) / 3.0
    texture_ratio = _high_texture_ratio(arr)

    randomness_score = float(min(1.0, avg_entropy * (1.0 - avg_balance_diff * 2.0)))
    randomness_score = max(0.0, randomness_score)

    suspicious = (avg_entropy > 0.999) and (avg_corr < 0.505) and (avg_balance_diff < 0.005)

    # ---- NEW P1 multi-plane signals --------------------------------------
    # 1) Count how many planes look like pure white noise per channel.
    white_planes = {ch: _white_noise_planes(plane_stats[ch]) for ch in "rgb"}
    # 2) "Suspicious" planes = white-noise planes shared across all 3 channels.
    #    Natural images: usually only plane 0 (and only on noisy phone shots).
    #    LSB-matching / random LSB-replacement on multiple planes pushes this
    #    set well beyond {0}.
    common_white = sorted(set(white_planes["r"])
                          & set(white_planes["g"])
                          & set(white_planes["b"]))
    # 3) Entropy hierarchy violation -- non-increasing assumption.
    hierarchy_score = max(_hierarchy_violation(plane_stats[ch]) for ch in "rgb")
    # 4) Cross-channel diff at plane 0 (weak supporting evidence).
    p0_diff = _cross_channel_diff(plane_stats, 0)

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

    # NEW: lift base_anomaly when planes BEYOND plane 0 also look random.
    # Two conservative bumps (texture-ratio gate keeps them from firing on
    # high-ISO phone shots):
    #   - common_white >= {0,1}        : +0.10  (LSB-matching at rate ~1)
    #   - common_white >= {0,1,2}      : additional +0.10 (deep embedding)
    if texture_ratio < 0.5 and not is_lossy:
        if {0, 1}.issubset(common_white):
            base_anomaly = min(1.0, base_anomaly + 0.10)
        if {0, 1, 2}.issubset(common_white):
            base_anomaly = min(1.0, base_anomaly + 0.10)
        # Hierarchy violation is rarer than chance in nature; a value > 0.2
        # is already a noteworthy signal.
        if hierarchy_score > 0.2:
            base_anomaly = min(1.0, base_anomaly + 0.05)

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

    evidence: list[dict[str, Any]] = []
    if suspicious and not is_lossy and texture_ratio < 0.4:
        evidence.append({
            "module": "lsb",
            "severity": "warning",
            "title": "LSB 位平面呈现高度随机",
            "description": "最低有效位平面的熵接近最大值，且空间相关性非常低，这在自然图像中并不常见。此现象是无损格式（PNG/BMP）中 LSB 隐写的经典启发式特征。",
            "confidence": 0.55,
        })
    if not is_lossy and texture_ratio < 0.5 and len(common_white) >= 2:
        planes_text = "、".join(f"plane-{p}" for p in common_white)
        evidence.append({
            "module": "lsb",
            "severity": "warning",
            "title": f"位平面 {planes_text} 在三个通道上同时呈白噪声",
            "description": (
                "正常图像中只有 plane-0（最低位）会接近白噪声；本图却在多个低位面同时出现"
                "高熵 + corr≈0.5 + balance≈0.5 三连，这与 LSB-matching / 随机替换型"
                "隐写在多个位面同时写入的指纹一致。"
            ),
            "confidence": 0.6,
        })
    if not is_lossy and texture_ratio < 0.5 and hierarchy_score > 0.2:
        evidence.append({
            "module": "lsb",
            "severity": "warning",
            "title": f"位平面熵层级被打破（违规度 {hierarchy_score:.2f}）",
            "description": (
                "自然图像中位面熵应当随 plane 编号上升而单调下降；本图存在显著"
                "反向跳跃，常见于人为对某些低位面做随机化操作。"
            ),
            "confidence": 0.45,
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
        # legacy plane-0 visualisations (kept for the existing UI)
        "lsb_r_image": "visualizations/lsb_r.png",
        "lsb_g_image": "visualizations/lsb_g.png",
        "lsb_b_image": "visualizations/lsb_b.png",
        # legacy plane-0 stats (read by scoring.py, do not rename)
        "lsb_entropy": entropy,
        "lsb_balance": balance,
        "lsb_neighborhood_correlation": corr,
        "lsb_high_texture_ratio": texture_ratio,
        "lsb_randomness_score": randomness_score,
        "lsb_anomaly_score": float(base_anomaly),
        "risk_level": risk,
        "evidence_items": evidence,
        # P1 multi-plane fields ------------------------------------------------
        "lsb_plane_stats": plane_stats,
        "lsb_plane_visualizations": plane_vis,
        "lsb_white_noise_planes": white_planes,
        "lsb_common_white_noise_planes": common_white,
        "lsb_hierarchy_violation_score": float(hierarchy_score),
        "lsb_plane0_cross_channel_spread": p0_diff,
        "limitations": [
            "JPEG / MPO / HEIC / AVIF / WEBP-lossy 等有损格式会破坏或随机化 LSB，对它们做 LSB 评分并不可靠。",
            "高熵本身并不能证明存在隐写：带抖动的平滑渐变、高频纹理、高 ISO 噪声都会让 LSB 熵显得很高。",
            "整图位平面统计无法发现「只藏在前 N 个像素里」的小 payload —— 那是 zsteg 风格的 magic-header 扫描的目标，详见隐藏内容提取页。",
            "本模块新增的 plane-1..7 启发式仅作为辅助证据，不会让风险等级越级到 HIGH。",
        ],
    }
