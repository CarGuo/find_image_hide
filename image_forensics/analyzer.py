"""Single-image analyzer: orchestrates all modules and writes report.json."""
from __future__ import annotations

import json
import os
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ai_provenance_analysis import analyze_ai_provenance
from .basic_info import collect_basic_info
from .dct_analysis import analyze_dct
from .ela import analyze_ela
from .extraction import analyze_extraction
from .fft_analysis import analyze_fft
from .invisible_watermark_detect import analyze_invisible_watermark
from .lsb_analysis import analyze_lsb
from .metadata_analysis import collect_metadata
from .noise_analysis import analyze_noise
from .phash_match import analyze_phash_match
from .scoring import aggregate
from .steganalysis import analyze_steganalysis
from .visible_watermark_ocr import analyze_visible_watermark


def analyze_image(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    vis_dir = output_dir / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)
    vis_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    try:
        basic = collect_basic_info(input_path)
    except Exception as exc:
        basic = {"file_name": input_path.name, "file_path": str(input_path), "error": str(exc)}
        errors.append(f"basic_info: {exc}")

    try:
        meta = collect_metadata(input_path)
    except Exception as exc:
        meta = {"raw": {}, "error": str(exc)}
        errors.append(f"metadata: {exc}")

    try:
        prov = analyze_ai_provenance(input_path, meta)
    except Exception as exc:
        prov = {"status": "NO_PROVENANCE_FOUND", "risk_level": "UNKNOWN", "error": str(exc)}
        errors.append(f"ai_provenance: {exc}")

    try:
        fft = analyze_fft(input_path, vis_dir)
    except Exception as exc:
        fft = {"risk_level": "UNKNOWN", "spectrum_anomaly_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"fft: {exc}\n{traceback.format_exc()}")

    try:
        dct = analyze_dct(input_path, vis_dir)
    except Exception as exc:
        dct = {"risk_level": "UNKNOWN", "dct_anomaly_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"dct: {exc}")

    fmt = (basic.get("format") or "").upper()
    from .utils import is_lossy_format
    is_lossy = is_lossy_format(fmt)
    try:
        lsb = analyze_lsb(input_path, vis_dir, is_lossy=is_lossy)
    except Exception as exc:
        lsb = {"risk_level": "UNKNOWN", "lsb_anomaly_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"lsb: {exc}")

    try:
        noise = analyze_noise(input_path, vis_dir)
    except Exception as exc:
        noise = {"risk_level": "UNKNOWN", "noise_inconsistency_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"noise: {exc}")

    try:
        steg = analyze_steganalysis(input_path, is_lossy=is_lossy)
    except Exception as exc:
        steg = {"risk_level": "UNKNOWN", "steganalysis_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"steganalysis: {exc}")

    try:
        ext = analyze_extraction(input_path)
    except Exception as exc:
        ext = {"risk_level": "UNKNOWN", "extraction_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"extraction: {exc}")

    try:
        ela = analyze_ela(input_path, vis_dir)
    except Exception as exc:
        ela = {"risk_level": "UNKNOWN", "ela_inconsistency_score": 0.0, "error": str(exc), "evidence_items": []}
        errors.append(f"ela: {exc}")

    try:
        visible_wm = analyze_visible_watermark(input_path, vis_dir)
    except Exception as exc:
        visible_wm = {"status": "ERROR", "risk_level": "UNKNOWN", "ocr_score": 0.0, "hits": [], "evidence_items": [], "error": str(exc)}
        errors.append(f"visible_watermark: {exc}")

    ref_dir_env = os.environ.get("FORENSICS_PHASH_REFERENCE_DIR")
    try:
        phash = analyze_phash_match(input_path, Path(ref_dir_env) if ref_dir_env else None)
    except Exception as exc:
        phash = {"status": "ERROR", "risk_level": "UNKNOWN", "phash_score": 0.0, "matches": [], "evidence_items": [], "error": str(exc)}
        errors.append(f"phash_match: {exc}")

    try:
        invisible_wm = analyze_invisible_watermark(input_path)
    except Exception as exc:
        invisible_wm = {"status": "ERROR", "risk_level": "UNKNOWN", "score": 0.0, "decoded": [], "evidence_items": [], "error": str(exc)}
        errors.append(f"invisible_watermark: {exc}")

    report: dict[str, Any] = {
        "schema_version": "0.3.0",
        "tool_name": "Image Forensics Inspector",
        "analysis_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": basic,
        "metadata": meta,
        "ai_provenance": prov,
        "frequency_analysis": fft,
        "dct_analysis": dct,
        "lsb_analysis": lsb,
        "noise_analysis": noise,
        "steganalysis": steg,
        "extraction": ext,
        "ela": ela,
        "visible_watermark": visible_wm,
        "invisible_watermark": invisible_wm,
        "phash_match": phash,
        "errors": errors,
    }
    overall = aggregate(report)
    report["overall"] = overall

    all_evidence: list[dict[str, Any]] = []
    for module_name, module in (
        ("metadata", meta),
        ("fft", fft), ("dct", dct), ("lsb", lsb), ("noise", noise),
        ("steganalysis", steg), ("extraction", ext), ("ela", ela),
        ("visible_watermark", visible_wm), ("invisible_watermark", invisible_wm),
        ("phash_match", phash),
    ):
        for item in module.get("evidence_items", []) or []:
            all_evidence.append({**item, "module": item.get("module", module_name)})
    if prov.get("status") and prov.get("status") != "NO_PROVENANCE_FOUND":
        _PROV_CN = {
            "VERIFIED_AI_GENERATED": "已验证：AI 生成",
            "VERIFIED_AI_EDITED": "已验证：AI 编辑过",
            "PROVENANCE_PRESENT_BUT_UNVERIFIED": "存在 C2PA 来源凭证但未通过签名校验",
            "POSSIBLE_AI_BUT_UNVERIFIED": "元数据疑似 AI 生成但缺少可信凭证",
        }
        status_cn = _PROV_CN.get(prov["status"], prov["status"])
        provs = prov.get("detected_providers") or []
        provs_text = "、".join(provs) if provs else "无"
        all_evidence.append({
            "module": "ai_provenance",
            "severity": "info" if "VERIFIED" not in prov["status"] else "warning",
            "title": f"AI 来源溯源：{status_cn}",
            "description": f"在元数据 / C2PA 中检测到的来源提供方：{provs_text}",
            "confidence": 0.5,
        })

    fp = (prov.get("synthid") or {}).get("frequency_probe") or {}
    if fp.get("available") and fp.get("suspicion") in ("medium", "high"):
        sev = "high" if fp["suspicion"] == "high" else "medium"
        all_evidence.append({
            "module": "ai_provenance",
            "severity": sev,
            "title": f"SynthID 频域启发式指纹：{fp['suspicion']} 可疑度",
            "description": (
                f"参考 reverse-SynthID 公布的 1024×1024 低频载频网格，"
                f"绿通道 FFT 中候选 bin 平均能量 {fp.get('peak_ratio_mean'):.2f} 倍背景，"
                f"P95 = {fp.get('peak_ratio_p95'):.2f} 倍，"
                f"相位圆方差 {fp.get('phase_circular_variance'):.3f}（越小越像固定模板）。"
                f"{fp.get('reason', '')}"
                "—— 该指标仅作启发式提示，权威验证需走 Google 官方接口。"
            ),
            "confidence": 0.4 if sev == "medium" else 0.6,
        })
    report["evidence_items"] = all_evidence

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (output_dir / "ai_provenance.json").write_text(
        json.dumps(prov, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return report
