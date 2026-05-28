"""AI provenance analysis: C2PA + provider keyword matching + SynthID probe."""
from __future__ import annotations

import importlib
import importlib.util
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

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


def _module_available(name: str) -> bool:
    """检测某个 python 包是否能被 import（不真正加载，避免副作用）。"""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


# reverse-SynthID（aloshdenny/reverse-SynthID）公布的 1024×1024 SynthID v1
# 主要载频网格：FFT shift 后中心 (512,512) 偏移量。绿通道信号最强。
# 这些坐标是该项目用 100 张纯黑 + 100 张纯白 Gemini 输出回归得到的，
# 跨图相位一致性 >99%。我们仅取它的低频可解释 bin，作为启发式参考。
_SYNTHID_CARRIERS_1024 = [
    (9, 9),
    (5, 5),
    (10, 11),
    (13, 6),
    (7, 14),
    (12, 10),
]


def _synthid_freq_fingerprint(path: Path) -> dict[str, Any]:
    """SynthID 频域启发式指纹（参考 reverse-SynthID 的低频载频网格）。

    设计：
      1) 把图缩到 1024×1024（载频网格按这个尺寸校准），双线性即可；
      2) 取绿通道做 2D FFT，shift 中心；
      3) 对每个候选载频 bin (dy, dx)，算它的能量 vs 同半径 32 个邻域 bin 的中位数比值；
      4) 取所有载频 bin 的相位，计算 circular variance（越低越像同一个固定模板）。

    判定（启发式、保守）：
      - peak_ratio_p95 >= 4.0 且 phase_circ_var <= 0.35 -> high
      - peak_ratio_p95 >= 2.5 且 phase_circ_var <= 0.55 -> medium
      - 其它 -> low

    本探针 **绝不冒充权威 SynthID 检测**，仅在元数据没有命中时给出
    "频域可疑度"提示。压缩 / 重存 / 缩放 / VAE 重编码会让此特征失效。
    """
    fallback = {
        "available": False,
        "suspicion": "unknown",
        "reason": "",
        "peak_ratio_mean": None,
        "peak_ratio_p95": None,
        "phase_circular_variance": None,
        "carrier_grid_reference": "reverse-SynthID/V4 1024x1024 low-freq carriers",
        "carrier_count_used": 0,
    }
    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        fallback["reason"] = f"图像无法读取: {exc}"
        return fallback

    # 太小直接放弃，否则 1024 上采样后频谱信息不可信
    w, h = img.size
    if min(w, h) < 256:
        fallback["reason"] = f"图像分辨率过小（{w}x{h}）, 频域指纹不可靠"
        return fallback

    try:
        img1024 = img.resize((1024, 1024), Image.BILINEAR)
        arr = np.asarray(img1024, dtype=np.float32) / 255.0
        green = arr[..., 1]
        # 去 DC 漂移再做 FFT，避免极低频干扰
        green = green - green.mean()
        fft = np.fft.fftshift(np.fft.fft2(green))
        mag = np.abs(fft)

        cy, cx = 512, 512
        peak_ratios: list[float] = []
        phases: list[float] = []
        for dy, dx in _SYNTHID_CARRIERS_1024:
            y, x = cy + dy, cx + dx
            radius = int(round(math.hypot(dy, dx)))
            if radius < 2:
                continue
            # 同半径背景：取一个 1.5px 宽的圆环上的中位幅度
            yy, xx = np.indices(mag.shape)
            ring_mask = (
                (np.abs(np.hypot(yy - cy, xx - cx) - radius) < 1.5)
                & ~((yy == y) & (xx == x))
            )
            ring_vals = mag[ring_mask]
            if ring_vals.size < 10:
                continue
            background = float(np.median(ring_vals)) + 1e-6
            ratio = float(mag[y, x] / background)
            peak_ratios.append(ratio)
            phases.append(float(np.angle(fft[y, x])))

        if len(peak_ratios) < 3:
            fallback["reason"] = "未能在频谱中取到足够的候选载频"
            return fallback

        peak_arr = np.array(peak_ratios, dtype=np.float64)
        phase_arr = np.array(phases, dtype=np.float64)
        # 圆方差：1 - |mean(e^{i*phase})|，越接近 0 表示相位越锁
        unit = np.exp(1j * phase_arr)
        circ_var = float(1.0 - np.abs(unit.mean()))

        ratio_p95 = float(np.percentile(peak_arr, 95))
        ratio_mean = float(peak_arr.mean())

        if ratio_p95 >= 4.0 and circ_var <= 0.35:
            suspicion = "high"
            reason = "多个低频载频 bin 显著高于背景且相位高度一致，符合固定模板水印的特征"
        elif ratio_p95 >= 2.5 and circ_var <= 0.55:
            suspicion = "medium"
            reason = "部分低频 bin 比背景高，且相位较一致，存在频域水印的可能"
        else:
            suspicion = "low"
            reason = "频域中没有看到明显的固定模板水印特征"

        return {
            "available": True,
            "suspicion": suspicion,
            "reason": reason,
            "peak_ratio_mean": ratio_mean,
            "peak_ratio_p95": ratio_p95,
            "phase_circular_variance": circ_var,
            "carrier_grid_reference": "reverse-SynthID/V4 1024x1024 low-freq carriers",
            "carrier_count_used": int(len(peak_ratios)),
        }
    except Exception as exc:
        fallback["reason"] = f"频域指纹计算失败: {exc}"
        return fallback


