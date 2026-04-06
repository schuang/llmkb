#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import os
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rename a source and update all references.")
    parser.add_argument("old_id", help="The current doc_id of the source.")
    parser.add_argument("new_id", help="The new doc_id for the source.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--no-link-update",
        action="store_true",
        help="Skip updating wiki links (not recommended).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes.",
    )
    return parser.parse_args()


def update_wiki_links(wiki_dir: Path, old_id: str, new_id: str, dry_run: bool) -> None:
    # Pattern to match [[source/old_id]] or [[source/old_id#p123]]
    # We use a non-greedy match for the anchor part
    pattern = re.compile(r"\[\[source/" + re.escape(old_id) + r"(#p\d+)?\]\]")
    replacement = r"[[source/" + new_id + r"\1]]"

    print(f"Updating links in {wiki_dir}...")
    for md_file in wiki_dir.rglob("*.md"):
        content = md_file.read_text()
        if pattern.search(content):
            new_content = pattern.sub(replacement, content)
            if dry_run:
                print(f"  Would update links in: {md_file}")
            else:
                print(f"  Updating links in: {md_file}")
                md_file.write_text(new_content)



def rename_document(context: KBContext, old_id: str, new_id: str, dry_run: bool = False, no_link_update: bool = False) -> bool:
    """Rename a document and all its associated artifacts across the knowledge base.
    
    Returns True if successful, False otherwise.
    """
    if not context.catalog_path.exists():
        print(f"Catalog not found at {context.catalog_path}. Run llmkb-catalog first.")
        return False

    catalog = load_json(context.catalog_path)
    old_entry = next((doc for doc in catalog.get("documents", []) if doc["doc_id"] == old_id), None)

    if not old_entry:
        print(f"Error: doc_id '{old_id}' not found in catalog.")
        return False

    # 1. Rename the physical file
    old_rel_path = old_entry["path"]
    old_file_path = Path(old_rel_path)
    if not old_file_path.is_absolute():
         old_file_path = context.root / old_rel_path
    
    if not old_file_path.exists():
        print(f"Warning: Source file not found at {old_file_path}")
    else:
        # Avoid simple replace to not mess up path components if doc_id is short
        new_filename = f"{new_id}{old_file_path.suffix}"
        new_file_path = old_file_path.parent / new_filename
        if dry_run:
            print(f"Would rename file: {old_file_path} -> {new_file_path}")
        else:
            print(f"Renaming file: {old_file_path} -> {new_file_path}")
            old_file_path.rename(new_file_path)

    # 2. Rename artifact folder
    old_extract_dir = context.extract_dir / old_id
    new_extract_dir = context.extract_dir / new_id
    if old_extract_dir.exists():
        if dry_run:
            print(f"Would rename artifacts: {old_extract_dir} -> {new_extract_dir}")
        else:
            print(f"Renaming artifacts: {old_extract_dir} -> {new_extract_dir}")
            old_extract_dir.rename(new_extract_dir)

    # 3. Rename wiki page
    old_wiki_page = context.source_wiki_dir / f"{old_id}.md"
    new_wiki_page = context.source_wiki_dir / f"{new_id}.md"
    if old_wiki_page.exists():
        if dry_run:
            print(f"Would rename wiki page: {old_wiki_page} -> {new_wiki_page}")
        else:
            print(f"Renaming wiki page: {old_wiki_page} -> {new_wiki_page}")
            old_wiki_page.rename(new_wiki_page)

    # 4. Update source_overrides.json
    overrides_path = context.overrides_path
    overrides_payload = load_json(overrides_path) if overrides_path.exists() else {}
    if old_id in overrides_payload:
        if dry_run:
            print(f"Would update override entry for {old_id}")
        else:
            print(f"Updating override entry for {old_id}")
            data = overrides_payload.pop(old_id)
            overrides_payload[new_id] = data
            write_json(overrides_path, overrides_payload)

    # 5. Update wiki links
    if not no_link_update:
        update_wiki_links(context.wiki_dir, old_id, new_id, dry_run)

    # 6. Update sources.json directly
    if not dry_run:
        catalog["documents"] = [doc for doc in catalog.get("documents", []) if doc["doc_id"] != old_id]
        # We don't add the NEW entry here because llmkb-update will pick it up correctly 
        # now that the physical file is renamed and the Duplicate Shield is fixed.
        # Removing the old entry prevents "phantom" duplicates.
        write_json(context.catalog_path, catalog)

    return True

def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    
    success = rename_document(context, args.old_id, args.new_id, args.dry_run, args.no_link_update)
    if success and not args.dry_run:
        print("\nRename complete. Please run 'llmkb-update' to refresh the catalog and indices.")

if __name__ == "__main__":
    main()
