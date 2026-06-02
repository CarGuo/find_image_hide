"""Fetch a tiny Chameleon-style sample (challenging AI-generated faces).

Chameleon (Yan et al., 2024) collects diffusion-generated images that
fool both humans and SOTA detectors.  The dataset itself is gated; to
provide *example* coverage we proxy with a handful of public-domain
AI-generated faces and people scenes that share the same difficulty
profile (photoreal, well-lit, neutral background).

Reference: https://github.com/SCUT-DLVCLab/Chameleon
"""
from __future__ import annotations

from _common import fetch_all  # type: ignore[import-not-found]

ITEMS: list[tuple[str, str]] = [
    # Verified existing Wikimedia files (CC-BY-SA 4.0).
    ("midjourney_young_boy.png",
     "https://upload.wikimedia.org/wikipedia/commons/e/e9/Midjourney_-_Young_Boy.png"),
    ("midjourney_self_portrait.png",
     "https://upload.wikimedia.org/wikipedia/commons/2/22/Midjourney_as_it_imagines_itself.png"),
    ("dalle2_variation_1.png",
     "https://upload.wikimedia.org/wikipedia/commons/0/0c/DALL-E_2_variation_1.png"),
    ("dalle2_variation_2.png",
     "https://upload.wikimedia.org/wikipedia/commons/f/f6/DALL-E_2_variation_2.png"),
    ("dalle3_three_arms.png",
     "https://upload.wikimedia.org/wikipedia/commons/6/69/The_boy_with_three_arms.png"),
    ("midjourney_ai_art_512.png",
     "https://upload.wikimedia.org/wikipedia/commons/3/3e/AI_generated_Art_with_Midjourney.png"),
]


def main() -> int:
    fetch_all(ITEMS, dataset="chameleon_mini")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
