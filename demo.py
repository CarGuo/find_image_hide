"""One-click demo runner for Image Forensics Inspector.

Usage:
    python demo.py                       # offline: 合成样本 + 跑分析 + 打印 expected-vs-actual 表
    python demo.py --serve               # 同上，并启动 Flask Web UI
    python demo.py --download            # 额外联网下载真实公开图（picsum/wikimedia/NASA），扩大样本面
    python demo.py --input <path>        # 跑用户自己提供的一张图 / 一个目录
    python demo.py --port 5050           # --serve 时的端口

设计原则（与 README "能力诚实声明" 一致）:
  1. 默认 **离线**: 不连任何外网，避免 demo 因网络失败误判工具坏了
  2. 输出 **expected vs actual 对比表**: 每个样本写明"我预期这张图应该被打到什么档"
     与"实际打到什么档"，绿色=预期内、红色=未达预期。让用户一眼看清
     哪些场景是真能命中 / 哪些场景项目本身就是短板。
  3. **主动暴露短板**: 合成样本几乎必胜（因为是用工具自己造的）；
     若用户走 --input 塞一张真实剥光元数据的 AI 图进来，大概率 LOW，
     这是诚实暴露而不是粉饰。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 期望表: 与 tools/make_test_images.py 产出的文件名前缀一一对应
# value = (overall 期望档, 命中应来自哪些模块, 一句话场景说明)
# ---------------------------------------------------------------------------
EXPECTATIONS: dict[str, tuple[str, list[str], str]] = {
    "normal_png": (
        "LOW",
        [],
        "干净 PNG 基线 —— 全 LOW 才是正确表现",
    ),
    "normal_jpeg": (
        "LOW",
        [],
        "干净 JPEG 基线",
    ),
    "lsb_steg": (
        "HIGH",
        ["lsb_analysis", "steganalysis"],
        "全随机 LSB 隐写 —— 卡方/位面分析必中",
    ),
    "lsb_text_payload": (
        "HIGH",
        ["lsb_analysis", "extraction", "steganalysis"],
        "LSB 嵌入文本 payload",
    ),
    "ai_metadata": (
        "HIGH",
        ["metadata", "ai_provenance"],
        "EXIF 里写了 'Stable Diffusion' 等关键词 —— 元数据线路命中",
    ),
    "trailing_zip": (
        "HIGH",
        ["extraction"],
        "PNG IEND 后追加 zip —— extraction 直接抓尾部数据",
    ),
    "trailing_text": (
        "HIGH",
        ["extraction"],
        "JPEG EOI 后追加文本",
    ),
    "visible_watermark_getty": (
        "HIGH",
        ["visible_watermark"],
        "图上叠 GETTY IMAGES 文字 —— 需 tesseract 才能 OCR 命中",
    ),
    "stock_metadata_shutterstock": (
        "HIGH",
        ["metadata"],
        "EXIF 里 Shutterstock 关键词命中图库黑名单",
    ),
    "phash_laundered_match": (
        "HIGH",
        ["phash_match"],
        "洗图反查 —— 需 FORENSICS_PHASH_REFERENCE_DIR 才能命中",
    ),
}


# --- helpers ----------------------------------------------------------------

def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _run_module(mod_path: str) -> None:
    import runpy
    runpy.run_path(str(ROOT / mod_path), run_name="__main__")


def _color(text: str, code: str) -> str:
    # ANSI 色码；Windows 现代 Terminal / VSCode 终端原生支持
    return f"\033[{code}m{text}\033[0m"


def _ok(text: str) -> str:
    return _color(text, "32")  # green


def _bad(text: str) -> str:
    return _color(text, "31")  # red


def _warn(text: str) -> str:
    return _color(text, "33")  # yellow


def _dim(text: str) -> str:
    return _color(text, "90")


# --- demo phases ------------------------------------------------------------

def step_prepare_images(download: bool) -> Path:
    images_dir = ROOT / "tools" / "test_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if download:
        _hr("[1/4] (opt-in) Downloading real-world demo images")
        try:
            _run_module("tools/download_test_images.py")
        except SystemExit:
            pass
        except Exception as exc:
            print(_warn(f"  download skipped due to error: {exc}"))
    else:
        _hr("[1/4] Offline mode (skipping network download, use --download to enable)")

    _hr("[2/4] Generating synthetic + copyright-laundered samples")
    _run_module("tools/make_test_images.py")
    return images_dir


def step_run_analysis(images_dir: Path, label: str = "demo_run") -> tuple[Path, dict]:
    out_dir = ROOT / "analysis_output" / label
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_dir = ROOT / "tools" / "phash_reference"
    if ref_dir.exists():
        os.environ["FORENSICS_PHASH_REFERENCE_DIR"] = str(ref_dir)

    _hr("[3/4] Running batch forensic analysis")
    print(f"  input : {images_dir}")
    print(f"  output: {out_dir}")
    print(f"  phash_reference: {os.environ.get('FORENSICS_PHASH_REFERENCE_DIR', '(none)')}")
    print()

    from image_forensics.batch import analyze_directory

    def _cb(done: int, total: int, res: dict) -> None:
        rl = res.get("risk_level") or ("ERROR" if not res.get("ok") else "?")
        name = Path(res.get("image_path", "")).name
        print(f"  [{done:>2}/{total}] {name:<44s} -> {rl}")

    summary = analyze_directory(
        images_dir, out_dir, recursive=True, workers=1, progress_cb=_cb,
    )
    return out_dir, summary


# ---------------------------------------------------------------------------
# expected-vs-actual 对比表
# ---------------------------------------------------------------------------

_MODULE_FIELDS = (
    "metadata", "ai_provenance", "frequency_analysis", "dct_analysis",
    "lsb_analysis", "noise_analysis", "steganalysis", "extraction",
    "ela", "visible_watermark", "invisible_watermark", "phash_match",
    "copy_move", "ai_heuristics", "c2pa_check", "external_steganalysis",
)


def _module_risks(report: dict[str, Any]) -> dict[str, str]:
    out = {}
    for k in _MODULE_FIELDS:
        v = report.get(k) or {}
        rl = v.get("risk_level") or "-"
        out[k] = rl
    return out


def _find_report(out_dir: Path, tag: str) -> Path | None:
    for d in out_dir.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(tag):
            rp = d / "report.json"
            if rp.exists():
                return rp
    return None


def step_print_expectation_table(out_dir: Path) -> tuple[int, int]:
    """打印 expected-vs-actual 对比表，返回 (hit_count, total_count)"""
    _hr("[4/4] Expected vs Actual — 合成样本应命中的场景")

    hdr = f"  {'sample tag':<32} {'expected':<8} {'actual':<8} {'verdict':<8}  {'scenario'}"
    print(hdr)
    print(_dim("  " + "-" * 110))

    hit = 0
    total = 0
    for tag, (exp_overall, exp_modules, desc) in EXPECTATIONS.items():
        rp = _find_report(out_dir, tag)
        if rp is None:
            print(f"  {tag:<32} {exp_overall:<8} {'<n/a>':<8} {_warn('SKIP'):<16}  {desc}")
            continue
        total += 1
        report = json.loads(rp.read_text(encoding="utf-8"))
        actual = (report.get("overall") or {}).get("risk_level") or "-"

        # 判定: HIGH 期望命中 HIGH; LOW 期望维持 LOW
        if exp_overall == "HIGH":
            ok = actual == "HIGH"
        elif exp_overall == "LOW":
            ok = actual in ("LOW", "MEDIUM")  # LOW 基线可以容忍 MEDIUM
        else:
            ok = actual == exp_overall

        if ok:
            hit += 1
            verdict = _ok("PASS")
        else:
            verdict = _bad("FAIL")

        print(f"  {tag:<32} {exp_overall:<8} {actual:<8} {verdict:<16}  {desc}")

        # 子表: 该样本各模块给的 risk_level，方便定位是哪条线在工作
        risks = _module_risks(report)
        active = [(m, r) for m, r in risks.items() if r in ("HIGH", "MEDIUM")]
        if active:
            chips = "  ".join(
                f"{m}={_bad(r) if r == 'HIGH' else _warn(r)}"
                for m, r in active
            )
            print(_dim(f"    └─ modules firing: {chips}"))

        # 检查期望的模块是否确实在 active 里
        missing = [m for m in exp_modules if risks.get(m) not in ("HIGH", "MEDIUM")]
        if missing:
            print(_dim(f"    └─ {_warn('note:')} expected to fire but didn't: {', '.join(missing)} (可能因依赖未装：tesseract/外部隐写工具/pHash 参考库)"))

    return hit, total


def step_print_user_input_table(out_dir: Path, summary: dict) -> None:
    """对 --input 模式：逐张图打印 overall + 哪些模块在叫"""
    _hr("[4/4] User-supplied images — 每张图哪些模块给了信号")
    for r in summary.get("results", []):
        if not r.get("ok"):
            print(f"  {_bad('ERROR')} {Path(r.get('image_path', '?')).name}: {r.get('error')}")
            continue
        per = Path(r["output_dir"]) / "report.json"
        if not per.exists():
            continue
        report = json.loads(per.read_text(encoding="utf-8"))
        name = Path(r["image_path"]).name
        actual = (report.get("overall") or {}).get("risk_level") or "-"
        risks = _module_risks(report)
        active = [(m, rl) for m, rl in risks.items() if rl in ("HIGH", "MEDIUM")]

        verdict_color = _bad if actual == "HIGH" else (_warn if actual == "MEDIUM" else _ok)
        print(f"\n  {name}")
        print(f"    overall = {verdict_color(actual)}")
        if active:
            print(f"    firing  = " + ", ".join(
                f"{m}={_bad(rl) if rl == 'HIGH' else _warn(rl)}"
                for m, rl in active
            ))
        else:
            print(_dim("    (no module fired above LOW — 若这是已知 AI 图，则恰好命中了项目的 AI 检测短板)"))

    print()
    print(_warn(
        "  提醒: 若你塞进来一张真实的、被微信/小红书转过的 AI 图（元数据已剥），\n"
        "  本项目大概率给出 LOW —— 这是 README 中明确声明的短板，参见 README\n"
        "  '不推荐使用场景' 一节。要补这个洞需要接入预训练判别模型 (NPR / UniversalFakeDetect)。"
    ))


# --- optional Flask launcher ------------------------------------------------

def step_serve(port: int, open_browser: bool) -> None:
    _hr("[bonus] Launching Web UI")
    from webapp import app  # noqa: WPS433

    url = f"http://127.0.0.1:{port}/"
    print(f"  Web UI  : {url}")
    print(f"  Stop    : Ctrl+C")

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open_new_tab(url)).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


# --- entry ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="One-click demo for Image Forensics Inspector (默认离线，跑合成样本 + expected-vs-actual 对比表)",
    )
    p.add_argument("--download", action="store_true",
                   help="额外联网下载真实公开图（picsum/wikimedia/NASA），扩大样本面")
    p.add_argument("--input", type=str, default=None,
                   help="跑用户自己提供的一张图或一个目录，跳过合成样本流程")
    p.add_argument("--serve", action="store_true",
                   help="跑完后启动 Flask Web UI")
    p.add_argument("--no-browser", action="store_true",
                   help="--serve 时不自动开浏览器")
    p.add_argument("--port", type=int, default=5050, help="Web UI port (default: 5050)")
    args = p.parse_args(argv)

    t0 = time.time()

    if args.input:
        user_path = Path(args.input).resolve()
        if not user_path.exists():
            print(_bad(f"Input not found: {user_path}"))
            return 2
        _hr(f"User-input mode: {user_path}")
        if user_path.is_file():
            tmp_dir = ROOT / "analysis_output" / "_demo_user_input_src"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(user_path, tmp_dir / user_path.name)
            images_dir = tmp_dir
        else:
            images_dir = user_path
        out_dir, summary = step_run_analysis(images_dir, label="demo_user_input")
        step_print_user_input_table(out_dir, summary)
    else:
        images_dir = step_prepare_images(args.download)
        out_dir, summary = step_run_analysis(images_dir, label="demo_run")
        hit, total = step_print_expectation_table(out_dir)
        print()
        print(_ok(f"  合成样本命中率: {hit}/{total}") if total and hit == total
              else _warn(f"  合成样本命中率: {hit}/{total} (未达 100% 多半因 B 档依赖未装；详见 README)"))
        print(_dim(
            "  说明: 合成样本几乎必胜 (因为是用工具自己造的，循环论证)。"
            "\n        要真正验证项目能力，建议 `python demo.py --input <你自己的一张图>` 试试。"
        ))

    print(f"\n  Output: {out_dir}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")

    if args.serve:
        step_serve(args.port, open_browser=not args.no_browser)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
