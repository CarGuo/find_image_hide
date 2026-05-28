"""Common utilities."""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".psd"}

# 真正"无损"的容器：LSB 位平面在这里才是可信的检测目标。
# 注意：不在这个集合里的（JPEG / MPO / HEIC / AVIF / WEBP-lossy / JFIF / JP2 / JPS / MPF...）
# 一律视为 lossy —— LSB 平面会被量化和反量化的舍入误差搞成接近白噪声，
# 把白噪声+卡方 P→1 当成"满载隐写"是 Westfeld 1999 论文里就警告过的经典 false positive。
LOSSLESS_FORMATS = {"PNG", "BMP", "TIFF", "TIF", "GIF", "PPM", "PGM", "PSD"}


def is_lossy_format(fmt: str | None) -> bool:
    """判断 PIL `Image.format` / 报告里 input.format 是否为有损容器。

    采用"白名单无损 → 其余全部视为有损"策略，避免今后扩 MPO/HEIC/AVIF 等
    新格式时漏改风险评估代码（这是 issue #1 之前的写法的真正坑点）。
    """
    if not fmt:
        return False
    return fmt.upper() not in LOSSLESS_FORMATS


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTS and path.is_file()


def iter_images(root: Path, recursive: bool = True) -> Iterable[Path]:
    if not root.exists():
        return
    if root.is_file():
        if is_supported_image(root):
            yield root
        return
    pattern = "**/*" if recursive else "*"
    for p in sorted(root.glob(pattern)):
        if is_supported_image(p):
            yield p


def sha256_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.as_posix())
    return mime or "application/octet-stream"


def safe_open_rgb(path: Path, max_side: int | None = None) -> Image.Image:
    img = Image.open(path)
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        img = img.convert("RGB")
    if max_side is not None:
        w, h = img.size
        m = max(w, h)
        if m > max_side:
            ratio = max_side / float(m)
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    return img


def to_numpy_rgb(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img, dtype=np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    return arr


def clamp_to_uint8(a: np.ndarray) -> np.ndarray:
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    mn, mx = float(a.min()), float(a.max())
    if mx - mn < 1e-9:
        return np.zeros_like(a, dtype=np.uint8)
    return ((a - mn) / (mx - mn) * 255.0).astype(np.uint8)
