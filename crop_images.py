#!/usr/bin/env python3
"""
Crop food photos out of Kindle Mac app screenshots.
Clean full-page photos are left untouched.
"""

import anthropic
import base64
import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

IMAGES_DIR = Path("/Users/lanali/Desktop/cookbook-site/images")
MODEL = "claude-haiku-4-5-20251001"


def is_kindle_screenshot(img_path: Path) -> bool:
    """Returns True if the image has a dark Mac menu bar at the top."""
    img = Image.open(img_path).convert("RGB")
    region = img.crop((0, 0, 50, 15))
    pixels = list(region.getdata())
    avg = sum(sum(p) for p in pixels) / (len(pixels) * 3)
    return avg < 80


def get_crop_box(client: anthropic.Anthropic, img_path: Path) -> Optional[Tuple[int, int, int, int]]:
    """Ask Haiku for the bounding box of the food photo in the screenshot."""
    with open(img_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    img = Image.open(img_path)
    w, h = img.size

    prompt = f"""This is a screenshot of the Kindle app on a Mac showing a cookbook page with a food photograph embedded in it.

The image is {w}x{h} pixels.

Your task: identify the bounding box of ONLY the food photograph (the dish/food image), excluding:
- The Mac menu bar and window chrome
- The Kindle app toolbar
- All text (recipe name, captions, instructions)
- The white page background/margins
- Any other UI elements

Return ONLY a JSON object with the pixel coordinates of the food photo, like this:
{{"left": 120, "top": 95, "right": 580, "bottom": 740}}

No explanation, just the JSON."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        box = json.loads(raw)
        return (box["left"], box["top"], box["right"], box["bottom"])
    except Exception as e:
        print(f"  ERROR getting crop box: {e}")
        return None


def crop_image(img_path: Path, box: Tuple[int, int, int, int], padding: int = 10):
    """Crop the image to the box (with padding) and save in place."""
    img = Image.open(img_path)
    w, h = img.size
    left = max(0, box[0] - padding)
    top = max(0, box[1] - padding)
    right = min(w, box[2] + padding)
    bottom = min(h, box[3] + padding)
    cropped = img.crop((left, top, right, bottom))
    cropped.save(img_path, "PNG", optimize=True)
    return (right - left, bottom - top)


def main():
    client = anthropic.Anthropic()

    images = sorted(IMAGES_DIR.glob("*.png"))
    to_crop = [p for p in images if is_kindle_screenshot(p)]
    print(f"Found {len(to_crop)} images to crop (out of {len(images)} total)\n")

    for i, img_path in enumerate(to_crop, 1):
        print(f"[{i:2d}/{len(to_crop)}] {img_path.name}", end=" ... ", flush=True)
        box = get_crop_box(client, img_path)
        if box:
            new_size = crop_image(img_path, box)
            print(f"cropped to {new_size[0]}x{new_size[1]} (box: {box})")
        else:
            print("SKIPPED (no crop box returned)")

    print("\nDone!")


if __name__ == "__main__":
    main()
