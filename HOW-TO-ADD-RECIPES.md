# How to Add a New Cookbook

## Quick steps

1. **Screenshot the new cookbook** — take screenshots of every recipe page in order (use CleanShot or similar). Put them all in a folder like:
   ```
   ~/Desktop/Cookbook Screenshots/Book Title/
   ```

2. **Edit `extract_recipes.py`** — update the config at the top:
   ```python
   SCREENSHOTS_DIR = Path("/path/to/your/new/screenshots/folder")
   ```

3. **Update the cookbook metadata** near the top of the script:
   ```python
   COOKBOOK = {
       "title": "Land of Fish and Rice",
       "author": "Fuchsia Dunlop",
       "year": 2016,
   }
   ```

4. **Run the script:**
   ```bash
   cd ~/Desktop/cookbook-site
   python3 extract_recipes.py
   ```
   It will extract recipes and photos, appending to `recipes.json`.

   > Cost: ~$0.25 for 230 images using claude-haiku.

5. **Re-deploy to Netlify** — drag the `cookbook-site/` folder back onto [netlify.com/drop](https://app.netlify.com/drop).

---

## Adding multiple books

The script currently *overwrites* `recipes.json`. To accumulate recipes across multiple books:

- Run the script once per book, saving each output as `recipes-bookname.json`
- Then merge them manually, combining the `cookbooks` and `recipes` arrays

Or, modify the script to load existing `recipes.json` first and append rather than overwrite (simple change in the `main()` function).

---

## Troubleshooting

- **Missing photos**: The script copies photo pages automatically. If a recipe shows no photo in the site, the photo page may have appeared before the recipe start (rare) — look in `images/` for orphaned files.
- **Wrong category**: The `ingredient_category` field is inferred from the chapter heading. You can manually edit `recipes.json` to fix any miscategorizations.
- **Script errors**: Make sure your `ANTHROPIC_API_KEY` environment variable is set.
