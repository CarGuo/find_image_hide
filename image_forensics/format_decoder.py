"""Multi-format decoder: HEIC / AVIF / WebP / RAW soft-dependency wrapper.

This module is the single source of truth for "which extra formats can the
inspector currently understand". It probes three optional decoders at import
time *without* raising, registers the HEIC opener into Pillow when available,
and exposes:

* ``EXTRA_EXTS``       — filename extensions that *might* be readable thanks
                         to the optional decoders (HEIC / AVIF / RAW family).
                         Always a stable set, regardless of which decoders
                         actually succeeded — the *fallback* in ``open_any``
                         is what handles the missing-tool case.
* ``decoder_status()`` — diagnostic dict telling the caller exactly which
                         optional decoder succeeded / failed and why. Useful
                         for unit tests, ``/api/diagnostics`` endpoints, or
                         operator hints in the UI.
* ``open_any(path)``   — Pillow-style ``Image.Image`` opener that transparently
                         falls back to ``rawpy`` for camera RAW files, and
                         leans on ``pillow_heif`` for HEIC/HEIF.  AVIF is
                         handled natively because Pillow 11.3+ ships with
                         libavif support on CPython.

Design choices (see docs/ROADMAP.md §四 P2.3 decision log for rationale):

1. **Soft deps, never raise on import** — same paradigm as ``c2pa_check`` and
   ``steganalysis_external``: the analyzer pipeline must keep working even
   when neither pillow-heif nor rawpy is installed. Missing decoders are
   reported via ``decoder_status()`` so the UI can hint at install commands.

2. **Lazy probe at import** — we attempt to import each optional package once
   and cache the result; subsequent ``open_any`` calls do not re-import.
   ``pillow_heif.register_heif_opener()`` is idempotent so calling it once
   here is enough for every ``Image.open()`` in the codebase to handle HEIC.

3. **RAW path is special** — rawpy doesn't return a ``PIL.Image`` directly;
   we postprocess to RGB ndarray and wrap it. The resulting image's
   ``.format`` is set to ``"RAW"`` so downstream lossy/lossless detection
   keeps working (RAW is, of course, treated as lossy by default since
   demosaicing introduces irreversible interpolation).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, features

# ---------------------------------------------------------------------------
# Static extension set: declared up front so callers know what *can* possibly
# work even before probing. Whether each format actually decodes depends on
# the decoder probe results below.
# ---------------------------------------------------------------------------
HEIF_EXTS = {".heic", ".heif"}
AVIF_EXTS = {".avif"}
RAW_EXTS = {
    ".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf",
    ".orf", ".rw2", ".pef", ".srw", ".kdc", ".dcr",
}
EXTRA_EXTS = HEIF_EXTS | AVIF_EXTS | RAW_EXTS


# ---------------------------------------------------------------------------
# Probe optional dependencies once at import time. ALL of these are wrapped
# so that an ``ImportError`` / DLL-load failure from a partial install does
# NOT take down the analyzer — we just disable that branch and remember why.
# ---------------------------------------------------------------------------
_HEIF_AVAILABLE = False
_HEIF_VERSION: str | None = None
_HEIF_ERROR: str | None = None
try:  # pragma: no cover - exercised by import-time probe
    import pillow_heif as _ph  # type: ignore

    _ph.register_heif_opener()
    _HEIF_AVAILABLE = True
    _HEIF_VERSION = getattr(_ph, "__version__", "unknown")
except Exception as _exc:  # noqa: BLE001 - we *want* to swallow everything
    _HEIF_ERROR = f"{type(_exc).__name__}: {_exc}"

# AVIF is native in Pillow >= 11.3 when libavif is present. ``features.check``
# returns False on older Pillow; we still probe ``pillow_avif`` as a back-up
# so users on Pillow < 11.3 can opt in via the plugin package.
_AVIF_AVAILABLE = False
_AVIF_BACKEND: str | None = None
_AVIF_ERROR: str | None = None
try:
    if features.check("avif"):
        _AVIF_AVAILABLE = True
        _AVIF_BACKEND = "pillow-native"
except Exception as _exc:  # noqa: BLE001
    _AVIF_ERROR = f"features.check failed: {type(_exc).__name__}: {_exc}"

if not _AVIF_AVAILABLE:
    try:  # pragma: no cover - only fires on older Pillow with plugin installed
        import pillow_avif  # type: ignore  # noqa: F401 - import-for-side-effect

        _AVIF_AVAILABLE = True
        _AVIF_BACKEND = "pillow-avif-plugin"
    except Exception as _exc:  # noqa: BLE001
        if _AVIF_ERROR is None:
            _AVIF_ERROR = f"{type(_exc).__name__}: {_exc}"

_RAWPY_AVAILABLE = False
_RAWPY_VERSION: str | None = None
_RAWPY_ERROR: str | None = None
try:
    import rawpy as _rawpy  # type: ignore

    _RAWPY_AVAILABLE = True
    _RAWPY_VERSION = getattr(_rawpy, "__version__", "unknown")
except Exception as _exc:  # noqa: BLE001
    _RAWPY_ERROR = f"{type(_exc).__name__}: {_exc}"


def decoder_status() -> dict[str, Any]:
    """Return a frozen snapshot of optional-decoder availability.

    Stable shape so callers (tests, ``/api/diagnostics`` etc.) can pattern-
    match without trying/excepting around imports themselves.
    """
    return {
        "heif": {
            "available": _HEIF_AVAILABLE,
            "version": _HEIF_VERSION,
            "error": _HEIF_ERROR,
            "package": "pillow-heif",
            "extensions": sorted(HEIF_EXTS),
        },
        "avif": {
            "available": _AVIF_AVAILABLE,
            "backend": _AVIF_BACKEND,
            "error": _AVIF_ERROR,
            "package": "Pillow>=11.3 (native) or pillow-avif-plugin",
            "extensions": sorted(AVIF_EXTS),
        },
        "raw": {
            "available": _RAWPY_AVAILABLE,
            "version": _RAWPY_VERSION,
            "error": _RAWPY_ERROR,
            "package": "rawpy",
            "extensions": sorted(RAW_EXTS),
        },
    }


def is_extra_format(path: str | Path) -> bool:
    """True if ``path``'s extension belongs to the P2.3 extended set.

    Extension-based, so it works for paths that don't exist yet (e.g.
    upload-routing decisions) and for files we can't yet decode (so the
    caller knows whether to try ``open_any`` vs hard-fail).
    """
    return Path(path).suffix.lower() in EXTRA_EXTS


def is_raw(path: str | Path) -> bool:
    """True if ``path``'s extension is in the camera-RAW family."""
    return Path(path).suffix.lower() in RAW_EXTS


