"""Regression harness: analyze every image under tools/test_images and dump
key fields (overall / invisible_watermark / copyright_summary) for review."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from image_forensics.analyzer import analyze_image  # noqa: E402

IMG_DIR = ROOT / "tools" / "test_images"


def short(d, keys):
    return {k: d.get(k) for k in keys if k in d}


def summarize(report: dict) -> dict:
    overall = report.get("overall", {}) or {}
    inv = report.get("invisible_watermark", {}) or {}
    meta = report.get("metadata", {}) or {}
    cs = meta.get("copyright_summary", {}) or {}
    vw = report.get("visible_watermark", {}) or {}
    prov = report.get("ai_provenance", {}) or {}
    ext = report.get("extraction", {}) or {}
    steg = report.get("steganalysis", {}) or {}
    lsb = report.get("lsb_analysis", {}) or {}
    return {
        "overall_risk": overall.get("risk_level"),
        "overall_confidence": overall.get("confidence"),
        "overall_summary": overall.get("summary"),
        "invisible_watermark": {
            "status": inv.get("status"),
            "risk_level": inv.get("risk_level"),
            "score": inv.get("score"),
            "best_text": inv.get("best_text"),
            "best_known_match": inv.get("best_known_match"),
            "decoded": inv.get("decoded"),
        },
        "copyright_summary": cs,
        "metadata_stock_hits": meta.get("metadata_stock_hits"),
        "metadata_ai_keywords": meta.get("metadata_ai_keywords"),
        "visible_watermark": {
            "risk_level": vw.get("risk_level"),
            "ocr_score": vw.get("ocr_score"),
            "hits": vw.get("hits"),
        },
        "ai_provenance": {
            "status": prov.get("status"),
            "risk_level": prov.get("risk_level"),
            "detected_providers": prov.get("detected_providers"),
        },
        "extraction_risk": ext.get("risk_level"),
        "extraction_score": ext.get("extraction_score"),
        "steganalysis_risk": steg.get("risk_level"),
        "steganalysis_score": steg.get("steganalysis_score"),
        "lsb_risk": lsb.get("risk_level"),
        "lsb_score": lsb.get("lsb_anomaly_score"),
    }


TARGET = {
    "normal_jpeg.jpg",
    "normal_png.png",
    "invisible_watermark_dwtdct.jpg",
    "iptc_full_copyright.jpg",
    "ai_forged_copyright.jpg",
    "visible_watermark_getty.jpg",
    "visible_watermark_shutterstock.jpg",
    "visible_watermark_istock.jpg",
    "visible_watermark_unsplash.jpg",
    "visible_watermark_adobestock.jpg",
    "visible_watermark_alamy.jpg",
    "lsb_steg.png",
    "trailing_zip.png",
    "ai_metadata.png",
}


def main():
    results = {}
    images = sorted(IMG_DIR.iterdir())
    for p in images:
        if not p.is_file():
            continue
        if p.name not in TARGET:
            continue
        td = tempfile.mkdtemp(prefix="forensics_reg_")
        try:
            print(f">>> {p.name}", flush=True)
            rep = analyze_image(str(p), td)
            results[p.name] = summarize(rep)
        except Exception as exc:
            results[p.name] = {"error": f"{type(exc).__name__}: {exc}"}
            print("    ERROR:", exc, flush=True)

    out_path = ROOT / "tools" / "regression_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
