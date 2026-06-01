"""真阳测试：验证 LSB 头部 magic、metadata 用户载荷、tEXt flag 三个用例。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from image_forensics.analyzer import analyze_image  # noqa: E402


def make_lsb_gsy_png(out_path: Path) -> None:
    """构造 64x64 RGB PNG，把 b'GSY\\x00' 顺序写入像素 RGB LSB（big-endian bit order）。"""
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)

    payload = b"GSY\x00"
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8), bitorder="big")

    flat = arr.reshape(-1, 3)
    interleaved = flat.reshape(-1)
    n = bits.size
    interleaved[:n] = (interleaved[:n] & 0xFE) | bits
    flat = interleaved.reshape(-1, 3)
    arr = flat.reshape(64, 64, 3)

    Image.fromarray(arr, "RGB").save(out_path, format="PNG")


def make_text_flag_png(out_path: Path) -> None:
    """构造一张 PNG，在 tEXt 里写 flag{test_ctf}。"""
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, size=(48, 48, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Comment", "flag{test_ctf}")
    img.save(out_path, format="PNG", pnginfo=meta)


def run_case(name: str, img_path: Path, work_dir: Path) -> dict:
    out_dir = work_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    report = analyze_image(img_path, out_dir)
    return report


def assert_case1(report: dict) -> list[tuple[str, bool, str]]:
    ext = report.get("extraction", {})
    hits = ext.get("lsb_header_magic_hits", [])
    risk = ext.get("risk_level")
    has_gsy = any("GSY" in (h.get("magic") or "") or "GSY" in (h.get("head_text") or "") for h in hits)
    return [
        (
            "extraction.lsb_header_magic_hits 命中 GSY",
            has_gsy,
            f"hits={json.dumps(hits, ensure_ascii=False)[:300]}",
        ),
        (
            "extraction.risk_level == HIGH",
            risk == "HIGH",
            f"risk_level={risk}",
        ),
    ]


def assert_case2(report: dict) -> list[tuple[str, bool, str]]:
    meta = report.get("metadata", {})
    payloads = meta.get("user_payload_strings", []) or []
    has_gsy_payload = any("GSY" in (p.get("value") or "") for p in payloads)

    ev_items = report.get("evidence_items", []) or []
    first_ev_title = ev_items[0].get("title", "") if ev_items else ""
    first_has_gsy = "GSY" in first_ev_title

    overall = report.get("overall", {})
    summary = overall.get("summary", "")
    summary_has_gsy = "GSY" in summary

    return [
        (
            "metadata.user_payload_strings 包含 GSY",
            has_gsy_payload,
            f"payloads={json.dumps(payloads, ensure_ascii=False)[:400]}",
        ),
        (
            "evidence_items[0].title 含 GSY",
            first_has_gsy,
            f"first_title={first_ev_title!r}",
        ),
        (
            "overall.summary 含 GSY",
            summary_has_gsy,
            f"summary={summary[:300]!r}",
        ),
    ]


def assert_case3(report: dict) -> list[tuple[str, bool, str]]:
    ev_items = report.get("evidence_items", []) or []
    flag_in_any = False
    matched_titles: list[str] = []
    for ev in ev_items:
        blob = (ev.get("title", "") + " || " + ev.get("description", ""))
        if "flag{test_ctf}" in blob:
            flag_in_any = True
            matched_titles.append(ev.get("title", ""))

    meta = report.get("metadata", {})
    payloads = meta.get("user_payload_strings", []) or []
    payload_has_flag = any("flag{test_ctf}" in (p.get("value") or "") for p in payloads)

    return [
        (
            "metadata.user_payload_strings 含 flag{test_ctf}",
            payload_has_flag,
            f"payloads={json.dumps(payloads, ensure_ascii=False)[:400]}",
        ),
        (
            "evidence_items 中至少一条提及 flag{test_ctf}",
            flag_in_any,
            f"matched_titles={matched_titles}",
        ),
    ]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="forensics_tp_"))
    print(f"# 工作目录：{work}\n", flush=True)

    # case 1: 生成 LSB GSY 图
    img1 = work / "lsb_gsy.png"
    make_lsb_gsy_png(img1)

    # case 2: 用户提供的文件
    img2 = Path("/Users/guoshuyu/Downloads/ramen_gsy_metadata_lsb_synthid_test.png")

    # case 3: tEXt flag
    img3 = work / "text_flag.png"
    make_text_flag_png(img3)

    cases = [
        ("case1_lsb_gsy", img1, assert_case1),
        ("case2_ramen_gsy", img2, assert_case2),
        ("case3_text_flag", img3, assert_case3),
    ]

    overall_ok = True
    all_results: list[tuple[str, list[tuple[str, bool, str]]]] = []
    for name, path, assertor in cases:
        print(f"\n=== {name} :: {path} ===", flush=True)
        if not path.exists():
            print(f"  [SKIP] 文件不存在: {path}")
            all_results.append((name, [(f"file_exists({path})", False, "missing")]))
            overall_ok = False
            continue
        report = run_case(name, path, work)
        results = assertor(report)
        for title, ok, detail in results:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {title}")
            print(f"        {detail}")
            if not ok:
                overall_ok = False
        all_results.append((name, results))

    print("\n# ===== Markdown 汇总 =====")
    print("| 用例 | 断言 | 结果 |")
    print("| --- | --- | --- |")
    for name, results in all_results:
        for title, ok, _ in results:
            print(f"| {name} | {title} | {'PASS' if ok else 'FAIL'} |")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
