"""External steganalysis tools wrapper (P1.2).

Design contract
---------------
This module *integrates* the de-facto industry-standard CLI steganalysis
tools via `subprocess`. Every tool is **soft-optional**:
  * Tool not on PATH       -> tool_status = "SKIPPED_NO_TOOL"
  * Tool present but errors -> tool_status = "ERROR" (with stderr captured)
  * Tool present, ran ok    -> tool_status = "OK" (with structured findings)

The module **never raises** to the caller; analyzer.py wraps it in a
try/except for belt-and-braces, but the design goal is that even with all
four tools missing the function returns a valid report dict.

We deliberately:
  - run every tool inside an isolated tempdir (binwalk / stegoveritas like to
    write carved artefacts into cwd) and clean up afterwards
  - cap each tool at 30 seconds (TOOL_TIMEOUT_SECONDS) so a hung tool can
    never freeze the pipeline
  - never feed user input to the shell (always argv list, shell=False)
  - require an opt-in env var FORENSICS_ENABLE_STEGSEEK=1 before invoking
    stegseek (which can run for *minutes* on a JPEG with the rockyou wordlist)

Risk policy
-----------
  * Direct evidence of an executable / archive embed via binwalk           => HIGH
  * Direct payload extracted by stegoveritas (Hidden Text / carved file)   => MEDIUM
  * Stegseek cracks a steghide passphrase                                  => HIGH
  * zsteg returns ASCII strings >= 6 chars on >= 2 distinct bit-orders     => MEDIUM
  * zsteg returns a magic-number hit (PNG/ZIP/PDF/...)                     => HIGH
  * Otherwise                                                              => LOW
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

TOOL_TIMEOUT_SECONDS = 30
ZSTEG_MIN_STRING_LEN = 6
EXECUTABLE_BINWALK_KEYWORDS = (
    "Zip archive",
    "RAR archive",
    "PDF document",
    "PE32",
    "ELF",
    "Mach-O",
    "Linux kernel",
    "gzip compressed",
    "7-zip archive",
    "JPEG image data",  # JPEG inside JPEG = polyglot trick
    "PNG image",         # PNG inside non-PNG = embed
    "GIF image",
    "Microsoft executable",
)


def _which(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    # Windows: shutil.which already handles .EXE/.CMD via PATHEXT, but some
    # Ruby gem wrappers (zsteg) install as `.bat`. Check explicit suffixes.
    if os.name == "nt":
        for suf in (".bat", ".cmd", ".exe"):
            p = shutil.which(name + suf)
            if p:
                return p
    return None


def _run(argv: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a CLI safely; return (returncode, stdout, stderr).

    Never raises -- on timeout / OSError / FileNotFoundError, returns
    (-1, "", explanation).
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            cwd=cwd,
            shell=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout > {TOOL_TIMEOUT_SECONDS}s"
    except FileNotFoundError as exc:
        return -1, "", f"not found: {exc}"
    except OSError as exc:
        return -1, "", f"oserror: {exc}"


# ---------- binwalk ---------------------------------------------------------
# We use the textual signature scan (-B). JSON mode (--log) varies across
# versions; the textual format has been stable since binwalk v2.1.
_BINWALK_LINE_RE = re.compile(r"^\s*(\d+)\s+0x[0-9A-Fa-f]+\s+(.+?)\s*$")


def _run_binwalk(input_path: Path) -> dict[str, Any]:
    exe = _which("binwalk")
    if not exe:
        return {"tool": "binwalk", "tool_status": "SKIPPED_NO_TOOL"}

    rc, out, err = _run([exe, "-B", str(input_path)])
    if rc < 0:
        return {"tool": "binwalk", "tool_status": "ERROR", "error": err}
    findings: list[dict[str, Any]] = []
    for line in out.splitlines():
        m = _BINWALK_LINE_RE.match(line)
        if not m:
            continue
        offset, desc = int(m.group(1)), m.group(2)
        # Skip the obvious "image header at offset 0" entries — every JPEG/PNG
        # will trip this, it's not evidence of an embed.
        if offset == 0:
            continue
        findings.append({"offset": offset, "description": desc})

    has_executable_embed = any(
        any(kw in f["description"] for kw in EXECUTABLE_BINWALK_KEYWORDS)
        for f in findings
    )
    return {
        "tool": "binwalk",
        "tool_status": "OK",
        "findings": findings,
        "finding_count": len(findings),
        "has_executable_embed": has_executable_embed,
    }


# ---------- zsteg ----------------------------------------------------------
# zsteg is a Ruby gem; it prints findings as `b<bits>,<channel>,<order>,<width>: <text>`.
# We look for ASCII-rich payloads and magic numbers.
_ZSTEG_LINE_RE = re.compile(r"^\s*(b\d+,[a-z]+,[a-z]+,[^\s:]+)\s*:\s*(.+?)\s*$")
_ZSTEG_MAGIC_HINTS = (
    "PNG image",
    "Zip archive",
    "PDF document",
    "GIF image",
    "JPEG image",
    "ELF",
    "PE32",
)


def _run_zsteg(input_path: Path) -> dict[str, Any]:
    exe = _which("zsteg")
    if not exe:
        return {"tool": "zsteg", "tool_status": "SKIPPED_NO_TOOL"}

    rc, out, err = _run([exe, "-a", str(input_path)])
    if rc < 0:
        return {"tool": "zsteg", "tool_status": "ERROR", "error": err}

    findings: list[dict[str, Any]] = []
    for line in out.splitlines():
        m = _ZSTEG_LINE_RE.match(line)
        if not m:
            continue
        plane, content = m.group(1), m.group(2)
        # zsteg appends `..` for ASCII strings, `<text>` for magic. Heuristic:
        is_magic = any(h in content for h in _ZSTEG_MAGIC_HINTS)
        # Strip surrounding quotes around extracted text payloads
        text_match = re.search(r'text:\s*"(.*?)"', content)
        text_payload = text_match.group(1) if text_match else None
        if text_payload and len(text_payload) >= ZSTEG_MIN_STRING_LEN:
            findings.append({
                "plane": plane,
                "kind": "text",
                "value": text_payload[:240],
            })
        elif is_magic:
            findings.append({"plane": plane, "kind": "magic", "value": content[:240]})

    distinct_planes = sorted({f["plane"] for f in findings if f["kind"] == "text"})
    has_magic = any(f["kind"] == "magic" for f in findings)
    return {
        "tool": "zsteg",
        "tool_status": "OK",
        "findings": findings,
        "finding_count": len(findings),
        "distinct_text_planes": distinct_planes,
        "has_magic_hit": has_magic,
    }


# ---------- stegoveritas ----------------------------------------------------
# stegoveritas writes carved bytes / decoded text into the output dir.
# We only need to know *whether anything came out* — list the output dir
# and inspect Results.json if present.
def _run_stegoveritas(input_path: Path) -> dict[str, Any]:
    exe = _which("stegoveritas")
    if not exe:
        return {"tool": "stegoveritas", "tool_status": "SKIPPED_NO_TOOL"}

    with tempfile.TemporaryDirectory(prefix="stegoveritas_") as tmpdir:
        rc, out, err = _run(
            [exe, str(input_path), "-out", tmpdir, "--quiet"],
            cwd=tmpdir,
        )
        if rc < 0:
            return {"tool": "stegoveritas", "tool_status": "ERROR", "error": err}

        carved: list[str] = []
        results_summary: dict[str, Any] = {}
        try:
            for entry in os.listdir(tmpdir):
                full = os.path.join(tmpdir, entry)
                if entry == "Results.json":
                    try:
                        results_summary = json.loads(Path(full).read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        results_summary = {"raw_unparseable": True}
                elif os.path.isfile(full) and os.path.getsize(full) > 0:
                    carved.append(entry)
        except OSError:
            pass

        return {
            "tool": "stegoveritas",
            "tool_status": "OK",
            "carved_artifact_count": len(carved),
            "carved_artifact_names": carved[:20],
            "results_summary_keys": sorted(list(results_summary.keys())) if isinstance(results_summary, dict) else [],
        }


# ---------- stegseek (opt-in only) -----------------------------------------
def _run_stegseek(input_path: Path) -> dict[str, Any]:
    if os.environ.get("FORENSICS_ENABLE_STEGSEEK") != "1":
        return {"tool": "stegseek", "tool_status": "SKIPPED_NOT_ENABLED"}
    exe = _which("stegseek")
    if not exe:
        return {"tool": "stegseek", "tool_status": "SKIPPED_NO_TOOL"}
    wordlist = os.environ.get("FORENSICS_STEGSEEK_WORDLIST")
    if not wordlist or not Path(wordlist).is_file():
        return {"tool": "stegseek", "tool_status": "SKIPPED_NO_WORDLIST"}

    with tempfile.TemporaryDirectory(prefix="stegseek_") as tmpdir:
        out_path = Path(tmpdir) / "stegseek_out"
        rc, out, err = _run(
            [exe, str(input_path), wordlist, str(out_path)],
            cwd=tmpdir,
        )
        if rc < 0:
            return {"tool": "stegseek", "tool_status": "ERROR", "error": err}
        cracked = "Found passphrase:" in out
        passphrase = None
        if cracked:
            m = re.search(r'Found passphrase:\s*"(.*?)"', out)
            if m:
                passphrase = m.group(1)
        return {
            "tool": "stegseek",
            "tool_status": "OK",
            "cracked": cracked,
            "passphrase": passphrase,
        }


# ---------- public entry ----------------------------------------------------
def analyze_external(input_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    if not input_path.is_file():
        return {
            "risk_level": "UNKNOWN",
            "external_steganalysis_score": 0.0,
            "tools": [],
            "evidence_items": [],
            "error": f"input not found: {input_path}",
        }

    binwalk = _run_binwalk(input_path)
    zsteg = _run_zsteg(input_path)
    stegoveritas = _run_stegoveritas(input_path)
    stegseek = _run_stegseek(input_path)
    tools = [binwalk, zsteg, stegoveritas, stegseek]

    available = [t for t in tools if t.get("tool_status") not in (
        "SKIPPED_NO_TOOL", "SKIPPED_NOT_ENABLED", "SKIPPED_NO_WORDLIST",
    )]

    # All tools missing? Then the whole module is UNKNOWN with score 0.
    if not available:
        return {
            "risk_level": "UNKNOWN",
            "external_steganalysis_score": 0.0,
            "tools": tools,
            "evidence_items": [],
            "note": (
                "外部隐写工具均未安装：binwalk / zsteg / stegoveritas / stegseek。"
                "可参考 docs/ROADMAP.md 安装其中任意一项以增强检测。"
            ),
        }

    # Aggregate
    score = 0.0
    risk = "LOW"
    evidence: list[dict[str, Any]] = []

    if binwalk.get("tool_status") == "OK":
        if binwalk.get("has_executable_embed"):
            score = max(score, 1.0)
            risk = "HIGH"
            descs = ", ".join(sorted({f["description"][:60] for f in binwalk.get("findings", [])}))[:300]
            evidence.append({
                "module": "external_steganalysis",
                "severity": "high",
                "title": "binwalk 检出可执行 / 归档嵌入",
                "description": f"binwalk 在文件中识别出非图像格式签名：{descs}",
                "confidence": 0.85,
            })
        elif binwalk.get("finding_count", 0) >= 3:
            score = max(score, 0.5)
            if risk == "LOW":
                risk = "MEDIUM"
            evidence.append({
                "module": "external_steganalysis",
                "severity": "medium",
                "title": f"binwalk 命中 {binwalk['finding_count']} 处签名（非可执行）",
                "description": "多处非图像签名命中，可能是误报也可能是隐写残骸；建议人工核查。",
                "confidence": 0.4,
            })

    if zsteg.get("tool_status") == "OK":
        if zsteg.get("has_magic_hit"):
            score = max(score, 1.0)
            risk = "HIGH"
            evidence.append({
                "module": "external_steganalysis",
                "severity": "high",
                "title": "zsteg 在 LSB 通道中识别出已知文件 magic",
                "description": "zsteg -a 在某个 LSB 位面 / 通道 / 字节顺序组合下读出 PNG/ZIP/PDF 等签名，强烈建议提取。",
                "confidence": 0.85,
            })
        elif len(zsteg.get("distinct_text_planes", [])) >= 2:
            score = max(score, 0.55)
            if risk == "LOW":
                risk = "MEDIUM"
            planes_str = ", ".join(zsteg["distinct_text_planes"][:6])
            evidence.append({
                "module": "external_steganalysis",
                "severity": "medium",
                "title": f"zsteg 在 ≥2 个 LSB 平面读出可打印文本（{planes_str}）",
                "description": "多平面共现可打印字符串，疑似 LSB 顺序写入；具体内容见 zsteg findings。",
                "confidence": 0.45,
            })

    if stegoveritas.get("tool_status") == "OK":
        if stegoveritas.get("carved_artifact_count", 0) >= 1:
            score = max(score, 0.55)
            if risk == "LOW":
                risk = "MEDIUM"
            evidence.append({
                "module": "external_steganalysis",
                "severity": "medium",
                "title": f"stegoveritas 提取出 {stegoveritas['carved_artifact_count']} 个产物",
                "description": (
                    "stegoveritas 在隔离目录中产出非空文件 / 文本，"
                    f"样例：{', '.join(stegoveritas.get('carved_artifact_names', [])[:5])}"
                ),
                "confidence": 0.5,
            })

    if stegseek.get("tool_status") == "OK" and stegseek.get("cracked"):
        score = max(score, 1.0)
        risk = "HIGH"
        evidence.append({
            "module": "external_steganalysis",
            "severity": "high",
            "title": "stegseek 破解出 steghide 密码",
            "description": (
                f"stegseek 用提供的字典解出 steghide 密码 "
                f"{stegseek.get('passphrase')!r}，可直接 steghide extract 取出嵌入文件。"
            ),
            "confidence": 0.95,
        })

    return {
        "risk_level": risk,
        "external_steganalysis_score": round(score, 3),
        "tools": tools,
        "evidence_items": evidence,
    }
