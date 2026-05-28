"""AI provenance analysis: C2PA + provider keyword matching."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROVIDER_KEYWORDS = {
    "OpenAI": ["openai", "chatgpt", "dall-e", "dall\u00b7e", "gpt-4o", "gpt image"],
    "Google": ["google", "gemini", "imagen", "deepmind", "synthid"],
    "Adobe": ["adobe", "firefly", "photoshop", "lightroom", "content credentials"],
    "StableDiffusion": ["stable diffusion", "comfyui", "automatic1111", "invokeai"],
    "Midjourney": ["midjourney"],
    "Other": ["leonardo", "ideogram", "runway", "kling"],
}

AI_KEYWORDS_FLAT = [kw for kws in PROVIDER_KEYWORDS.values() for kw in kws] + [
    "c2pa", "contentauthenticity", "claim_generator",
]


def _detect_providers_from_text(blob: str) -> tuple[list[str], list[str]]:
    low = blob.lower()
    providers: list[str] = []
    tools: list[str] = []
    for prov, kws in PROVIDER_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                if prov not in providers:
                    providers.append(prov)
                if kw not in tools:
                    tools.append(kw)
    return providers, tools


def _try_c2patool(path: Path) -> tuple[bool, dict[str, Any] | None]:
    """Try to call c2patool if installed; return (available, parsed_json)."""
    exe = shutil.which("c2patool")
    if not exe:
        return False, None
    try:
        proc = subprocess.run(
            [exe, str(path), "--detailed"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            proc = subprocess.run(
                [exe, str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        if proc.returncode != 0:
            return True, {"error": proc.stderr.strip() or proc.stdout.strip()}
        out = proc.stdout.strip()
        if not out:
            return True, None
        try:
            return True, json.loads(out)
        except Exception:
            return True, {"raw": out}
    except Exception as exc:
        return True, {"error": str(exc)}


def _extract_c2pa_fields(c2pa_json: dict[str, Any] | None) -> dict[str, Any]:
    out = {
        "claim_generator": None,
        "producer": None,
        "issuer": None,
        "actions": [],
        "ingredients": [],
        "verified": None,
    }
    if not c2pa_json or not isinstance(c2pa_json, dict):
        return out
    out["claim_generator"] = c2pa_json.get("claim_generator")
    manifests = c2pa_json.get("manifests") or {}
    active = c2pa_json.get("active_manifest")
    manifest = None
    if isinstance(manifests, dict) and active and active in manifests:
        manifest = manifests[active]
    elif isinstance(manifests, dict) and manifests:
        manifest = next(iter(manifests.values()))
    if manifest and isinstance(manifest, dict):
        out["claim_generator"] = manifest.get("claim_generator") or out["claim_generator"]
        out["issuer"] = (manifest.get("signature_info") or {}).get("issuer")
        sig = manifest.get("signature_info") or {}
        out["verified"] = sig.get("validated")
        assertions = manifest.get("assertions") or []
        for a in assertions:
            label = a.get("label", "")
            data = a.get("data") or {}
            if "actions" in label:
                acts = data.get("actions") or []
                for act in acts:
                    if isinstance(act, dict):
                        out["actions"].append(act.get("action"))
            if "ingredient" in label:
                out["ingredients"].append(data)
        producer = manifest.get("producer")
        if producer:
            out["producer"] = producer
    return out


def analyze_ai_provenance(path: Path, metadata_result: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(metadata_result.get("raw", {}), default=str, ensure_ascii=False)
    providers_meta, tools_meta = _detect_providers_from_text(blob)

    c2pa_available, c2pa_json = _try_c2patool(Path(path))
    c2pa_fields = _extract_c2pa_fields(c2pa_json)

    c2pa_present = c2pa_json is not None and not (
        isinstance(c2pa_json, dict) and "error" in c2pa_json and len(c2pa_json) == 1
    )
    if c2pa_json and isinstance(c2pa_json, dict) and "error" in c2pa_json:
        c2pa_present = False

    if c2pa_present:
        extra = json.dumps(c2pa_fields, default=str, ensure_ascii=False)
        p2, t2 = _detect_providers_from_text(extra)
        for p in p2:
            if p not in providers_meta:
                providers_meta.append(p)
        for t in t2:
            if t not in tools_meta:
                tools_meta.append(t)

    actions = [a for a in (c2pa_fields.get("actions") or []) if a]
    is_generated = any(a and ("generated" in a or "created" in a or "produced" in a) for a in actions)
    is_edited = any(a and ("edited" in a or "transformed" in a or "modified" in a) for a in actions)

    if c2pa_present and c2pa_fields.get("verified") is True and is_generated:
        status = "VERIFIED_AI_GENERATED"
    elif c2pa_present and c2pa_fields.get("verified") is True and is_edited:
        status = "VERIFIED_AI_EDITED"
    elif c2pa_present:
        status = "PROVENANCE_PRESENT_BUT_UNVERIFIED"
    elif providers_meta:
        status = "POSSIBLE_AI_BUT_UNVERIFIED"
    else:
        status = "NO_PROVENANCE_FOUND"

    if status.startswith("VERIFIED_AI"):
        risk_level = "HIGH"
    elif status == "PROVENANCE_PRESENT_BUT_UNVERIFIED":
        risk_level = "MEDIUM"
    elif status == "POSSIBLE_AI_BUT_UNVERIFIED":
        risk_level = "MEDIUM"
    else:
        risk_level = "UNKNOWN"

    return {
        "status": status,
        "risk_level": risk_level,
        "c2pa_present": bool(c2pa_present),
        "c2pa_verified": c2pa_fields.get("verified"),
        "c2pa_tool_available": c2pa_available,
        "detected_providers": providers_meta,
        "detected_models_or_tools": tools_meta,
        "claim_generator": c2pa_fields.get("claim_generator"),
        "producer": c2pa_fields.get("producer"),
        "issuer": c2pa_fields.get("issuer"),
        "actions": actions,
        "ingredients": c2pa_fields.get("ingredients") or [],
        "metadata_ai_keywords": metadata_result.get("metadata_ai_keywords", []),
        "raw_c2pa": c2pa_json,
        "synthid": {
            "local_detection_supported": False,
            "possible_provider": "Google" if "Google" in providers_meta else None,
            "external_verification_required": True,
            "note": "SynthID is not a normal EXIF/XMP metadata field. Reliable detection requires official verification support.",
        },
        "external_verification": {
            "content_credentials_verify_recommended": True,
            "openai_verification_recommended": True,
            "gemini_synthid_check_recommended": True,
        },
        "limitations": [
            "No provenance metadata found does not prove the image is not AI-generated.",
            "C2PA metadata may be stripped by screenshots, format conversion, social platforms, or image recompression.",
            "Local FFT/DCT/LSB analysis cannot reliably determine whether a SynthID watermark is present.",
        ],
    }
