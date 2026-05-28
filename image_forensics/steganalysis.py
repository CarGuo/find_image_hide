"""Statistical steganalysis using industry-standard methods.

Implements:
  - Chi-square attack (Westfeld & Pfitzmann, 1999) -> probability that LSBs of
    Pairs-of-Values (2k, 2k+1) are equalized, which happens when LSB embedding
    is performed on a contiguous stream. Produces a per-channel "embedding
    likelihood" map and a global probability.
  - Sample Pair Analysis (Dumitrescu, Wu, Wang / Fridrich), aka SPA -> estimates
    the LSB embedding rate p in [0, 1] from horizontal pixel pairs.

These are the same techniques used by tools like StegExpose, Stegdetect,
Aletheia, and StegSecret, and are the de-facto "industry standard" for
detecting LSB replacement steganography in lossless raster images.

References:
  Westfeld & Pfitzmann, "Attacks on Steganographic Systems", 1999.
  Dumitrescu, Wu, Wang, "Detection of LSB Steganography via Sample Pair
  Analysis", 2003.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .utils import safe_open_rgb, to_numpy_rgb


def _chi_square_pov(channel: np.ndarray) -> dict[str, Any]:
    """Westfeld & Pfitzmann chi-square test on the whole channel.

    For each Pair of Values (2k, 2k+1), under LSB embedding the two histogram
    counts become equal, so the chi-square distance to (n/2, n/2) shrinks.
    A SMALL chi-square -> HIGH probability of embedding.
    """
    flat = channel.ravel().astype(np.int64)
    hist = np.bincount(flat, minlength=256).astype(np.float64)
    chi = 0.0
    dof = 0
    for k in range(128):
        n0 = hist[2 * k]
        n1 = hist[2 * k + 1]
        n = n0 + n1
        if n < 5:
            continue
        expected = n / 2.0
        chi += ((n0 - expected) ** 2 + (n1 - expected) ** 2) / expected
        dof += 1
    if dof <= 0:
        return {"chi2": float("nan"), "dof": 0, "p_embed": 0.0}
    try:
        from scipy.stats import chi2 as chi2_dist
        p_not_embed = float(chi2_dist.sf(chi, dof))
    except Exception:
        p_not_embed = float(np.exp(-max(0.0, (chi - dof) / max(1.0, np.sqrt(2.0 * dof)))))
    p_embed = float(max(0.0, min(1.0, 1.0 - p_not_embed)))
    return {"chi2": float(chi), "dof": int(dof), "p_embed": p_embed}


def _chi_square_sliding(channel: np.ndarray, blocks: int = 32) -> dict[str, Any]:
    """Sliding chi-square along scanline order (classic Westfeld curve).

    A sequential LSB embedding shows a prefix of high p_embed that drops as
    the cursor passes the embedded length. We compute p_embed in cumulative
    blocks and report the prefix that stays above 0.5.
    """
    flat = channel.ravel()
    n = flat.size
    if n < 1024:
        return {"prefix_embed_ratio": 0.0, "curve": []}
    step = max(256, n // blocks)
    curve = []
    cumulative_hist = np.zeros(256, dtype=np.int64)
    high_run = 0
    last_high = 0
    for i in range(step, n + 1, step):
        cumulative_hist[:] = np.bincount(flat[:i], minlength=256)
        chi = 0.0
        dof = 0
        for k in range(128):
            n0 = cumulative_hist[2 * k]
            n1 = cumulative_hist[2 * k + 1]
            tot = n0 + n1
            if tot < 5:
                continue
            expected = tot / 2.0
            chi += ((n0 - expected) ** 2 + (n1 - expected) ** 2) / expected
            dof += 1
        try:
            from scipy.stats import chi2 as chi2_dist
            p_not = float(chi2_dist.sf(chi, max(1, dof)))
        except Exception:
            p_not = float(np.exp(-max(0.0, (chi - dof) / max(1.0, np.sqrt(2.0 * max(1, dof))))))
        p_embed = max(0.0, min(1.0, 1.0 - p_not))
        curve.append({"position_ratio": i / n, "p_embed": p_embed})
        if p_embed > 0.5:
            high_run += 1
            last_high = i
    prefix = last_high / n if last_high else 0.0
    return {"prefix_embed_ratio": float(prefix), "curve": curve}


def _sample_pair_analysis(channel: np.ndarray) -> dict[str, Any]:
    """Sample Pair Analysis (Dumitrescu/Wu/Wang) -> estimated embedding rate p.

    Uses horizontally adjacent pairs (u, v). Pairs are classified into:
      X = pairs with v even and u<v, or v odd and u>v
      Y = pairs with v even and u>v, or v odd and u<v
      Z = pairs with u==v
      W = pairs with |u-v| differing by exactly 2 in a way that makes them
          'primary' (see paper)
    The estimator solves a quadratic for p.
    """
    a = channel[:, :-1].astype(np.int32).ravel()
    b = channel[:, 1:].astype(np.int32).ravel()
    diff = b - a
    same = diff == 0
    even_v = (b % 2 == 0)
    odd_v = ~even_v

    X = int(np.sum(((even_v & (a < b)) | (odd_v & (a > b))) & ~same))
    Y = int(np.sum(((even_v & (a > b)) | (odd_v & (a < b))) & ~same))
    Z = int(np.sum(same))
    total = X + Y + Z
    if total == 0:
        return {"embedding_rate": 0.0, "X": X, "Y": Y, "Z": Z}

    # Quadratic: 0.5 * (X + Y) * p^2 + (Y - X - 2*Z) * p + (Y - X) = 0
    A = 0.5 * (X + Y)
    B = (Y - X - 2.0 * Z)
    C = float(Y - X)
    if abs(A) < 1e-9:
        p = 0.0 if abs(B) < 1e-9 else max(0.0, min(1.0, -C / B))
    else:
        disc = B * B - 4.0 * A * C
        if disc < 0:
            p = 0.0
        else:
            sq = float(np.sqrt(disc))
            roots = [(-B + sq) / (2.0 * A), (-B - sq) / (2.0 * A)]
            roots = [r for r in roots if 0.0 <= r <= 1.0] or [max(0.0, min(1.0, r)) for r in roots]
            p = float(min(roots, key=abs))
    return {
        "embedding_rate": float(max(0.0, min(1.0, p))),
        "X": X, "Y": Y, "Z": Z,
    }


def analyze_steganalysis(path: Path, is_lossy: bool) -> dict[str, Any]:
    """Run chi-square + SPA on each RGB channel and aggregate."""
    img = safe_open_rgb(Path(path), max_side=1024)
    arr = to_numpy_rgb(img)

    per_channel: dict[str, Any] = {}
    chi_p_max = 0.0
    spa_max = 0.0
    chi_prefix_max = 0.0
    for idx, ch_name in enumerate(("r", "g", "b")):
        ch = arr[..., idx]
        chi = _chi_square_pov(ch)
        chi_slide = _chi_square_sliding(ch)
        spa = _sample_pair_analysis(ch)
        per_channel[ch_name] = {
            "chi_square": chi,
            "chi_square_sliding": chi_slide,
            "sample_pair_analysis": spa,
        }
        chi_p_max = max(chi_p_max, chi["p_embed"])
        chi_prefix_max = max(chi_prefix_max, chi_slide["prefix_embed_ratio"])
        spa_max = max(spa_max, spa["embedding_rate"])

    if is_lossy:
        chi_p_max *= 0.3
        spa_max *= 0.3
        chi_prefix_max *= 0.3

    score = float(min(1.0, max(chi_p_max, spa_max, chi_prefix_max)))
    # Industry-standard thresholds (StegExpose / Aletheia practice):
    # SPA naturally floats around 0.0-0.10 on noisy natural images, so we only
    # treat SPA >= 0.20 as strong evidence and SPA >= 0.10 as supporting.
    # Chi-square pov + sliding prefix are HIGHLY CORRELATED and both can hit
    # P~1 on smooth / synthetic natural images (a well-known weakness of
    # Westfeld's test). To avoid those false positives we require a MULTI-
    # DETECTOR CONSENSUS for HIGH risk: SPA must agree with the chi-square
    # signal. SPA alone, with a very high rate, also counts as direct evidence.
    spa_very_strong = spa_max >= 0.50            # near-fully-embedded
    spa_strong = spa_max >= 0.40                  # supporting only with chi
    spa_support = spa_max >= 0.20
    chi_pov_strong = chi_p_max >= 0.95
    chi_prefix_strong = chi_prefix_max >= 0.5
    consensus_high = spa_support and chi_pov_strong and chi_prefix_strong
    if spa_very_strong or (spa_strong and chi_pov_strong) or consensus_high:
        risk = "HIGH"
    elif spa_max >= 0.10 or (chi_pov_strong and chi_prefix_strong):
        risk = "MEDIUM"
    else:
        risk = "LOW"

    evidence: list[dict[str, Any]] = []
    if not is_lossy and spa_max >= 0.10:
        sev = "warning" if spa_max >= 0.20 else "info"
        evidence.append({
            "module": "steganalysis",
            "severity": sev,
            "title": f"Sample Pair Analysis estimates LSB embedding rate ~{spa_max*100:.1f}%",
            "description": "Sample Pair Analysis (Dumitrescu/Wu/Wang, 2003) estimates the fraction of pixels modified by LSB-replacement steganography. Rates >=20% are strong evidence; 10-20% may also occur on highly textured natural images.",
            "confidence": 0.7 if spa_max >= 0.20 else 0.4,
        })
    if not is_lossy and chi_p_max >= 0.95 and chi_prefix_max >= 0.2:
        evidence.append({
            "module": "steganalysis",
            "severity": "warning",
            "title": f"Chi-square LSB attack: P(embedding) = {chi_p_max:.3f}, prefix ratio = {chi_prefix_max:.2f}",
            "description": "Westfeld & Pfitzmann's chi-square test (1999) reports a high probability that the LSB pairs-of-values histogram has been equalized, AND a sliding chi-square confirms a long high-probability prefix. Combined, these are characteristic of LSB-replacement steganography.",
            "confidence": 0.65,
        })
    if not is_lossy and chi_prefix_max >= 0.5:
        evidence.append({
            "module": "steganalysis",
            "severity": "warning",
            "title": f"Sequential LSB prefix detected (~{chi_prefix_max*100:.1f}% of stream)",
            "description": "Sliding chi-square shows a long initial prefix where embedding probability stays high, then drops. This is the classical 'Westfeld curve' for sequential LSB tools (e.g. Steghide-like).",
            "confidence": 0.6,
        })

    return {
        "per_channel": per_channel,
        "chi_square_max_p_embed": chi_p_max,
        "spa_max_embedding_rate": spa_max,
        "chi_square_prefix_max": chi_prefix_max,
        "steganalysis_score": score,
        "risk_level": risk,
        "evidence_items": evidence,
        "limitations": [
            "Chi-square and SPA only reliably detect LSB-replacement steganography in lossless formats.",
            "JPEG / WebP-lossy compression destroys the LSB plane; results on lossy formats are not reliable.",
            "These tests do not detect F5, OutGuess, JSteg matrix embedding, or modern LSB-matching (\u00b11) schemes.",
        ],
    }
