"""Fetch a tiny GenImage-style sample (AI-generated showcase).

GenImage (Zhu et al., NeurIPS 2023) is a 1.3M-image benchmark for
AI-generated detection.  The full archive needs the official Google Drive
link.  For demo purposes we instead pull a handful of public-domain
AI-generated examples from Wikimedia that cover the same generators
(Stable Diffusion, ADM, BigGAN, Midjourney, DALL-E).

Citation::

    @inproceedings{zhu2023genimage,
        title  = {GenImage: A Million-Scale Benchmark for Detecting AI-Generated Image},
        author = {Zhu, Mingjian and Chen, Hanting and Yan, Qiangyu and ...},
        booktitle = {NeurIPS},
        year   = {2023},
    }
"""
from __future__ import annotations

from _common import fetch_all  # type: ignore[import-not-found]

ITEMS: list[tuple[str, str]] = [
    ("dalle3_wikipedia_example.png",
     "https://upload.wikimedia.org/wikipedia/commons/a/ad/DALL-E_3_Wikipedia_Example.png"),
    ("dalle3_modern_arch.png",
     "https://upload.wikimedia.org/wikipedia/commons/2/2b/DALL-E_3_example_AI_generated_image.png"),
    ("dalle2_shiba_beret.jpg",
     "https://upload.wikimedia.org/wikipedia/commons/2/2b/A_Shiba_Inu_dog_wearing_a_beret_and_black_turtleneck_DALLE2.jpg"),
    ("midjourney_oldtimer.png",
     "https://upload.wikimedia.org/wikipedia/commons/3/33/Midjourney_-_Oldtimer.png"),
    ("midjourney_castle.png",
     "https://upload.wikimedia.org/wikipedia/commons/8/8c/Midjourney_-_Dark_Castle_with_Dragon.png"),
    ("sdxl_poisoned_examples.png",
     "https://upload.wikimedia.org/wikipedia/commons/2/20/Example_images_generated_by_SD-XL_when_poisoned_with_data_poisoning_samples_according_to_a_study.png"),
]


def main() -> int:
    fetch_all(ITEMS, dataset="genimage_mini")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
