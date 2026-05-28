"""Aggregate scoring."""
from __future__ import annotations

from typing import Any

RISK_RANK = {"LOW": 0, "UNKNOWN": 1, "MEDIUM": 2, "HIGH": 3}
RANK_RISK = {v: k for k, v in RISK_RANK.items()}


def _r(level: str) -> int:
    return RISK_RANK.get(level, 1)


def aggregate(report: dict[str, Any]) -> dict[str, Any]:
    fmt = (report.get("input", {}).get("format") or "").upper()
    is_lossy = fmt in {"JPEG", "JPG", "WEBP"}

    fft = report.get("frequency_analysis", {})
    dct = report.get("dct_analysis", {})
    lsb = report.get("lsb_analysis", {})
    noise = report.get("noise_analysis", {})
    prov = report.get("ai_provenance", {})
    meta = report.get("metadata", {})
    steg = report.get("steganalysis", {})
    ext = report.get("extraction", {})
    ela = report.get("ela", {})
    vis_wm = report.get("visible_watermark", {})
    phash = report.get("phash_match", {})

    # Weights: industry-standard steganalysis (chi-square / SPA) and direct
    # extraction findings dominate, since they are *evidence* rather than
    # heuristics. FFT/DCT/LSB-entropy are weak supporting signals.
    weights = {
        "extraction": 0.30,
        "steganalysis": 0.20,
        "fft": 0.05,
        "dct": 0.05,
        "lsb": 0.05 if is_lossy else 0.10,
        "noise": 0.05,
        "ela": 0.05,
        "metadata": 0.05,
        "provenance": 0.10,
        "visible_watermark": 0.10,
        "phash_match": 0.10,
    }

    meta_score = 0.0
    if meta.get("metadata_stock_hits"):
        meta_score = 0.7
    elif meta.get("metadata_ai_keywords"):
        meta_score = 0.6
    elif meta.get("suspicious_fields"):
        meta_score = 0.2

    prov_score = {
        "VERIFIED_AI_GENERATED": 1.0,
        "VERIFIED_AI_EDITED": 0.8,
        "PROVENANCE_PRESENT_BUT_UNVERIFIED": 0.5,
        "POSSIBLE_AI_BUT_UNVERIFIED": 0.4,
        "NO_PROVENANCE_FOUND": 0.0,
        "PROVENANCE_STRIPPED_OR_UNKNOWN": 0.2,
    }.get(prov.get("status", ""), 0.0)

    raw = (
        weights["extraction"] * float(ext.get("extraction_score", 0.0))
        + weights["steganalysis"] * float(steg.get("steganalysis_score", 0.0))
        + weights["fft"] * float(fft.get("spectrum_anomaly_score", 0.0))
        + weights["dct"] * float(dct.get("dct_anomaly_score", 0.0))
        + weights["lsb"] * float(lsb.get("lsb_anomaly_score", 0.0))
        + weights["noise"] * float(noise.get("noise_inconsistency_score", 0.0))
        + weights["ela"] * float(ela.get("ela_inconsistency_score", 0.0))
        + weights["metadata"] * meta_score
        + weights["provenance"] * prov_score
        + weights["visible_watermark"] * float(vis_wm.get("ocr_score", 0.0))
        + weights["phash_match"] * float(phash.get("phash_score", 0.0))
    )
    confidence = float(min(1.0, max(0.0, raw)))

    levels = [
        ext.get("risk_level", "LOW"),
        steg.get("risk_level", "LOW"),
        fft.get("risk_level", "LOW"),
        dct.get("risk_level", "LOW"),
        lsb.get("risk_level", "LOW") if not is_lossy else "LOW",
        noise.get("risk_level", "LOW"),
        ela.get("risk_level", "LOW"),
        prov.get("risk_level", "UNKNOWN"),
        vis_wm.get("risk_level", "LOW"),
        phash.get("risk_level", "LOW"),
    ]
    high_count = sum(1 for l in levels if l == "HIGH")
    med_count = sum(1 for l in levels if l == "MEDIUM")

    # Risk escalation: HIGH only fires on *direct evidence*, not on the
    # accumulation of weak signals. This matches how forensic tools (FotoForensics,
    # StegExpose, zsteg) communicate findings.
    lsb_white_noise = lsb.get("lsb_anomaly_score", 0.0) >= 0.9
    spa = float(steg.get("spa_max_embedding_rate", 0.0)) if steg else 0.0
    chi_p = float(steg.get("chi_square_max_p_embed", 0.0)) if steg else 0.0
    # "Full-LSB-replacement" signature: the LSB plane is statistically white
    # noise on every channel, AND the chi-square POV test agrees. SPA can sit
    # near 0 (math fixed point) or near 1 in this case, so we use chi+lsb
    # consensus (this is exactly what StegSecret + stegdetect's plain-LSB
    # test does).
    full_lsb_replacement = (not is_lossy) and lsb_white_noise and chi_p >= 0.95

    direct_high = (
        prov.get("status") in ("VERIFIED_AI_GENERATED", "VERIFIED_AI_EDITED")
        or ext.get("risk_level") == "HIGH"
        or steg.get("risk_level") == "HIGH"
        or full_lsb_replacement
        or (not is_lossy and lsb.get("risk_level") == "HIGH")
        or bool(meta.get("metadata_stock_hits"))
        or vis_wm.get("risk_level") == "HIGH"
        or phash.get("risk_level") == "HIGH"
    )
    if direct_high:
        overall = "HIGH"
    elif ext.get("risk_level") == "MEDIUM" or steg.get("risk_level") == "MEDIUM":
        overall = "MEDIUM"
    elif med_count >= 2 or confidence > 0.5:
        overall = "MEDIUM"
    elif med_count >= 1:
        overall = "MEDIUM" if confidence > 0.35 else "UNKNOWN"
    else:
        overall = "LOW"

    summary_parts: list[str] = []
    if vis_wm.get("hits"):
        kws = ", ".join(sorted({h["keyword"] for h in vis_wm["hits"]}))
        summary_parts.append(f"Visible watermark / copyright text detected via OCR: {kws}.")
    if phash.get("matches"):
        best = phash["matches"][0]
        summary_parts.append(f"Image is a near-duplicate of reference '{best['reference']}' (Hamming distance={best['distance']}).")
    if meta.get("metadata_stock_hits"):
        kws = ", ".join(sorted({h["keyword"] for h in meta["metadata_stock_hits"]}))
        summary_parts.append(f"Copyrighted stock-image signature found in metadata: {kws}.")
    if full_lsb_replacement:
        summary_parts.append("LSB plane is statistically white noise on all channels AND chi-square test confirms; the image likely has its LSB plane fully replaced (random data or a maximally-embedded payload).")
    if ext.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"Extraction findings: {ext.get('risk_level')} (see Extraction tab).")
    if steg.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"Steganalysis (chi-square / SPA): {steg.get('risk_level')}.")
    if prov.get("status") == "NO_PROVENANCE_FOUND":
        summary_parts.append("No verified AI provenance metadata was found.")
    elif prov.get("status") == "POSSIBLE_AI_BUT_UNVERIFIED":
        summary_parts.append(f"Possible AI provider keywords found: {prov.get('detected_providers')}.")
    elif prov.get("status", "").startswith("VERIFIED"):
        summary_parts.append(f"Verified provenance: {prov.get('status')}.")
    if fft.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"FFT anomaly: {fft.get('risk_level')}.")
    if dct.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"DCT anomaly: {dct.get('risk_level')}.")
    if not is_lossy and lsb.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"LSB anomaly: {lsb.get('risk_level')}.")
    if noise.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"Noise inconsistency: {noise.get('risk_level')}.")
    if ela.get("risk_level") in ("MEDIUM", "HIGH"):
        summary_parts.append(f"ELA inconsistency: {ela.get('risk_level')}.")
    if not summary_parts:
        summary_parts.append("No obvious watermark or steganography signal was found, but absence of evidence is not evidence of absence.")

    return {
        "risk_level": overall,
        "confidence": round(confidence, 3),
        "summary": " ".join(summary_parts),
        "module_scores": {
            "extraction": float(ext.get("extraction_score", 0.0)),
            "steganalysis": float(steg.get("steganalysis_score", 0.0)),
            "fft": float(fft.get("spectrum_anomaly_score", 0.0)),
            "dct": float(dct.get("dct_anomaly_score", 0.0)),
            "lsb": float(lsb.get("lsb_anomaly_score", 0.0)),
            "noise": float(noise.get("noise_inconsistency_score", 0.0)),
            "ela": float(ela.get("ela_inconsistency_score", 0.0)),
            "metadata": meta_score,
            "provenance": prov_score,
            "visible_watermark": float(vis_wm.get("ocr_score", 0.0)),
            "phash_match": float(phash.get("phash_score", 0.0)),
        },
        "limitations": [
            "This tool cannot prove that an image has no watermark.",
            "Unknown private watermarking schemes may not be detectable.",
            "C2PA metadata may be stripped by screenshots, recompression, social platforms, or format conversion.",
            "SynthID requires official verification support.",
            "Chi-square / SPA detect classical LSB-replacement; LSB-matching, F5, or modern adaptive embeddings may evade them.",
            "All scores are heuristic and must not be used as legal evidence.",
        ],
    }
