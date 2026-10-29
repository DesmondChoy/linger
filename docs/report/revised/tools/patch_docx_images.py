#!/usr/bin/env python3
"""Copy the figures the revised report keeps from the Word draft, applying small fixes.

Run from the repository root with the path to the Word draft:

    python3 -I docs/report/revised/tools/patch_docx_images.py Linger_Group_Project_Report_4.docx

Fixes applied, each recorded in docs/report/revised/CHANGES.md:
- Figure 1.1: crop the slide deck's navigation bar.
- Figures 3.1, 3.4 and 3.6: remove the "Fixed reply, turn ends" legend entry,
  which those figures never use.
- Figure 3.8: replace the file path in step 1 with what the check does.
- Figure 4.1: the review application is now Figure 2.6, not Figure 2.9.
- Figure F.3: crop the card whose description shows a raw Markdown link.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "figures"
INTER = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
LIBERATION = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# Word media name -> file name in the revised report.
KEEP = {
    "image14.jpg": "fig-1-1-problem.png",
    "image21.png": "fig-1-2-one-note.png",
    "image3.png": "fig-2-4-state-lifetimes.png",
    "image43.png": "fig-2-5-chat-and-inspect.png",
    "image23.png": "fig-2-6-ground-truth-review.png",
    "image32.png": "fig-3-1-muse-skills.png",
    "image15.png": "fig-3-2-librarian-skills.png",
    "image34.png": "fig-3-3-serendipity-skills.png",
    "image6.png": "fig-3-4-provenance-skills.png",
    "image4.png": "fig-3-5-provenance-outcome.png",
    "image13.png": "fig-3-6-sculptor-skills.png",
    "image10.png": "fig-3-8-input-checks.png",
    "image31.png": "fig-3-9-agent-context.png",
    "image8.png": "fig-3-10-recorded-handoff.png",
    "image20.png": "fig-3-11-release-path.png",
    "image24.png": "fig-4-1-scenario-pipeline.png",
    "image9.png": "fig-4-2-check-coverage.png",
    "image19.png": "fig-4-3-scenario-coverage.png",
    "image11.png": "fig-4-4-results.png",
    "image29.png": "fig-4-5-agreement.png",
    "image12.png": "fig-4-6-douglass-scene.png",
    "image17.png": "fig-10-2-stage-survival.png",
    "image40.png": "fig-f-1-landing.png",
    "image42.png": "fig-f-2-memories.png",
    "image41.png": "fig-f-3-scenario-list.png",
    "image38.png": "fig-f-4-saved-evaluation.png",
    "image28.png": "fig-g-1-request-plan-fix.png",
}


def dark_bbox(image: Image.Image, box: tuple[int, int, int, int], threshold: int = 150):
    grey = image.convert("L").crop(box)
    pixels = grey.load()
    width, height = grey.size
    points = [(x, y) for x in range(width) for y in range(height) if pixels[x, y] < threshold]
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (box[0] + min(xs), box[1] + min(ys), box[0] + max(xs), box[1] + max(ys))


def remove_unused_legend(image: Image.Image) -> Image.Image:
    """White out the third legend item ("Fixed reply, turn ends") at the top left."""
    bbox = dark_bbox(image, (420, 5, 900, 85))
    if bbox is None:
        raise SystemExit("legend entry not found")
    draw = ImageDraw.Draw(image)
    draw.rectangle((bbox[0] - 6, bbox[1] - 6, bbox[2] + 6, bbox[3] + 6), fill="white")
    return image


def fitted_font(path: str, sample: str, target_width: int) -> ImageFont.FreeTypeFont:
    size = 10
    while True:
        font = ImageFont.truetype(path, size + 1)
        if font.getlength(sample) > target_width:
            return ImageFont.truetype(path, size)
        size += 1


def replace_rate_limit_path(image: Image.Image) -> Image.Image:
    old = "apps/backend/rate_limit.py"
    bbox = dark_bbox(image, (60, 300, 900, 345))
    font = fitted_font(INTER, old, bbox[2] - bbox[0])
    draw = ImageDraw.Draw(image)
    draw.rectangle((bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2), fill="white")
    new = "ten messages a minute per account"
    centre = (bbox[0] + bbox[2]) / 2
    # Anchor on the ascender line so the new text sits where the old text sat.
    draw.text((centre, bbox[1]), new, font=font, fill=(61, 68, 77), anchor="mt")
    return image


def renumber_review_figure(image: Image.Image) -> Image.Image:
    """Change "(Figure 2.9)." to "(Figure 2.6)." by redrawing the last digit."""
    two = dark_bbox(image, (1159, 353, 1175, 380), threshold=215)
    nine = dark_bbox(image, (1179, 353, 1194, 375), threshold=235)
    height = two[3] - two[1] + 1
    size = 10
    while ImageFont.truetype(LIBERATION, size + 1).getbbox("6")[3] - ImageFont.truetype(LIBERATION, size + 1).getbbox("6")[1] <= height:
        size += 1
    font = ImageFont.truetype(LIBERATION, size)
    draw = ImageDraw.Draw(image)
    draw.rectangle((nine[0] - 1, nine[1] - 2, nine[2] + 1, nine[3] + 1), fill="white")
    left, top, _, _ = font.getbbox("6")
    draw.text((nine[0] - left, two[1] - top), "6", font=font, fill=(17, 17, 17))
    return image


def crop_navigation_bar(image: Image.Image) -> Image.Image:
    return image.crop((0, 62, image.width, image.height))


def crop_last_card_row(image: Image.Image) -> Image.Image:
    return image.crop((0, 0, image.width, 742))


PATCHES = {
    "image14.jpg": crop_navigation_bar,
    "image32.png": remove_unused_legend,
    "image6.png": remove_unused_legend,
    "image13.png": remove_unused_legend,
    "image10.png": replace_rate_limit_path,
    "image24.png": renumber_review_figure,
    "image41.png": crop_last_card_row,
}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(sys.argv[1]) as docx:
        for media, name in KEEP.items():
            image = Image.open(io.BytesIO(docx.read(f"word/media/{media}"))).convert("RGB")
            patch = PATCHES.get(media)
            if patch:
                image = patch(image)
            image.save(OUT / name, optimize=True)
            print(f"{media} -> {name}{' (patched)' if patch else ''}")


if __name__ == "__main__":
    main()
