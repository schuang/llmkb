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
        print(f"Error: Catalog not found at {context.catalog_path}. Run llmkb-add first.")
        return False

    catalog = load_json(context.catalog_path)
    old_entry = next((doc for doc in catalog.get("documents", []) if doc["doc_id"] == old_id), None)
    new_entry = next((doc for doc in catalog.get("documents", []) if doc["doc_id"] == new_id), None)

    if not old_entry:
        print(f"Error: Current doc_id '{old_id}' not found in catalog.")
        return False
        
    if new_entry:
        print(f"Error: Target doc_id '{new_id}' is already in use by: {new_entry.get('path')}")
        return False

    # 1. Determine paths
    old_rel_path = old_entry["path"]
    old_file_path = context.root / old_rel_path
    
    # Calculate new file path (preserving original extension)
    original_ext = Path(old_rel_path).suffix
    new_filename = f"{new_id}{original_ext}"
    new_file_path = old_file_path.parent / new_filename
    
    # Bulletproof Check: Physical file collision
    if new_file_path.exists() and new_file_path.resolve() != old_file_path.resolve():
        print(f"Error: A physical file already exists at target path: {new_file_path.relative_to(context.root)}")
        return False
        
    # Bulletproof Check: Artifact collision
    new_extract_dir = context.extract_dir / new_id
    if new_extract_dir.exists():
        print(f"Error: Extraction artifacts already exist for target id: {new_id}")
        return False
        
    # Bulletproof Check: Wiki page collision
    new_wiki_page = context.source_wiki_dir / f"{new_id}.md"
    if new_wiki_page.exists():
        print(f"Error: A wiki page already exists for target id: {new_id}")
        return False

    print(f"Renaming '{old_id}' to '{new_id}'...")

    # 2. Perform Physical Rename
    if not old_file_path.exists():
        print(f"Warning: Source file not found at {old_file_path}")
    else:
        if dry_run:
            print(f"  [Dry Run] Would rename file: {old_file_path.name} -> {new_filename}")
        else:
            print(f"  Renaming file: {old_file_path.name} -> {new_filename}")
            old_file_path.rename(new_file_path)

    # 3. Rename artifact folder
    old_extract_dir = context.extract_dir / old_id
    if old_extract_dir.exists():
        if dry_run:
            print(f"  [Dry Run] Would rename artifacts: {old_id} -> {new_id}")
        else:
            print(f"  Renaming artifacts: {old_id} -> {new_id}")
            old_extract_dir.rename(new_extract_dir)

    # 4. Rename wiki page
    old_wiki_page = context.source_wiki_dir / f"{old_id}.md"
    if old_wiki_page.exists():
        if dry_run:
            print(f"  [Dry Run] Would rename wiki page: {old_id}.md -> {new_id}.md")
        else:
            print(f"  Renaming wiki page: {old_id}.md -> {new_id}.md")
            old_wiki_page.rename(new_wiki_page)

    # 5. Update source_overrides.json
    overrides_path = context.overrides_path
    overrides_payload = load_json(overrides_path) if overrides_path.exists() else {}
    if old_id in overrides_payload:
        if dry_run:
            print(f"  [Dry Run] Would update override entry for {old_id}")
        else:
            print(f"  Updating override entry for {old_id}")
            data = overrides_payload.pop(old_id)
            overrides_payload[new_id] = data
            write_json(overrides_path, overrides_payload)

    # 6. Update wiki links
    if not no_link_update:
        update_wiki_links(context.wiki_dir, old_id, new_id, dry_run)

    # 7. Update sources.json directly
    if not dry_run:
        catalog["documents"] = [doc for doc in catalog.get("documents", []) if doc["doc_id"] != old_id]
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