def _synthid_probe(path: Path, metadata_blob: str) -> dict[str, Any]:
    """SynthID 现状探测（含启发式频域指纹）：

    - 文本 SynthID：Google 在 2024-10 开源了 ``synthid-text``（github: google-deepmind/synthid-text）。
      它只能在拥有 LLM 原始 logits 的场景下嵌入 / 检测水印，对最终的 PNG / JPG 图像 **无作用**。
    - 图像 SynthID：Google 至今 **未公开发布权重或离线检测器**，仅在 Vertex AI / Gemini API
      内部提供 verify。任何"开源 SynthID 图像检测"都不是官方实现。
    - 社区项目 reverse-SynthID（aloshdenny/reverse-SynthID）通过 100 张纯黑/白 Gemini
      输出回归出了 1024×1024 下的固定低频载频网格 + 跨图相位一致性，
      其检测自报准确率 ~90%，对压缩/缩放/VAE 会失效。
      本工具 **不下载它的 220MB codebook**，只复用它公开的载频坐标做"频域指纹启发式探测"，
      并在 UI 中明确标记是参考性提示，权威验证仍需 Google 官方接口。
    - 想要更精确的检测，可在「SynthID 增强」面板中一键安装它的官方 src 包 + codebook（方案 B）。
    """
    text_pkg = _module_available("synthid_text")
    reverse_pkg = _module_available("synthid_bypass_v4") or _module_available(
        "robust_extractor"
    )
    blob_lower = (metadata_blob or "").lower()
    metadata_mentions_synthid = "synthid" in blob_lower
    fingerprint = _synthid_freq_fingerprint(Path(path))
    return {
        "image_watermark_open_source": False,
        "image_watermark_official_endpoint": "Google Cloud Vertex AI / Gemini API",
        "text_watermark_open_source": True,
        "text_watermark_package": "synthid-text (github.com/google-deepmind/synthid-text)",
        "text_watermark_package_installed": text_pkg,
        "reverse_synthid_package_installed": reverse_pkg,
        "metadata_mentions_synthid": metadata_mentions_synthid,
        "local_image_detection_supported": False,
        "frequency_probe": fingerprint,
        "note": (
            "Google DeepMind 已开源 synthid-text（仅文本 LLM 水印，2024-10）；"
            "图像版 SynthID 至今没有官方开源权重。本工具内置一个参考自 "
            "aloshdenny/reverse-SynthID 的纯 numpy 频域启发式指纹，"
            "可在元数据被剥离时给出弱可疑度提示；权威验证仍需 Google 官方接口或 Gemini App。"
        ),
    }



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
        "synthid": _synthid_probe(Path(path), blob),
        "external_verification": {
            "content_credentials_verify_recommended": True,
            "openai_verification_recommended": True,
            "gemini_synthid_check_recommended": True,
        },
        "limitations": [
            "本地没有找到来源凭证，并不能反过来证明图像不是 AI 生成的。",
            "C2PA 元数据可能在截图、平台压缩、格式转换或重新编码中被剥离。",
            "图像版 SynthID 至今没有官方开源权重，本地频域分析最多给出弱启发提示，权威验证仍需走 Google 官方渠道。",
            "SynthID 的开源版本（synthid-text）仅适用于带 logits 的 LLM 文本，对成品 PNG / JPG 无效。",
        ],
    }
