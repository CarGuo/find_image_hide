"""Error Level Analysis (ELA, Krawetz/FotoForensics-style).

ELA recompresses the image at a known JPEG quality and shows the per-pixel
difference between the original and the recompressed version. Regions that
have been edited or pasted typically show a different error level than the
surrounding image (because their compression history differs).

This is *not* a definitive splicing detector \u2014 it is a long-standing
visual aid in forensic analysis (Hany Farid, Neal Krawetz).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops

from .utils import safe_open_rgb


def analyze_ela(path: Path, vis_dir: Path, quality: int = 90, scale: float = 15.0) -> dict[str, Any]:
    vis_dir.mkdir(parents=True, exist_ok=True)
    img = safe_open_rgb(Path(path), max_side=1024)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(img, recompressed)

    arr = np.asarray(diff, dtype=np.float32)
    arr = np.clip(arr * scale, 0, 255).astype(np.uint8)
    out_path = vis_dir / "ela.png"
    Image.fromarray(arr).save(out_path)

    err_per_pixel = arr.mean(axis=2)
    h, w = err_per_pixel.shape
    bs = max(32, min(96, min(h, w) // 10))
    locals_mean = []
    for y in range(0, h - bs, bs):
        for x in range(0, w - bs, bs):
            blk = err_per_pixel[y:y + bs, x:x + bs]
            locals_mean.append(float(blk.mean()))
    arr_local = np.asarray(locals_mean) if locals_mean else np.zeros(1)
    inconsistency = float(arr_local.std() / (arr_local.mean() + 1e-6)) if arr_local.size > 1 else 0.0
    score = float(min(1.0, max(0.0, (inconsistency - 0.5) * 1.0)))

    if score > 0.85:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence = []
    if score > 0.55:
        evidence.append({
            "module": "ela",
            "severity": "info",
            "title": "ELA 显示误差水平不均匀",
            "description": "图像中分块 ELA 误差水平差异显著，可能暗示存在粘贴区域或局部重新编码。ELA 在纹理与平滑区域的边界处可能产生误报。",
            "confidence": 0.4,
        })

    return {
        "ela_image": "visualizations/ela.png",
        "ela_quality": quality,
        "ela_scale": scale,
        "ela_inconsistency_score": score,
        "block_mean_std": float(arr_local.std()),
        "block_mean_mean": float(arr_local.mean()),
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "ELA 只是一种启发式可视化辅助手段，亮区不能直接当作篡改证据。",
            "平滑区域、锐利边缘以及不同纹理本身就会产生 ELA 对比度。",
            "把整张图重新存一次（任意质量）就会抹掉 ELA 痕迹。",
        ],
    }