class UnsupportedFormatError(RuntimeError):
    """Raised by ``open_any`` only when no decoder pathway exists at all.

    Critically, callers downstream of ``open_any`` should still ``try/except``
    to mirror the rest of the pipeline's never-raise philosophy.  This
    exception type exists purely to let unit tests assert on the failure
    mode without string-matching on a generic ``RuntimeError``.
    """


def open_any(path: str | Path) -> Image.Image:
    """Open *any* supported image format and return a PIL ``Image`` instance.

    Routing logic:

    * ``.heic / .heif`` → relies on ``pillow_heif.register_heif_opener()``
      having patched Pillow at import time.  We still call ``Image.open``
      so callers get the same object type; if pillow-heif is missing we
      raise ``UnsupportedFormatError`` with an actionable hint.

    * ``.avif`` → goes through plain ``Image.open`` because Pillow 11.3+
      handles AVIF natively (or pillow-avif-plugin patches it in).  When
      neither backend is available we raise ``UnsupportedFormatError``.

    * RAW (``.dng / .nef / .cr2 / ...``) → uses ``rawpy.imread()`` and
      ``postprocess()`` to demosaic to an 8-bit RGB ndarray, then wraps
      with ``Image.fromarray``.  The returned image has ``.format = "RAW"``
      so the rest of the pipeline correctly classifies it as lossy.

    * Anything else → falls through to ``Image.open(path)`` — i.e. the
      historical behaviour, byte-for-byte.

    The image's ``load()`` method is *not* called here — callers that need
    eager decoding should ``img.load()`` themselves.  This matches the
    contract of ``PIL.Image.open``.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in HEIF_EXTS:
        if not _HEIF_AVAILABLE:
            raise UnsupportedFormatError(
                f"HEIC/HEIF decoding requires the optional 'pillow-heif' package "
                f"(pip install pillow-heif). Original probe error: {_HEIF_ERROR}"
            )
        return Image.open(p)

    if suffix in AVIF_EXTS:
        if not _AVIF_AVAILABLE:
            raise UnsupportedFormatError(
                f"AVIF decoding requires Pillow>=11.3 with libavif, or the "
                f"'pillow-avif-plugin' package. Probe error: {_AVIF_ERROR}"
            )
        return Image.open(p)

    if suffix in RAW_EXTS:
        if not _RAWPY_AVAILABLE:
            raise UnsupportedFormatError(
                f"Camera RAW ({suffix}) decoding requires the optional 'rawpy' "
                f"package (pip install rawpy). Probe error: {_RAWPY_ERROR}"
            )
        with _rawpy.imread(str(p)) as raw:  # type: ignore[name-defined]
            rgb = raw.postprocess(
                output_bps=8,
                no_auto_bright=False,
                use_camera_wb=True,
            )
        img = Image.fromarray(rgb, mode="RGB")
        img.format = "RAW"
        return img

    # Default path: trust Pillow.  pillow-heif / pillow-avif-plugin may have
    # already patched in extra formats here, so this also covers the case
    # where a user renamed a HEIC to .jpg by mistake -- Pillow still picks
    # the right decoder via magic bytes.
    return Image.open(p)
