"""Quick verification dump of latest test_run results."""
from __future__ import annotations
import json
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _pick_run_dir() -> str:
    # CLI arg > env var > demo_run > test_run (whichever exists with summary.json)
    if len(sys.argv) > 1:
        return os.path.abspath(sys.argv[1])
    env = os.environ.get("FORENSICS_RUN_DIR")
    if env:
        return os.path.abspath(env)
    candidates = [
        os.path.join(ROOT, "analysis_output", "demo_run"),
        os.path.join(ROOT, "analysis_output", "test_run"),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "summary.json")):
            return c
    return candidates[0]

OUT = _pick_run_dir()
print(f"# Inspecting run dir: {OUT}\n")

EXPECT = {
    "normal_png":                       "LOW (clean PNG)",
    "normal_jpeg":                      "LOW (clean JPEG)",
    "commons_lenna":                    "LOW-MEDIUM (clean Lenna)",
    "picsum_grayscale":                 "LOW",
    "picsum_landscape":                 "HIGH (matches reference library)",
    "picsum_portrait":                  "LOW",
    "tiny":                             "LOW",
    "lsb_steg":                         "HIGH (full random LSB)",
    "lsb_text_payload":                 "HIGH (text in LSB)",
    "ai_metadata":                      "HIGH (AI metadata)",
    "trailing_zip":                     "HIGH (zip after IEND)",
    "trailing_text":                    "HIGH (text after EOI)",
    "visible_watermark_getty":          "HIGH if tesseract installed, else LOW",
    "stock_metadata_shutterstock":      "HIGH (Shutterstock metadata)",
    "phash_laundered_match":            "HIGH (resaved/cropped near-dup)",
}

print(
    f"{'name':<32} {'overall':<8} {'steg':<7} {'ext':<7} {'meta':<6} {'ocr':<5} {'phash':<6} "
    f"{'spa':>6} {'chiP':>6} {'dctKS':>6} {'phD':>4}  expectation"
)
print("-" * 150)
for tag, exp in EXPECT.items():
    fs = sorted(glob.glob(os.path.join(OUT, f"{tag}*/report.json")))
    if not fs:
        print(f"{tag:<32} <missing>  {exp}")
        continue
    d = json.load(open(fs[0], encoding="utf-8"))
    st = d.get("steganalysis", {})
    ext = d.get("extraction", {})
    meta = d.get("metadata", {})
    ocr = d.get("visible_watermark", {})
    ph = d.get("phash_match", {})
    dct = d.get("dct_analysis", {})
    overall = d.get("overall", {}).get("risk_level", "-")
    meta_kw = "Y" if meta.get("metadata_stock_keywords") else "-"
    ocr_state = ocr.get("status", "-")[:3]
    ph_state = ph.get("status", "-")[:3]
    ph_best = ph.get("best_distance", 64)
    print(
        f"{tag:<32} {overall:<8} {st.get('risk_level','-'):<7} {ext.get('risk_level','-'):<7} "
        f"{meta_kw:<6} {ocr_state:<5} {ph_state:<6} "
        f"{st.get('spa_max_embedding_rate',0):>6.3f} {st.get('chi_square_max_p_embed',0):>6.3f} "
        f"{dct.get('dct_ks_statistic',0):>6.3f} {ph_best:>4}  {exp}"
    )
