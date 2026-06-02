"""Copy-move forgery detection (block DCT + shift-vector histogram).

Algorithm
---------
This is the classical *Fridrich-Goljan-Du* (2003) approach, kept dependency-
free (NumPy only). It is one of the most cited copy-move forensics
baselines and remains useful as a "first warning shot" before the user
spends compute on patch-match / SIFT descriptors.

Steps:
1. Convert the image to greyscale and downscale (max side 512) so even
   on Win laptops the O(N log N) sort stays under ~0.5s for typical photos.
2. Extract overlapping 8x8 blocks with stride=4 (block shift, not pixel
   shift -- still dense enough to catch copy-paste >= 16x16 px).
3. Apply 2D-DCT to each block. We only keep the first 16 zig-zag
   coefficients as the signature: high-frequency DCT coeffs are dominated
   by JPEG-quantisation noise and are useless for matching.
4. Quantise the signature (round to 1 unit) so near-identical blocks share
   exactly one key, and lexicographically sort.
5. Walk the sorted list -- adjacent matches are the candidate clone pairs.
6. For each candidate pair (B_i, B_j) record the shift vector
   (dx, dy) = pos_j - pos_i with sign normalised so that dy>=0
   (or dy==0 and dx>=0).
7. Build a histogram over shift vectors. A genuine copy-move forgery
   produces a *single* shift vector with a count far above the 99-th
   percentile of all shift counts. Random "lucky matches" in textureless
   patches produce a flat histogram instead.

Output anomaly_score is the signal-to-noise ratio between the top shift
count and the median, normalised to 0..1. We only escalate to MEDIUM at
SNR>=8 and to HIGH at SNR>=20 plus a minimum cluster size, mirroring
the conservatism of the rest of the pipeline.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .utils import safe_open_rgb, to_numpy_rgb


# ---------- DCT primitives (8x8) -------------------------------------------------
# Build the 8-point DCT matrix once. NumPy's einsum below applies it to every
# block in one fused call -- ~50x faster than scipy.fft.dctn on 8x8.
def _build_dct_matrix(n: int = 8) -> np.ndarray:
    k = np.arange(n).reshape(-1, 1)
    i = np.arange(n).reshape(1, -1)
    M = np.cos(np.pi * (2 * i + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
    M[0, :] /= np.sqrt(2.0)
    return M.astype(np.float32)


_DCT8 = _build_dct_matrix(8)

# Zig-zag indices for the first 16 DCT coefficients of an 8x8 block.
# (DC + 15 lowest frequencies.) These carry the bulk of block identity.
_ZIGZAG_16 = np.array([
    (0, 0), (0, 1), (1, 0), (2, 0), (1, 1), (0, 2), (0, 3), (1, 2),
    (2, 1), (3, 0), (4, 0), (3, 1), (2, 2), (1, 3), (0, 4), (0, 5),
])


def _dct_2d(blocks: np.ndarray) -> np.ndarray:
    """Apply 2D DCT-II to a stack of (N, 8, 8) float blocks."""
    # einsum: out[n,k,l] = sum_{i,j} M[k,i] * M[l,j] * blocks[n,i,j]
    tmp = np.einsum("ki,nij->nkj", _DCT8, blocks)
    return np.einsum("nkj,lj->nkl", tmp, _DCT8)


def _extract_block_signatures(gray: np.ndarray,
                              block: int = 8,
                              stride: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Return (positions[N,2], signatures[N,16]) as int32."""
    h, w = gray.shape
    if h < block or w < block:
        return np.zeros((0, 2), dtype=np.int32), np.zeros((0, 16), dtype=np.int32)
    ys = np.arange(0, h - block + 1, stride)
    xs = np.arange(0, w - block + 1, stride)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    positions = np.stack([yy.ravel(), xx.ravel()], axis=-1).astype(np.int32)

    n = positions.shape[0]
    blocks = np.empty((n, block, block), dtype=np.float32)
    for idx, (y, x) in enumerate(positions):
        blocks[idx] = gray[y:y + block, x:x + block]
    blocks -= blocks.mean(axis=(1, 2), keepdims=True)
    coeffs = _dct_2d(blocks)
    sigs = coeffs[:, _ZIGZAG_16[:, 0], _ZIGZAG_16[:, 1]]
    sigs = np.rint(sigs).astype(np.int32)
    return positions, sigs


