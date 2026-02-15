#!/usr/bin/env python3
"""Download the full Prismata wiki from Fandom via the MediaWiki API.

Saves all pages as individual text files in docs/wiki/ plus a JSON index.
Uses the MediaWiki API (no scraping, no auth needed).

Usage:
    python tools/download_wiki.py
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error

API_URL = "https://prismata.fandom.com/api.php"
OUTPUT_DIR = "docs/wiki"
INDEX_FILE = os.path.join(OUTPUT_DIR, "_index.json")
DELAY = 0.5  # seconds between requests (be polite)


def api_request(params):
    """Make a MediaWiki API request and return parsed JSON."""
    params["format"] = "json"
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "PrismataAI-WikiDump/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_all_pages():
    """Get all page titles from the wiki using allpages API."""
    pages = []
    params = {
        "action": "query",
        "list": "allpages",
        "aplimit": "500",
        "apnamespace": "0",  # main namespace only
    }

    while True:
        data = api_request(params)
        batch = data.get("query", {}).get("allpages", [])
        pages.extend(batch)
        print(f"  Listed {len(pages)} pages so far...")

        # Check for continuation
        if "continue" in data:
            params["apcontinue"] = data["continue"]["apcontinue"]
            time.sleep(DELAY)
        else:
            break

    return pages


def get_page_content(title):
    """Get the wikitext content of a page."""
    params = {
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "disablelimitreport": "true",
    }
    try:
        data = api_request(params)
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        return wikitext
    except urllib.error.HTTPError as e:
        print(f"    HTTP error fetching '{title}': {e.code}")
        return None
    except Exception as e:
        print(f"    Error fetching '{title}': {e}")
        return None


def sanitize_filename(title):
    """Convert a wiki page title to a safe filename."""
    # Replace characters that aren't safe in filenames
    safe = re.sub(r'[<>:"/\\|?*]', '_', title)
    safe = safe.strip('. ')
    if not safe:
        safe = "_unnamed"
    return safe + ".txt"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Check for existing index (resume support)
    existing = set()
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
            existing = {entry["title"] for entry in index if entry.get("status") == "ok"}
        print(f"Found existing index with {len(existing)} downloaded pages.")
    else:
        index = []

    # Step 1: List all pages
    print("Listing all wiki pages...")
    all_pages = get_all_pages()
    print(f"Found {len(all_pages)} pages total.")

    # Step 2: Download each page
    new_count = 0
    skip_count = 0
    fail_count = 0

    # Build index lookup by title
    index_by_title = {entry["title"]: entry for entry in index}

    for i, page in enumerate(all_pages):
        title = page["title"]
        pageid = page["pageid"]
        filename = sanitize_filename(title)

        if title in existing:
            skip_count += 1
            continue

        print(f"  [{i+1}/{len(all_pages)}] Downloading: {title}")
        content = get_page_content(title)
        time.sleep(DELAY)

        if content is not None:
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"= {title} =\n\n")
                f.write(content)

            entry = {
                "title": title,
                "pageid": pageid,
                "filename": filename,
                "size": len(content),
                "status": "ok",
            }
            new_count += 1
        else:
            entry = {
                "title": title,
                "pageid": pageid,
                "filename": None,
                "size": 0,
                "status": "error",
            }
            fail_count += 1

        index_by_title[title] = entry

        # Save index periodically (every 20 pages)
        if (new_count + fail_count) % 20 == 0:
            _save_index(index_by_title)

    # Final save
    _save_index(index_by_title)

    print(f"\n=== Wiki Download Complete ===")
    print(f"  New pages downloaded: {new_count}")
    print(f"  Skipped (already had): {skip_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Total in index: {len(index_by_title)}")
    print(f"  Output directory: {OUTPUT_DIR}/")


def _save_index(index_by_title):
    """Save the index to disk."""
    index_list = sorted(index_by_title.values(), key=lambda x: x["title"])
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_list, f, indent=2)


if __name__ == "__main__":
    main()
