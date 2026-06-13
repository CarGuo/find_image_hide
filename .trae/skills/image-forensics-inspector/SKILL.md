---
name: "image-forensics-inspector"
description: "Local, offline image forensics: scans a single image or a directory for hidden payloads, LSB/χ²/SPA steganalysis, EXIF/XMP/IPTC metadata, AI provenance (C2PA + keywords), invisible/visible watermarks, ELA, FFT/DCT, copy-move tampering, pHash reverse-lookup, and emits report.json + summary.json + a byte-reproducible forensic PDF. Invoke when an agent (OpenClaw, Hermes, etc.) needs to inspect images for tampering, AI generation, steganography, hidden files, copyright watermarks, or to produce a court-grade reproducible PDF report."
---

# Image Forensics Inspector (Skill)

This skill exposes the [find_image_hide](file:///d:/workspace/project/find_image_hide) project as a reusable capability for **OpenClaw, Hermes, and other agents**. Everything runs **100% locally** — no network calls, no telemetry, no SaaS dependency.

## When to invoke this skill

Invoke when the user/agent task involves any of:

- "Is this image AI-generated / has C2PA / SynthID-like signal?"
- "Is anything hidden inside this PNG/JPG (zip, text, executable, LSB payload)?"
- "Was this image tampered with (copy-move, splicing, ELA bright regions)?"
- "Does this image carry a Shutterstock / Getty / Adobe Firefly watermark?"
- "Reverse-lookup this image against my local reference library (pHash)."
- "Produce a court-grade, byte-reproducible PDF forensic report."
- Batch scanning a folder of images for risk triage (LOW / MEDIUM / HIGH).

## Capability inventory

Mapped to source modules so the agent can cite evidence chain:

| Capability | Source module |
|---|---|
| Basic info + EXIF/XMP/IPTC/PNG text | [basic_info.py](file:///d:/workspace/project/find_image_hide/image_forensics/basic_info.py), [metadata_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py) |
| Hidden payload extraction (trailing zip / EOI text / appended files) | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) |
| Steganalysis (χ² POV, sliding χ², SPA) | [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) |
| External steg tools aggregator (binwalk / zsteg / stegoveritas / stegseek) | [steganalysis_external.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis_external.py) |
| LSB bit-plane analysis | [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) |
| FFT / DCT frequency-domain anomalies | [fft_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/fft_analysis.py), [dct_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/dct_analysis.py) |
| Noise residual + Laplacian | [noise_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/noise_analysis.py) |
| ELA (error level analysis) | [ela.py](file:///d:/workspace/project/find_image_hide/image_forensics/ela.py) |
| Copy-move splice detection (ORB + block match) | [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py) |
| AI provenance (C2PA + keyword) | [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py), [c2pa_check.py](file:///d:/workspace/project/find_image_hide/image_forensics/c2pa_check.py) |
| Invisible watermark (DwtDct, e.g. SDXL/SD2 defaults) | [invisible_watermark_detect.py](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py) |
| Visible watermark OCR (Getty / Shutterstock / "preview only") | [visible_watermark_ocr.py](file:///d:/workspace/project/find_image_hide/image_forensics/visible_watermark_ocr.py) |
| pHash reverse-lookup against local reference dir | [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) |
| Risk scoring (LOW / MEDIUM / HIGH / UNKNOWN) | [scoring.py](file:///d:/workspace/project/find_image_hide/image_forensics/scoring.py) |
| Orchestrator | [analyzer.py](file:///d:/workspace/project/find_image_hide/image_forensics/analyzer.py) |
| Byte-reproducible PDF | [pdf_report.py](file:///d:/workspace/project/find_image_hide/image_forensics/pdf_report.py) |

## Prerequisites

1. Python 3.10+.
2. Install runtime deps:

   ```powershell
   cd d:\workspace\project\find_image_hide
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Optional soft-dependencies (skill degrades gracefully without them — fields are tagged `SKIPPED_NO_LIBRARY` / `SKIPPED_NO_TOOL`):
   - `pip install reportlab` — needed for the byte-reproducible PDF report.
   - `pip install invisible-watermark opencv-python` — DwtDct invisible-watermark decode.
   - `pip install c2pa-python` — pure-Python C2PA verification (or system-wide `c2patool`).
   - System: `tesseract` (visible-watermark OCR), `binwalk` / `zsteg` / `stegoveritas` / `stegseek` (external steg tools).
   - Env var `FORENSICS_PHASH_REFERENCE_DIR=<absolute dir>` — pHash reverse-lookup library.

## Usage modes

### Mode A — CLI (recommended for agent automation)

Entry point: [analyze_image.py](file:///d:/workspace/project/find_image_hide/analyze_image.py)

Single image:

```powershell
python analyze_image.py --input <path-to-image> --output <out-dir>
```

Directory (batch):

```powershell
python analyze_image.py --input <dir> --output <out-dir> --recursive --workers 4
```

stdout (single-image mode) is a JSON object:

```json
{
  "report": "<abs-path>/report.json",
  "risk_level": "LOW|MEDIUM|HIGH|UNKNOWN",
  "confidence": 0.0
}
```

Full machine-readable result lives in `<out-dir>/report.json` (single) or `<out-dir>/summary.json` + `<out-dir>/<slug>__<hash>/report.json` (batch). Schema is summarized in [README.md](file:///d:/workspace/project/find_image_hide/README.md#L306-L326).

### Mode B — Python API (in-process embedding)

```python
from pathlib import Path
from image_forensics.analyzer import analyze_image
from image_forensics.batch import analyze_directory

report = analyze_image(Path("test.jpg"), Path("./out"))
risk = report["overall"]["risk_level"]

summary = analyze_directory(
    Path("./photos"), Path("./out"),
    recursive=True, workers=4,
)
```

Both functions write `report.json` / `summary.json` to the output dir and return the same dict.

### Mode C — Local HTTP API (for non-Python agents like Hermes)

Boot the local server (binds to `127.0.0.1` only):

```powershell
python webapp.py --host 127.0.0.1 --port 5050
```

Then call:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/scan` | Body `{ "directory": "...", "recursive": true, "workers": 2 }` — scan a local absolute path |
| `POST` | `/api/scan_upload` | multipart `files[]` + `paths[]` — upload + scan |
| `POST` | `/api/demo` | Run built-in demo set |
| `GET` | `/api/jobs/<job_id>` | Job status + last 50 results |
| `GET` | `/api/jobs/<job_id>/summary` | Whole-batch `summary.json` |
| `GET` | `/api/jobs/<job_id>/image/<slug>/report` | Single-image full report |
| `GET` | `/api/jobs/<job_id>/image/<slug>/report.pdf` | Court-grade reproducible PDF (sets `X-Pdf-Sha256` / `X-Source-Sha256` headers) |
| `GET` | `/api/pdf/status` | `{available, version, error, package}` for PDF backend |

Full server impl: [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py).

### Mode D — One-shot demo

```powershell
python demo.py            # prepare samples + run
python demo.py --serve    # + start web UI
python demo.py --no-download  # offline-only synthetic samples
```

See [demo.py](file:///d:/workspace/project/find_image_hide/demo.py).

## Output contract

`report.json` schema (full list in [README.md L306-L326](file:///d:/workspace/project/find_image_hide/README.md#L306-L326)):

```json
{
  "schema_version": "0.1.0",
  "input": { "file_name": "...", "format": "PNG", "sha256": "...", ... },
  "overall": {
    "risk_level": "LOW|MEDIUM|HIGH|UNKNOWN",
    "confidence": 0.0,
    "summary": "...",
    "module_scores": { "fft": 0.0, "dct": 0.0, "lsb": 0.0, "noise": 0.0, "metadata": 0.0, "provenance": 0.0 }
  },
  "metadata": { ... },
  "ai_provenance": { "status": "NO_PROVENANCE_FOUND | VERIFIED_AI_GENERATED | VERIFIED_AI_EDITED | PROVENANCE_PRESENT_BUT_UNVERIFIED | POSSIBLE_AI_BUT_UNVERIFIED", ... },
  "frequency_analysis": { ... },
  "dct_analysis": { ... },
  "lsb_analysis": { ... },
  "noise_analysis": { ... },
  "evidence_items": [ ... ]
}
```

Visualizations written alongside `report.json`:

```
visualizations/
  spectrum.png, r/g/b_spectrum.png
  dct_mean_heatmap.png, dct_histogram.png
  lsb_r.png, lsb_g.png, lsb_b.png
  residual.png, laplacian.png
```

## Recommended agent recipes

1. **Triage a folder for an OpenClaw task** — run Mode A in batch, then parse `summary.json` and surface every entry where `risk_level == "HIGH"`; deep-dive each by reading its `report.json` and citing `evidence_items[].description`.
2. **Hermes "is this AI?" check** — run Mode A single-image, read `report["ai_provenance"]["status"]`. Treat `VERIFIED_AI_GENERATED` / `VERIFIED_AI_EDITED` as **hard evidence**; `POSSIBLE_AI_BUT_UNVERIFIED` as soft signal that needs human review; never claim hard AI judgement based solely on `ai_heuristics`.
3. **CTF / payload hunt** — read `report["extraction"]` and `report["external_steganalysis"]`; if either reports trailing zip / archive / `stegseek` hit, extract the file path it emits and follow up.
4. **Court-grade evidence** — call `/api/jobs/.../report.pdf` and capture the `X-Pdf-Sha256` + `X-Source-Sha256` response headers into the case file. Re-rendering the same `report.json` on any machine **must** produce the same PDF SHA-256 (see [P2.4_ACCEPTANCE.md](file:///d:/workspace/project/find_image_hide/docs/P2.4_ACCEPTANCE.md)).

## Honesty / limits the agent MUST surface

- This skill **cannot** prove an image is or is not AI-generated; `ai_heuristics` is hand-tuned thresholds, not a trained classifier. See the "🟠 C 档" section of [README.md](file:///d:/workspace/project/find_image_hide/README.md).
- Classic χ²/SPA steganalysis is **ineffective** against modern adaptive steg (HUGO / WOW / S-UNIWARD).
- SynthID has no official local decoder — only Google's API is authoritative.
- LSB confidence is auto-down-weighted on lossy formats (JPEG).
- No watermark is ever removed, no C2PA is ever forged; this is a read-only forensic tool.

## Security envelope

- All processing is local; no outbound traffic.
- HTTP server defaults to `127.0.0.1`; agents binding `0.0.0.0` accept full responsibility.
- Uploaded files are path-sanitized (`..` rejected, extension whitelisted) and confined to `analysis_output/<job_id>/_uploaded/`.
- Upload size cap defaults to 1 GB (see `MAX_UPLOAD_BYTES` in [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py#L24-L24)).