def _normalise_shift(dy: int, dx: int) -> tuple[int, int]:
    """Canonicalise (dy, dx) so that (dy, dx) and (-dy, -dx) collapse to one."""
    if dy < 0 or (dy == 0 and dx < 0):
        return -dy, -dx
    return dy, dx


def analyze_copy_move(path: Path, vis_dir: Path,
                      max_side: int = 512,
                      block: int = 8,
                      stride: int = 4,
                      min_shift_distance: int = 16) -> dict[str, Any]:
    """Detect copy-move duplicated regions.

    Args:
        path: image path.
        vis_dir: where to drop the visualisation PNG.
        max_side: downscale long side to this many pixels (perf cap).
        block: DCT block size, fixed at 8 for now.
        stride: stride between blocks (smaller = denser = slower).
        min_shift_distance: ignore matches whose shift magnitude is below
            this many pixels -- those are the natural neighbour-block
            similarities that always exist in flat regions.
    """
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=max_side)
    arr = to_numpy_rgb(img)
    gray = arr.mean(axis=-1).astype(np.float32)

    positions, sigs = _extract_block_signatures(gray, block=block, stride=stride)
    n_blocks = int(positions.shape[0])
    if n_blocks < 32:
        return {
            "risk_level": "LOW",
            "copy_move_score": 0.0,
            "n_blocks": n_blocks,
            "candidate_pairs": 0,
            "top_shift": None,
            "top_shift_count": 0,
            "shift_snr": 0.0,
            "evidence_items": [],
            "limitations": [
                "图像太小或过度缩放，跳过 Copy-Move 检测。",
            ],
        }

    # ----- diversity gate ------------------------------------------------
    # If the image is so smooth that >=80% of blocks share a signature with
    # at least one other block, the whole image is effectively self-similar
    # (think: clean sky, gradient, low-quality JPEG flatland). The shift
    # histogram is *meaningless* in that regime -- any random pair of
    # near-identical blocks lights it up. We bail out gracefully.
    unique_sigs = np.unique(sigs, axis=0)
    diversity = float(unique_sigs.shape[0]) / float(n_blocks)
    # Also measure AC energy (variance of DCT coefficients excluding DC).
    # Very flat images sit at ~0.0; natural photos at base ISO sit >> 1.0.
    ac_energy = float(np.mean(np.abs(sigs[:, 1:]).astype(np.float64)))
    if diversity < 0.30 or ac_energy < 0.5:
        return {
            "risk_level": "LOW",
            "copy_move_score": 0.0,
            "n_blocks": n_blocks,
            "unique_signatures": int(unique_sigs.shape[0]),
            "block_diversity": diversity,
            "ac_energy": ac_energy,
            "candidate_pairs": 0,
            "top_shift": None,
            "top_shift_count": 0,
            "shift_snr": 0.0,
            "evidence_items": [{
                "module": "copy_move",
                "severity": "info",
                "title": "图像过于平滑，Copy-Move 检测自动跳过",
                "description": (
                    f"块多样性={diversity:.2f}（unique={unique_sigs.shape[0]}/"
                    f"{n_blocks}），AC 能量={ac_energy:.2f}。该图缺乏足够的纹理细节，"
                    "Copy-Move 算法在此类图像上会产生大量自然重复，结论不可信。"
                ),
                "confidence": 0.1,
            }],
            "limitations": [
                "纯色 / 强渐变 / 低质量压缩图像无法提供足够的块多样性，跳过本检测。",
            ],
        }

    # Lexicographic sort on signatures.
    order = np.lexsort(sigs.T[::-1])
    sigs_sorted = sigs[order]
    pos_sorted = positions[order]

    # Walk adjacent rows; cluster all consecutive equal-signature blocks.
    shift_counts: Counter[tuple[int, int]] = Counter()
    shift_examples: dict[tuple[int, int], tuple[tuple[int, int], tuple[int, int]]] = {}
    candidate_pairs = 0

    i = 0
    while i < n_blocks - 1:
        j = i + 1
        while j < n_blocks and np.array_equal(sigs_sorted[i], sigs_sorted[j]):
            j += 1
        # Pairs within [i, j) all share the same signature.
        if j - i >= 2:
            cluster = pos_sorted[i:j]
            # Pair the cluster's first member with each subsequent member.
            for k in range(1, cluster.shape[0]):
                dy = int(cluster[k, 0]) - int(cluster[0, 0])
                dx = int(cluster[k, 1]) - int(cluster[0, 1])
                if abs(dy) + abs(dx) < min_shift_distance:
                    continue
                key = _normalise_shift(dy, dx)
                shift_counts[key] += 1
                shift_examples.setdefault(
                    key,
                    ((int(cluster[0, 0]), int(cluster[0, 1])),
                     (int(cluster[k, 0]), int(cluster[k, 1]))),
                )
                candidate_pairs += 1
        i = j

    if not shift_counts:
        return {
            "risk_level": "LOW",
            "copy_move_score": 0.0,
            "n_blocks": n_blocks,
            "candidate_pairs": 0,
            "top_shift": None,
            "top_shift_count": 0,
            "shift_snr": 0.0,
            "evidence_items": [],
            "limitations": [
                "未找到具有显著重复签名的块对。",
            ],
        }

    counts = np.array(sorted(shift_counts.values(), reverse=True), dtype=np.int32)
    top_count = int(counts[0])
    median_count = float(np.median(counts)) if counts.size > 0 else 0.0
    snr = float(top_count) / max(1.0, median_count)

    top_shift, _ = shift_counts.most_common(1)[0]
    top_example = shift_examples.get(top_shift)

    # Anomaly score in 0..1: sigmoid-ish around SNR=10.
    score = float(min(1.0, max(0.0, (snr - 4.0) / 16.0)))

    # Risk gating: HIGH demands BOTH high SNR AND a non-trivial cluster size.
    if snr >= 20.0 and top_count >= 12:
        risk = "HIGH"
    elif snr >= 8.0 and top_count >= 6:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    # ---- visualisation ---------------------------------------------------
    vis_rel = ""
    if risk in ("MEDIUM", "HIGH") and top_example is not None:
        vis_img = img.copy()
        draw = ImageDraw.Draw(vis_img)
        # Draw rectangles for every pair sharing the dominant shift.
        for key, ((y1, x1), (y2, x2)) in shift_examples.items():
            if key != top_shift:
                continue
            draw.rectangle([x1, y1, x1 + block, y1 + block], outline="red", width=2)
            draw.rectangle([x2, y2, x2 + block, y2 + block], outline="orange", width=2)
            draw.line([(x1 + block // 2, y1 + block // 2),
                       (x2 + block // 2, y2 + block // 2)], fill="yellow", width=1)
        out_path = vis_dir / "copy_move.png"
        vis_img.save(out_path)
        vis_rel = "visualizations/copy_move.png"

    evidence: list[dict[str, Any]] = []
    if risk in ("MEDIUM", "HIGH"):
        evidence.append({
            "module": "copy_move",
            "severity": "warning" if risk == "MEDIUM" else "alert",
            "title": f"检测到疑似 Copy-Move 复制粘贴痕迹（SNR={snr:.1f}）",
            "description": (
                f"在 {n_blocks} 个 8×8 块中发现 {top_count} 对重复块共享同一位移向量 "
                f"({top_shift[1]}, {top_shift[0]})，远高于其他位移的中位数 {median_count:.1f}。"
                "这是图像内同一区域被复制粘贴并位移的经典指纹。"
            ),
            "confidence": 0.6 if risk == "MEDIUM" else 0.8,
        })

    return {
        "risk_level": risk,
        "copy_move_score": score,
        "n_blocks": n_blocks,
        "candidate_pairs": candidate_pairs,
        "top_shift": [int(top_shift[0]), int(top_shift[1])],
        "top_shift_count": top_count,
        "shift_snr": snr,
        "shift_median": median_count,
        "visualization": vis_rel,
        "evidence_items": evidence,
        "limitations": [
            "本算法只能发现「平移」型复制粘贴；旋转 / 缩放后的克隆需要 SIFT 等不变特征。",
            "极平坦区域（纯天空、纯墙）产生的「自然重复」已被最小位移阈值过滤，但仍可能在密集纹理图像上产生少量误报。",
            "JPEG 重压缩会让 DCT 系数被进一步量化，灵敏度下降；laundered 图像建议结合 ELA 综合判断。",
        ],
    }
