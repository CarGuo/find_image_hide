"""Noise residual analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False

from .utils import clamp_to_uint8, safe_open_rgb, to_numpy_rgb


def analyze_noise(path: Path, vis_dir: Path) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img).astype(np.float32)
    gray = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]

    if HAVE_CV2:
        blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    else:
        from scipy.ndimage import gaussian_filter, laplace
        blurred = gaussian_filter(gray, sigma=2.0)
        lap = laplace(gray)

    residual = gray - blurred

    Image.fromarray(clamp_to_uint8(residual)).save(vis_dir / "residual.png")
    Image.fromarray(clamp_to_uint8(np.abs(lap))).save(vis_dir / "laplacian.png")

    h, w = residual.shape
    bs = max(32, min(128, min(h, w) // 8))
    locals_std = []
    for y in range(0, h - bs, bs):
        for x in range(0, w - bs, bs):
            blk = residual[y:y + bs, x:x + bs]
            locals_std.append(float(blk.std()))
    locals_std_arr = np.asarray(locals_std) if locals_std else np.zeros(1)
    inconsistency = float(locals_std_arr.std() / (locals_std_arr.mean() + 1e-6)) if locals_std_arr.size > 1 else 0.0

    score = float(min(1.0, max(0.0, (inconsistency - 0.6) * 1.0)))
    if score > 0.85:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence = []
    if score > 0.4:
        evidence.append({
            "module": "noise",
            "severity": "info",
            "title": "检测到局部噪声不一致",
            "description": "图像中各区域的局部噪声方差差异比正常情况更大。这可能表明存在拼接、严重的局部编辑或不均匀的水印嵌入，但在同时包含平坦和纹理区域的图像中也可能出现这种情况。",
            "confidence": 0.4,
        })

    return {
        "residual_image": "visualizations/residual.png",
        "laplacian_image": "visualizations/laplacian.png",
        "noise_inconsistency_score": score,
        "residual_stats": {
            "mean": float(residual.mean()),
            "std": float(residual.std()),
            "abs_mean": float(np.abs(residual).mean()),
            "local_std_mean": float(locals_std_arr.mean()),
            "local_std_std": float(locals_std_arr.std()),
        },
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "噪声不一致也可能由自然纹理变化、景深虚化或相机内部处理（去噪 / 锐化）引起。",
            "本模块只是启发式判断，不是严格意义上的拼接 / 篡改鉴定器。",
        ],
    }
