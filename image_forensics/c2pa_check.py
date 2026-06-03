"""C2PA Content Credentials check via the optional `c2pa-python` library.

This module is *complementary* to ai_provenance_analysis:
  - ai_provenance_analysis already wraps the **c2patool CLI binary** (Rust),
    plus PROVIDER keyword scanning of metadata blobs. That covers the case
    where the user has the official Adobe / OpenAI tool installed.
  - This module wraps the pure-Python `c2pa-python` package (PyPI). It lets us
    parse C2PA manifests on machines where the CLI is not available (e.g.
    pip-only Windows / macOS environments), and exposes raw manifest
    fields (claim_generator, signature_info, assertions[]) in a structured
    way that is convenient for the report.

Design contract:
  * Soft dependency: if `c2pa` is not importable, return status="SKIPPED_NO_LIBRARY"
    with risk_level="UNKNOWN" and c2pa_score=0.0. No exception leaks.
  * If the file has no C2PA manifest, return status="NO_MANIFEST".
  * If a manifest exists, return:
      - has_active_manifest: bool
      - active_manifest_label: str | None
      - claim_generator: str | None
      - signature_info: dict | None  (issuer / cert_serial_number / time)
      - signature_valid: bool | None (True / False / None=unverified)
      - assertions: list[{label, action?, software_agent?, parameters?}]
  * Risk policy:
      - signature_valid is True  AND assertions contain c2pa.created/edited
        with AI software_agent => HIGH (this matches ai_provenance VERIFIED_*)
      - has_manifest but signature_valid is False (tampered)              => MEDIUM
      - has_manifest, signature unverified                                  => LOW
      - no manifest                                                         => LOW
      - library missing                                                     => UNKNOWN
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _has_c2pa_python() -> bool:
    return importlib.util.find_spec("c2pa") is not None


_AI_SOFTWARE_HINTS = (
    "openai", "dall-e", "dall\u00b7e", "gpt-image", "chatgpt",
    "google", "gemini", "imagen", "synthid",
    "adobe firefly", "firefly",
    "stable diffusion", "comfyui", "automatic1111",
    "midjourney",
    "leonardo", "ideogram", "runway",
)


def _looks_like_ai_software(s: str | None) -> bool:
    if not s:
        return False
    low = s.lower()
    return any(kw in low for kw in _AI_SOFTWARE_HINTS)


def _extract_assertions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the most useful subset of assertions out of a c2pa manifest dict.

    The c2pa-python library returns manifests in the same JSON shape the spec
    documents at https://c2pa.org/specifications/specifications/2.0/specs/_attachments/C2PA_Specification.pdf
    """
    out: list[dict[str, Any]] = []
    assertions = manifest.get("assertions") or []
    for a in assertions:
        if not isinstance(a, dict):
            continue
        label = a.get("label")
        data = a.get("data") if isinstance(a.get("data"), dict) else {}
        if label == "c2pa.actions" or (label or "").startswith("c2pa.actions"):
            for act in (data.get("actions") or []):
                if not isinstance(act, dict):
                    continue
                out.append({
                    "label": label,
                    "action": act.get("action"),
                    "software_agent": act.get("softwareAgent")
                                       or act.get("software_agent"),
                    "parameters": act.get("parameters"),
                })
        else:
            out.append({"label": label, "raw_keys": sorted(list(data.keys()))})
    return out


