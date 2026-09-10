#!/usr/bin/env python3
"""
Check that every page declared in docs.json navigation has a corresponding
.mdx file on disk. Catches the common mistake of adding a new API version
to the navigation for es/fr without creating the translated MDX stubs.

Exit 0 if all pages exist, exit 1 if any are missing.
"""

import json
import os
import sys


def extract_pages(obj):
    """Recursively extract all page path strings from the navigation tree."""
    pages = []
    if isinstance(obj, str):
        pages.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            pages.extend(extract_pages(item))
    elif isinstance(obj, dict):
        for key in ("pages", "groups", "tabs", "versions", "languages"):
            if key in obj:
                pages.extend(extract_pages(obj[key]))
    return pages


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_json_path = os.path.join(repo_root, "docs.json")

    if not os.path.exists(docs_json_path):
        print("docs.json not found, skipping i18n page check.")
        return 0

    with open(docs_json_path) as f:
        data = json.load(f)

    navigation = data.get("navigation", {})
    all_pages = extract_pages(navigation)

    missing = []
    for page_path in all_pages:
        mdx_file = os.path.join(repo_root, page_path + ".mdx")
        if not os.path.exists(mdx_file):
            missing.append(page_path)

    if not missing:
        print(f"All {len(all_pages)} declared pages have .mdx files.")
        return 0

    print(f"\n{len(missing)} page(s) declared in docs.json have no .mdx file:\n")

    by_dir = {}
    for p in missing:
        parts = p.split("/")
        key = "/".join(parts[:3]) if len(parts) >= 3 else p
        by_dir.setdefault(key, []).append(p)

    for dir_key in sorted(by_dir):
        pages_in_dir = by_dir[dir_key]
        print(f"  {dir_key}/ ({len(pages_in_dir)} missing)")
        for p in pages_in_dir[:3]:
            print(f"    {p}.mdx")
        if len(pages_in_dir) > 3:
            print(f"    ... and {len(pages_in_dir) - 3} more")

    print(
        "\nTo fix: create the missing .mdx stubs (copy from the previous "
        "version and update the openapi frontmatter)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
