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
    inv_wm = report.get("invisible_watermark", {})
    phash = report.get("phash_match", {})

    # Weights: industry-standard steganalysis (chi-square / SPA) and direct
    # extraction findings dominate, since they are *evidence* rather than
    # heuristics. FFT/DCT/LSB-entropy are weak supporting signals.
    weights = {
        "extraction": 0.28,
        "steganalysis": 0.18,
        "fft": 0.04,
        "dct": 0.04,
        "lsb": 0.04 if is_lossy else 0.08,
        "noise": 0.04,
        "ela": 0.04,
        "metadata": 0.05,
        "provenance": 0.10,
        "visible_watermark": 0.10,
        "invisible_watermark": 0.10,
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
        + weights["invisible_watermark"] * float(inv_wm.get("score", 0.0))
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
        inv_wm.get("risk_level", "LOW"),
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

    # 复合升级：AI 关键字 ≥ 2 条 + 元数据声明明确版权 ⇒ 强烈怀疑"AI 改图后伪造版权声明"
    ai_kw_count = len(meta.get("metadata_ai_keywords") or [])
    has_explicit_cr = bool((meta.get("copyright_summary") or {}).get("has_explicit_copyright"))
    forged_copyright_signal = ai_kw_count >= 2 and has_explicit_cr

    direct_high = (
        prov.get("status") in ("VERIFIED_AI_GENERATED", "VERIFIED_AI_EDITED")
        or ext.get("risk_level") == "HIGH"
        or steg.get("risk_level") == "HIGH"
        or full_lsb_replacement
        or (not is_lossy and lsb.get("risk_level") == "HIGH")
        or bool(meta.get("metadata_stock_hits"))
        or vis_wm.get("risk_level") == "HIGH"
        or inv_wm.get("risk_level") == "HIGH"
        or phash.get("risk_level") == "HIGH"
        or forged_copyright_signal
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
        kws = "、".join(sorted({h["keyword"] for h in vis_wm["hits"]}))
        summary_parts.append(f"图上 OCR 出版权 / 水印文字：{kws}。")
    if inv_wm.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[inv_wm.get("risk_level")]
        best = inv_wm.get("best_text") or ""
        match = inv_wm.get("best_known_match")
        if match:
            summary_parts.append(
                f"DWT-DCT 隐形水印解码命中已知字典「{match}」，文本="
                f"{best!r}（{lvl_cn}）。"
            )
        elif best:
            summary_parts.append(
                f"DWT-DCT 隐形水印解出可打印文本：{best!r}（{lvl_cn}）。"
            )
        else:
            summary_parts.append(f"隐形水印通道命中（{lvl_cn}）。")
    if phash.get("matches"):
        best = phash["matches"][0]
        summary_parts.append(
            f"与本地参考图 “{best['reference']}” 高度相似（pHash 汉明距离 = {best['distance']}），"
            f"很可能是同一张图被改裁 / 重存。"
        )
    if meta.get("metadata_stock_hits"):
        kws = "、".join(sorted({h["keyword"] for h in meta["metadata_stock_hits"]}))
        summary_parts.append(f"元数据中带有版权图库特征字段：{kws}。")
    if forged_copyright_signal:
        ai_kws = "、".join(meta.get("metadata_ai_keywords") or [])
        summary_parts.append(
            f"元数据同时出现 AI 生成器关键字（{ai_kws}）和明确的版权 / 作者声明 —— "
            "强烈怀疑这是 AI 改图后被加上伪造的版权字段。"
        )
    if full_lsb_replacement:
        summary_parts.append(
            "三个通道的 LSB 位平面统计上都是均匀白噪声，且卡方检验 P 接近 1 —— "
            "几乎可以确定 LSB 位被随机数据 / 满载隐写完全替换。"
        )
    if ext.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[ext.get("risk_level")]
        summary_parts.append(f"隐藏内容提取命中（{lvl_cn}），详见“隐藏内容提取”页签。")
    if steg.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[steg.get("risk_level")]
        summary_parts.append(f"隐写检测（卡方 / SPA）触发：{lvl_cn}。")
    prov_status = prov.get("status", "")
    if prov_status == "NO_PROVENANCE_FOUND":
        summary_parts.append("未发现 C2PA 等可信来源凭证。")
    elif prov_status == "POSSIBLE_AI_BUT_UNVERIFIED":
        providers = prov.get("detected_providers") or []
        if providers:
            summary_parts.append(
                f"元数据里出现疑似 AI 生成器关键字：{', '.join(providers)}（未经 C2PA 验证）。"
            )
        else:
            summary_parts.append("元数据里出现疑似 AI 关键字（未经 C2PA 验证）。")
    elif prov_status.startswith("VERIFIED"):
        verified_cn = {
            "VERIFIED_AI_GENERATED": "C2PA 已验证：AI 生成图",
            "VERIFIED_AI_EDITED": "C2PA 已验证：AI 编辑过",
        }.get(prov_status, f"C2PA 已验证：{prov_status}")
        summary_parts.append(f"{verified_cn}。")
    elif prov_status == "PROVENANCE_PRESENT_BUT_UNVERIFIED":
        summary_parts.append("发现 C2PA manifest，但当前环境没法验证签名。")
    if fft.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[fft.get("risk_level")]
        summary_parts.append(f"FFT 频谱出现异常对称峰（{lvl_cn}）。")
    if dct.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[dct.get("risk_level")]
        summary_parts.append(f"DCT 系数分布偏离自然图像（{lvl_cn}）。")
    if not is_lossy and lsb.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[lsb.get("risk_level")]
        summary_parts.append(f"LSB 位平面统计异常（{lvl_cn}）。")
    if noise.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[noise.get("risk_level")]
        summary_parts.append(f"局部噪声分布不一致，可能存在拼接 / 修图（{lvl_cn}）。")
    if ela.get("risk_level") in ("MEDIUM", "HIGH"):
        lvl_cn = {"MEDIUM": "中风险", "HIGH": "高风险"}[ela.get("risk_level")]
        summary_parts.append(f"ELA 误差水平异常，疑似存在重压缩 / 拼接区域（{lvl_cn}）。")
    if not summary_parts:
        summary_parts.append(
            "未发现明显的水印 / 隐写 / AI 痕迹，但请注意：检测不到不等于一定不存在。"
        )

    overall_cn = {"HIGH": "高风险", "MEDIUM": "中风险", "LOW": "低风险", "UNKNOWN": "未知"}.get(overall, overall)
    headline = f"综合判定：{overall_cn}（启发式置信度 {round(confidence, 2)}）。"

    return {
        "risk_level": overall,
        "confidence": round(confidence, 3),
        "summary": headline + " " + " ".join(summary_parts),
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
            "invisible_watermark": float(inv_wm.get("score", 0.0)),
            "phash_match": float(phash.get("phash_score", 0.0)),
        },
        "limitations": [
            "本工具不能证明一张图绝对没有水印 / 隐写。",
            "未知的私有水印方案可能完全检测不到。",
            "C2PA 元数据可能在截图、平台压缩、格式转换中丢失。",
            "SynthID 等私有水印需要官方接口才能可靠验证。",
            "卡方 / SPA 主要针对经典 LSB 替换，对 LSB-matching、F5、自适应隐写效果有限。",
            "所有评分都是启发式结果，不构成法律鉴定结论。",
        ],
    }