def analyze_c2pa(input_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)

    if not _has_c2pa_python():
        return {
            "status": "SKIPPED_NO_LIBRARY",
            "risk_level": "UNKNOWN",
            "c2pa_score": 0.0,
            "library": "c2pa-python",
            "evidence_items": [],
            "note": (
                "未安装 `c2pa-python` 库，跳过纯 Python 路径的 C2PA 校验。"
                "若已安装 c2patool 二进制，AI 来源溯源模块仍会读取签名。"
            ),
        }

    try:
        import c2pa  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "status": "SKIPPED_NO_LIBRARY",
            "risk_level": "UNKNOWN",
            "c2pa_score": 0.0,
            "library": "c2pa-python",
            "evidence_items": [],
            "error": f"import failed: {exc}",
        }

    manifest_store: dict[str, Any] | None = None
    err: str | None = None
    try:
        # c2pa-python v0.x exposes Reader; older versions exposed read_file().
        # Try Reader first, then fall back.
        if hasattr(c2pa, "Reader"):
            with c2pa.Reader.from_file(str(input_path)) as reader:  # type: ignore[attr-defined]
                manifest_json = reader.json()
            import json as _json
            manifest_store = _json.loads(manifest_json) if isinstance(manifest_json, str) else manifest_json
        elif hasattr(c2pa, "read_file"):
            manifest_store = c2pa.read_file(str(input_path), None)  # type: ignore[attr-defined]
        else:
            return {
                "status": "SKIPPED_NO_LIBRARY",
                "risk_level": "UNKNOWN",
                "c2pa_score": 0.0,
                "library": "c2pa-python",
                "evidence_items": [],
                "error": "c2pa module present but no Reader/read_file API found",
            }
    except Exception as exc:
        msg = str(exc).lower()
        if "no claim" in msg or "no manifest" in msg or "not found" in msg:
            return {
                "status": "NO_MANIFEST",
                "risk_level": "LOW",
                "c2pa_score": 0.0,
                "library": "c2pa-python",
                "evidence_items": [],
            }
        err = str(exc)

    if err is not None or not manifest_store:
        return {
            "status": "NO_MANIFEST" if err is None else "ERROR",
            "risk_level": "LOW" if err is None else "UNKNOWN",
            "c2pa_score": 0.0,
            "library": "c2pa-python",
            "evidence_items": [],
            **({"error": err} if err else {}),
        }

    active_label = manifest_store.get("active_manifest")
    manifests = manifest_store.get("manifests") or {}
    active = manifests.get(active_label) if active_label else None
    if not active and manifests:
        # take the first one as a fallback
        active_label, active = next(iter(manifests.items()))
    if not active:
        return {
            "status": "NO_MANIFEST",
            "risk_level": "LOW",
            "c2pa_score": 0.0,
            "library": "c2pa-python",
            "evidence_items": [],
        }

    claim_generator = active.get("claim_generator") or active.get("claim_generator_info")
    if isinstance(claim_generator, list) and claim_generator:
        cg = claim_generator[0]
        claim_generator = cg.get("name") if isinstance(cg, dict) else str(cg)

    sig_info = active.get("signature_info") or {}
    validation_status = manifest_store.get("validation_status") or []
    sig_valid: bool | None
    if validation_status:
        # The C2PA spec uses validation status codes; any "failure.*" or
        # "error.*" code means we can't trust the signature.
        bad = any(
            isinstance(v, dict) and str(v.get("code", "")).startswith(("failure", "error"))
            for v in validation_status
        )
        sig_valid = (not bad)
    else:
        sig_valid = None

    assertions = _extract_assertions(active)

    ai_software_agents = sorted({
        a.get("software_agent")
        for a in assertions
        if a.get("software_agent") and _looks_like_ai_software(a.get("software_agent"))
    })
    has_ai_action = bool(ai_software_agents) or _looks_like_ai_software(
        claim_generator if isinstance(claim_generator, str) else None
    )

    if sig_valid is True and has_ai_action:
        risk = "HIGH"
        score = 1.0
        status = "VERIFIED_AI_GENERATED"
    elif sig_valid is False:
        risk = "MEDIUM"
        score = 0.6
        status = "SIGNATURE_INVALID"
    elif sig_valid is None and has_ai_action:
        risk = "MEDIUM"
        score = 0.4
        status = "AI_MANIFEST_UNVERIFIED"
    elif sig_valid is True:
        risk = "LOW"
        score = 0.2
        status = "VERIFIED_NON_AI"
    else:
        risk = "LOW"
        score = 0.1
        status = "MANIFEST_PRESENT_UNVERIFIED"

    evidence: list[dict[str, Any]] = []
    if has_ai_action:
        evidence.append({
            "module": "c2pa_check",
            "severity": "high" if risk == "HIGH" else "medium",
            "title": f"C2PA manifest 声明 AI 生成器：{', '.join(ai_software_agents) or claim_generator}",
            "description": (
                f"c2pa-python 解出的活动 manifest 中包含 AI 软件代理声明。"
                f"签名状态：{ {True:'已验证', False:'失败', None:'未验证'}[sig_valid] }。"
            ),
            "confidence": 0.9 if sig_valid is True else 0.5,
        })
    elif active_label:
        evidence.append({
            "module": "c2pa_check",
            "severity": "info",
            "title": "存在 C2PA Content Credentials manifest",
            "description": (
                f"active_manifest = {active_label}，claim_generator = "
                f"{claim_generator}。签名状态：{ {True:'已验证', False:'失败', None:'未验证'}[sig_valid] }。"
            ),
            "confidence": 0.6 if sig_valid is True else 0.3,
        })

    return {
        "status": status,
        "risk_level": risk,
        "c2pa_score": float(score),
        "library": "c2pa-python",
        "active_manifest_label": active_label,
        "claim_generator": claim_generator if isinstance(claim_generator, str) else None,
        "signature_info": sig_info,
        "signature_valid": sig_valid,
        "ai_software_agents": ai_software_agents,
        "assertions": assertions,
        "evidence_items": evidence,
    }
