"""P2.4: Forensic-grade PDF report renderer (soft dependency on reportlab).

Design goals
------------
* Soft dependency: ``import reportlab`` is probed at import time. If missing,
  ``render_pdf`` raises a :class:`PdfBackendUnavailableError` carrying a
  ``pip install reportlab`` hint. Webapp / CLI callers MUST catch and surface
  this to the user; the rest of the pipeline keeps working.
* Reproducibility: the rendered PDF is content-addressable. ``render_pdf``
  returns a manifest dict containing
  ``{ pdf_path, pdf_sha256, source_report_sha256, generated_at }``.
  PDF metadata (CreationDate / ModDate / producer) is stamped from
  ``report["created_at"]`` so the same input report always yields the same
  byte-identical PDF (``reportlab`` honours the ``invariant=1`` canvas flag).
* Privacy: the user's absolute file path is **not** embedded in the PDF body;
  only basename + sha256 of the original image bytes are kept.
* Cross-platform: pure Python wheel, no system fonts required. CJK rendering
  uses ``HeiseiMin-W3`` / ``STSong-Light`` — both ship inside reportlab as
  CID fonts and need no external TTF.

API
---
* :func:`pdf_status` → ``{available, version, error, package}`` (mirrors the
  P2.3 / P1.5 / P1.2 ``*_status()`` convention).
* :func:`render_pdf(report_path, output_pdf, viz_dir=None, image_path=None)`
  → manifest dict (see above). Internally tolerant of missing visualizations.
* :class:`PdfBackendUnavailableError` — raised when reportlab is not installed.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPORTLAB_AVAILABLE = False
_REPORTLAB_VERSION: str | None = None
_REPORTLAB_ERROR: str | None = None
try:
    import reportlab as _rl  # noqa: F401
    from reportlab.lib import colors  # noqa: F401
    from reportlab.lib.pagesizes import A4  # noqa: F401
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: F401
    from reportlab.lib.units import mm  # noqa: F401
    from reportlab.pdfbase import pdfmetrics  # noqa: F401
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: F401
    from reportlab.platypus import (  # noqa: F401
        Image as RLImage,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _REPORTLAB_AVAILABLE = True
    _REPORTLAB_VERSION = getattr(_rl, "Version", "unknown")
except Exception as _exc:
    _REPORTLAB_ERROR = f"{type(_exc).__name__}: {_exc}"


class PdfBackendUnavailableError(RuntimeError):
    """Raised when ``render_pdf`` is called without reportlab installed."""

    def __init__(self, hint_pkg: str = "reportlab") -> None:
        super().__init__(
            f"PDF backend unavailable. Install with: pip install {hint_pkg}"
        )
        self.hint_pkg = hint_pkg


def pdf_status() -> dict[str, Any]:
    """Return decoder-style status for ``/api/diagnostics`` and unit tests."""
    return {
        "available": _REPORTLAB_AVAILABLE,
        "version": _REPORTLAB_VERSION,
        "error": _REPORTLAB_ERROR,
        "package": "reportlab",
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


_RISK_COLOR = {
    "HIGH": "#c0392b",
    "MEDIUM": "#e67e22",
    "LOW": "#27ae60",
    "UNKNOWN": "#7f8c8d",
}


_MODULE_LABEL = {
    "ai_provenance": "AI 来源 / C2PA",
    "frequency_analysis": "频域 (FFT)",
    "dct_analysis": "DCT 频域",
    "lsb_analysis": "LSB 位平面",
    "noise_analysis": "噪声残差",
    "steganalysis": "隐写检测 (内置)",
    "extraction": "隐藏内容提取",
    "ela": "ELA 误差",
    "visible_watermark": "可见水印 OCR",
    "invisible_watermark": "不可见水印",
    "phash_match": "pHash 图库比对",
    "copy_move": "复制-粘贴篡改",
    "ai_heuristics": "AI 启发式",
    "c2pa_check": "C2PA 签名校验",
    "external_steganalysis": "外部隐写工具",
}


def _register_cjk_font() -> str:
    """Register a CID CJK font that ships inside reportlab. Returns the font
    name that should be used in styles. Falls back to Helvetica if the CID
    Asian fonts module is not present (very old reportlab)."""
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
            return "HeiseiMin-W3"
        except Exception:
            return "Helvetica"


def _safe(report: dict[str, Any], *keys: str, default: Any = "—") -> Any:
    cur: Any = report
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    if cur is None or cur == "":
        return default
    return cur


def _build_overview_table(report: dict[str, Any], styles: dict[str, Any]) -> "Table":
    overall = report.get("overall") or {}
    risk = (overall.get("risk_level") or "UNKNOWN").upper()
    color = colors.HexColor(_RISK_COLOR.get(risk, _RISK_COLOR["UNKNOWN"]))
    inp = report.get("input") or {}
    rows = [
        ["综合风险", risk],
        ["综合得分", f"{overall.get('overall_score', 0.0):.3f}"],
        ["文件名", inp.get("file_name") or "—"],
        ["格式", inp.get("format") or "—"],
        ["尺寸", f"{inp.get('width','—')} x {inp.get('height','—')}"],
        ["原图 SHA-256", (inp.get("sha256") or "—")[:16] + ("…" if inp.get("sha256") else "")],
        ["分析 ID", report.get("analysis_id") or "—"],
        ["生成时间 (UTC)", report.get("created_at") or "—"],
        ["报告 schema", report.get("schema_version") or "—"],
        ["错误数", str(len(report.get("errors") or []))],
    ]
    table = Table(rows, colWidths=[40 * mm, 130 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), styles["body_font"], 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f6fa")),
                ("TEXTCOLOR", (1, 0), (1, 0), color),
                ("FONT", (1, 0), (1, 0), styles["body_font"], 11),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bdc3c7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_module_table(report: dict[str, Any], styles: dict[str, Any]) -> "Table":
    rows = [["模块", "风险", "得分 / 状态"]]
    score_keys = {
        "ai_provenance": "ai_provenance_score",
        "frequency_analysis": "spectrum_anomaly_score",
        "dct_analysis": "dct_anomaly_score",
        "lsb_analysis": "lsb_anomaly_score",
        "noise_analysis": "noise_inconsistency_score",
        "steganalysis": "steganalysis_score",
        "extraction": "extraction_score",
        "ela": "ela_inconsistency_score",
        "visible_watermark": "ocr_score",
        "invisible_watermark": "score",
        "phash_match": "phash_score",
        "copy_move": "copy_move_score",
        "ai_heuristics": "ai_heuristics_score",
        "c2pa_check": "c2pa_score",
        "external_steganalysis": "external_steganalysis_score",
    }
    for key, label in _MODULE_LABEL.items():
        block = report.get(key) or {}
        risk = (block.get("risk_level") or "UNKNOWN").upper()
        sk = score_keys.get(key)
        score_val = block.get(sk) if sk else None
        if isinstance(score_val, (int, float)):
            score_text = f"{score_val:.3f}"
        else:
            score_text = block.get("status") or "—"
        rows.append([label, risk, str(score_text)])
    tbl = Table(rows, colWidths=[60 * mm, 30 * mm, 80 * mm])
    style_cmds = [
        ("FONT", (0, 0), (-1, -1), styles["body_font"], 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), styles["body_font"], 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bdc3c7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for r_idx, row in enumerate(rows[1:], start=1):
        risk = row[1]
        c = colors.HexColor(_RISK_COLOR.get(risk, _RISK_COLOR["UNKNOWN"]))
        style_cmds.append(("TEXTCOLOR", (1, r_idx), (1, r_idx), c))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _build_evidence_paragraphs(
    report: dict[str, Any], styles: dict[str, Any]
) -> list[Any]:
    flow: list[Any] = []
    items = report.get("evidence_items") or []
    if not items:
        flow.append(Paragraph("（本次分析未产生证据条目）", styles["body"]))
        return flow
    for ev in items[:30]:
        sev = (ev.get("severity") or "info").lower()
        sev_label = {
            "high": "[HIGH]",
            "medium": "[MED]",
            "warning": "[WARN]",
            "info": "[INFO]",
            "low": "[LOW]",
        }.get(sev, f"[{sev.upper()}]")
        title = (ev.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
        desc = (ev.get("description") or "").replace("<", "&lt;").replace(">", "&gt;")
        module = ev.get("module") or "?"
        flow.append(
            Paragraph(
                f"<b>{sev_label} [{module}]</b> {title}",
                styles["evidence_title"],
            )
        )
        if desc:
            flow.append(Paragraph(desc, styles["evidence_body"]))
        flow.append(Spacer(1, 3))
    if len(items) > 30:
        flow.append(
            Paragraph(
                f"... 另有 {len(items) - 30} 条证据未在 PDF 中展示，请参阅 report.json",
                styles["body"],
            )
        )
    return flow


_PREFERRED_VIZ = (
    "ela.png",
    "spectrum.png",
    "dct_histogram.png",
    "lsb_b_p0.png",
    "residual.png",
    "laplacian.png",
)


def _build_visualization_pages(viz_dir: Path | None, styles: dict[str, Any]) -> list[Any]:
    flow: list[Any] = []
    if viz_dir is None or not viz_dir.is_dir():
        return flow
    available = []
    for name in _PREFERRED_VIZ:
        p = viz_dir / name
        if p.is_file():
            available.append((name, p))
    if not available:
        return flow
    flow.append(PageBreak())
    flow.append(Paragraph("可视化图证 (Visualizations)", styles["h2"]))
    flow.append(
        Paragraph(
            "下列图证由各分析模块在内存中渲染并落盘，不含任何用户路径。",
            styles["body"],
        )
    )
    flow.append(Spacer(1, 6))
    for label, path in available:
        flow.append(Paragraph(label, styles["caption"]))
        try:
            img = RLImage(str(path), width=150 * mm, height=100 * mm, kind="proportional")
            flow.append(img)
        except Exception as exc:
            flow.append(Paragraph(f"[图证渲染失败: {type(exc).__name__}: {exc}]", styles["body"]))
        flow.append(Spacer(1, 6))
    return flow


def render_pdf(
    report_path: str | Path,
    output_pdf: str | Path,
    viz_dir: str | Path | None = None,
    image_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render ``report.json`` to a forensic-grade PDF.

    Returns a manifest dict with content-addressable identifiers so callers
    can attach signatures or chain-of-custody records later.
    """
    if not _REPORTLAB_AVAILABLE:
        raise PdfBackendUnavailableError("reportlab")

    report_path = Path(report_path)
    output_pdf = Path(output_pdf)
    viz_dir_p = Path(viz_dir) if viz_dir else None

    raw = report_path.read_bytes()
    source_sha = _sha256_bytes(raw)
    report = json.loads(raw.decode("utf-8"))

    if image_path is not None:
        try:
            img_p = Path(image_path)
            if img_p.is_file():
                report.setdefault("input", {}).setdefault(
                    "sha256", _sha256_file(img_p)
                )
        except Exception:
            pass

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    body_font = _register_cjk_font()
    base_styles = getSampleStyleSheet()
    styles = {
        "body_font": body_font,
        "h1": ParagraphStyle(
            "H1",
            parent=base_styles["Title"],
            fontName=body_font,
            fontSize=18,
            leading=22,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base_styles["Heading2"],
            fontName=body_font,
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base_styles["BodyText"],
            fontName=body_font,
            fontSize=9,
            leading=12,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base_styles["BodyText"],
            fontName=body_font,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#34495e"),
        ),
        "evidence_title": ParagraphStyle(
            "EvT",
            parent=base_styles["BodyText"],
            fontName=body_font,
            fontSize=9,
            leading=12,
            spaceAfter=1,
        ),
        "evidence_body": ParagraphStyle(
            "EvB",
            parent=base_styles["BodyText"],
            fontName=body_font,
            fontSize=8.5,
            leading=11,
            leftIndent=10,
            textColor=colors.HexColor("#2c3e50"),
        ),
    }

    invariant_dt = datetime.now(timezone.utc)
    try:
        if report.get("created_at"):
            invariant_dt = datetime.fromisoformat(
                str(report["created_at"]).replace("Z", "+00:00")
            )
    except Exception:
        pass

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Image Forensics Report",
        author=report.get("tool_name") or "Image Forensics Inspector",
        subject=f"analysis_id={report.get('analysis_id','?')}",
        creator=f"image_forensics.pdf_report (reportlab {_REPORTLAB_VERSION})",
        producer=f"image_forensics.pdf_report (reportlab {_REPORTLAB_VERSION})",
        invariant=1,
    )

    flow: list[Any] = []
    flow.append(Paragraph("图像取证分析报告", styles["h1"]))
    flow.append(
        Paragraph(
            f"Tool: {report.get('tool_name','Image Forensics Inspector')} · "
            f"schema: {report.get('schema_version','?')} · "
            f"analysis_id: {report.get('analysis_id','?')}",
            styles["caption"],
        )
    )
    flow.append(Spacer(1, 8))
    flow.append(Paragraph("一、综合概览", styles["h2"]))
    flow.append(_build_overview_table(report, styles))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph("二、模块分项", styles["h2"]))
    flow.append(_build_module_table(report, styles))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph("三、证据条目", styles["h2"]))
    flow.extend(_build_evidence_paragraphs(report, styles))
    flow.extend(_build_visualization_pages(viz_dir_p, styles))
    flow.append(PageBreak())
    flow.append(Paragraph("四、可重现性凭据", styles["h2"]))
    chain_table = Table(
        [
            ["report.json SHA-256", source_sha],
            ["生成器", f"image_forensics.pdf_report (reportlab {_REPORTLAB_VERSION})"],
            ["生成时间 (UTC)", invariant_dt.isoformat()],
            ["可重现性", "本 PDF 由 reportlab invariant=1 生成；同一份 report.json + viz_dir 渲染出的 PDF 字节级一致"],
            ["数字签名", "（占位：建议用 GnuPG / Adobe Sign 对最终 PDF 做外部签名）"],
        ],
        colWidths=[40 * mm, 130 * mm],
    )
    chain_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), body_font, 8.5),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ecf0f1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bdc3c7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flow.append(chain_table)

    doc.build(flow)
    pdf_bytes = buf.getvalue()
    output_pdf.write_bytes(pdf_bytes)

    return {
        "pdf_path": str(output_pdf),
        "pdf_sha256": _sha256_bytes(pdf_bytes),
        "pdf_size_bytes": len(pdf_bytes),
        "source_report_sha256": source_sha,
        "generated_at": invariant_dt.isoformat(),
        "backend": "reportlab",
        "backend_version": _REPORTLAB_VERSION,
    }


__all__ = [
    "PdfBackendUnavailableError",
    "pdf_status",
    "render_pdf",
]
