#!/usr/bin/env python3
"""
Cookbook extraction pipeline.
Processes screenshots of "Every Grain of Rice" (Fuchsia Dunlop) using Claude Haiku,
extracts recipe data, copies food photos, and outputs recipes.json.
"""

import anthropic
import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Set

# ── Config ──────────────────────────────────────────────────────────────────
SCREENSHOTS_DIR = Path("/Users/lanali/Desktop/Fucshia Dunlop Every Grain of Rice")
OUTPUT_DIR = Path("/Users/lanali/Desktop/cookbook-site")
IMAGES_DIR = OUTPUT_DIR / "images"
OUTPUT_JSON = OUTPUT_DIR / "recipes.json"

COOKBOOK = {
    "title": "Every Grain of Rice",
    "author": "Fuchsia Dunlop",
    "year": 2012,
}

# Ordered ingredient categories matching the book's chapters
INGREDIENT_CATEGORIES = [
    "pork", "chicken-eggs", "beef-lamb", "seafood",
    "tofu", "vegetables", "noodles", "soups", "other"
]

CHAPTER_TO_CATEGORY = {
    "PORK": "pork",
    "CHICKEN": "chicken-eggs",
    "EGGS": "chicken-eggs",
    "BEEF": "beef-lamb",
    "LAMB": "beef-lamb",
    "SEAFOOD": "seafood",
    "FISH": "seafood",
    "TOFU": "tofu",
    "BEAN CURD": "tofu",
    "VEGETABLES": "vegetables",
    "LEAFY GREENS": "vegetables",
    "ROOTS": "vegetables",
    "NOODLES": "noodles",
    "RICE": "noodles",
    "SOUPS": "soups",
    "MEAT": "pork",
}

MODEL = "claude-haiku-4-5-20251001"

# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def classify_and_extract(client: anthropic.Anthropic, image_path: Path) -> dict:
    """
    Ask Haiku to classify and extract data from a single screenshot.
    Returns a dict with keys: type, data
    """
    b64 = encode_image(image_path)
    prompt = """Analyze this screenshot from a cookbook (Fuchsia Dunlop's "Every Grain of Rice").

Classify it as exactly one of:
- recipe_start: first page of a recipe (has English title, possibly Chinese name/characters, intro text, ingredients)
- recipe_continuation: continuation of a recipe (ingredients list continued, or cooking instructions)
- photo_page: full-page or near-full-page food photograph, minimal text
- chapter_divider: colored section divider page with chapter title (e.g. MEAT, VEGETABLES, NOODLES)
- other: front matter, index, table of contents, blank, or unclassifiable

Respond with a single JSON object. No markdown, no explanation, just JSON.

Schema by type:

recipe_start:
{
  "type": "recipe_start",
  "title": "English recipe title",
  "chinese_name": "Romanized name + Chinese characters if visible, else null",
  "introduction": "Intro paragraph text or null",
  "ingredients": ["ingredient 1", "ingredient 2", ...],
  "instructions": "Cooking instructions if on this page, else null",
  "variations": ["variation text"] or []
}

recipe_continuation:
{
  "type": "recipe_continuation",
  "ingredients": ["additional ingredient 1", ...] or [],
  "instructions": "Additional or full instruction text or null",
  "variations": ["variation text"] or []
}

photo_page:
{
  "type": "photo_page",
  "caption": "Any caption text visible, or null"
}

chapter_divider:
{
  "type": "chapter_divider",
  "chapter": "CHAPTER NAME IN CAPS"
}

other:
{
  "type": "other"
}

Be thorough extracting ingredients (each as a separate list item) and instructions (as one block of text). If instructions span this and previous pages, include only what's on THIS page."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.BadRequestError as e:
        print(f"  SKIPPED (content filter): {image_path.name} — {e}")
        return {"type": "other"}

    raw = response.content[0].text.strip()
    # Strip any accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  WARNING: Could not parse JSON for {image_path.name}: {raw[:200]}")
        return {"type": "other"}


def infer_category(chapter: str, title: str) -> str:
    upper_chapter = chapter.upper()
    for key, cat in CHAPTER_TO_CATEGORY.items():
        if key in upper_chapter:
            return cat

    # Fallback: guess from title keywords
    title_lower = title.lower()
    keyword_map = {
        "pork": "pork", "bacon": "pork", "belly": "pork", "char siu": "pork",
        "chicken": "chicken-eggs", "egg": "chicken-eggs", "duck": "chicken-eggs",
        "beef": "beef-lamb", "lamb": "beef-lamb",
        "fish": "seafood", "shrimp": "seafood", "prawn": "seafood", "crab": "seafood", "clam": "seafood",
        "tofu": "tofu", "bean curd": "tofu",
        "noodle": "noodles", "rice": "noodles", "congee": "noodles",
        "soup": "soups", "broth": "soups",
    }
    for kw, cat in keyword_map.items():
        if kw in title_lower:
            return cat

    return "other"


def save_photo(image_path: Path, recipe_title: str, used_slugs: set) -> str:
    """Copy photo PNG to images/ dir. Returns relative filename."""
    base_slug = slugify(recipe_title) if recipe_title else slugify(image_path.stem)
    slug = base_slug
    counter = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{counter}"
        counter += 1
    used_slugs.add(slug)
    dest = IMAGES_DIR / f"{slug}.jpg"
    shutil.copy2(image_path, dest)
    # Rename with .jpg extension even though source is PNG (browsers handle it fine;
    # alternatively keep .png — use png for accuracy)
    dest_png = IMAGES_DIR / f"{slug}.png"
    shutil.copy2(image_path, dest_png)
    dest.unlink()  # remove .jpg copy, keep .png
    return f"images/{slug}.png"


# ── Main pipeline ────────────────────────────────────────────────────────────

def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    # Collect and sort screenshots by name (timestamp order)
    screenshots = sorted(SCREENSHOTS_DIR.glob("*.png"), key=lambda p: p.name)
    total = len(screenshots)
    print(f"Found {total} screenshots in {SCREENSHOTS_DIR}")

    # Load existing progress if recipes.json exists (resume support)
    already_processed: Set[str] = set()
    existing_recipes: list = []
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, encoding="utf-8") as f:
                existing_data = json.load(f)
            existing_recipes = existing_data.get("recipes", [])
            for r in existing_recipes:
                already_processed.update(r.get("source_screenshots", []))
            if already_processed:
                print(f"Resuming — {len(already_processed)} screenshots already processed, {len(existing_recipes)} recipes loaded")
        except Exception:
            pass

    recipes: list = list(existing_recipes)
    current_recipe: Optional[dict] = None
    current_chapter = "UNKNOWN"
    used_photo_slugs: Set[str] = set(r["photo_file"].replace("images/", "").replace(".png", "") for r in existing_recipes if r.get("photo_file"))

    def finalize_recipe():
        nonlocal current_recipe
        if current_recipe and current_recipe.get("title"):
            # Ensure required fields
            current_recipe.setdefault("chinese_name", None)
            current_recipe.setdefault("introduction", None)
            current_recipe.setdefault("ingredients", [])
            current_recipe.setdefault("instructions", None)
            current_recipe.setdefault("variations", [])
            current_recipe.setdefault("photo_file", None)
            current_recipe.setdefault("source_screenshots", [])
            current_recipe["id"] = slugify(current_recipe["title"])
            recipes.append(current_recipe)
        current_recipe = None

    for i, img_path in enumerate(screenshots, 1):
        if img_path.name in already_processed:
            print(f"[{i:3d}/{total}] {img_path.name} ... SKIP (already done)")
            continue
        print(f"[{i:3d}/{total}] {img_path.name}", end=" ... ", flush=True)
        result = classify_and_extract(client, img_path)
        page_type = result.get("type", "other")
        print(page_type)

        if page_type == "chapter_divider":
            current_chapter = result.get("chapter", "UNKNOWN").upper()

        elif page_type == "recipe_start":
            finalize_recipe()
            title = result.get("title", "").strip()
            current_recipe = {
                "title": title,
                "chinese_name": result.get("chinese_name"),
                "source_book": COOKBOOK["title"],
                "chapter": current_chapter,
                "main_ingredient": None,  # derived below
                "ingredient_category": infer_category(current_chapter, title),
                "introduction": result.get("introduction"),
                "ingredients": result.get("ingredients", []),
                "instructions": result.get("instructions") or "",
                "variations": result.get("variations", []),
                "photo_file": None,
                "source_screenshots": [img_path.name],
            }

        elif page_type == "recipe_continuation":
            if current_recipe:
                current_recipe["ingredients"].extend(result.get("ingredients", []))
                extra_instructions = result.get("instructions")
                if extra_instructions:
                    if current_recipe["instructions"]:
                        current_recipe["instructions"] += "\n\n" + extra_instructions
                    else:
                        current_recipe["instructions"] = extra_instructions
                current_recipe["variations"].extend(result.get("variations", []))
                current_recipe["source_screenshots"].append(img_path.name)

        elif page_type == "photo_page":
            if current_recipe:
                # Only use first photo per recipe
                if current_recipe["photo_file"] is None:
                    photo_ref = save_photo(img_path, current_recipe["title"], used_photo_slugs)
                    current_recipe["photo_file"] = photo_ref
                    current_recipe["source_screenshots"].append(img_path.name)
                    print(f"       -> saved photo: {photo_ref}")

    # Don't forget the last recipe
    finalize_recipe()

    # Derive main_ingredient from first ingredient or title heuristic
    for r in recipes:
        if r["ingredients"]:
            # First ingredient is often the main one; strip quantity
            first = r["ingredients"][0]
            main = re.sub(r"^\d+[\w.]*\s*(g|kg|ml|l|tbsp|tsp|oz|lb|cups?|cloves?|rashers?|slices?)?\s*", "", first, flags=re.IGNORECASE).strip()
            r["main_ingredient"] = main.split(",")[0].strip() or None
        else:
            r["main_ingredient"] = None

    output = {
        "cookbooks": [COOKBOOK],
        "recipes": recipes,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Extracted {len(recipes)} recipes.")
    print(f"Output: {OUTPUT_JSON}")
    print(f"Photos: {len([r for r in recipes if r['photo_file']])} recipes have photos")


if __name__ == "__main__":
    main()
