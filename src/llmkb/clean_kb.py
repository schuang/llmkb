#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from llmkb.kb_common import KBContext, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove artifacts and wiki pages for sources no longer in the catalog.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting it.",
    )
    return parser.parse_args()


def remove_path(path: Path, dry_run: bool) -> None:
    if not path.exists():
        return
    if dry_run:
        print(f"Would delete: {path}")
        return
    
    print(f"Deleting: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    
    if not context.catalog_path.exists():
        print(f"Catalog not found at {context.catalog_path}. Run catalog_raw.py first.")
        return

    catalog = load_json(context.catalog_path)
    valid_doc_ids = {doc["doc_id"] for doc in catalog.get("documents", [])}

    # 1. Clean up artifacts/extract/<doc_id>
    if context.extract_dir.exists():
        for doc_dir in context.extract_dir.iterdir():
            if doc_dir.is_dir() and doc_dir.name not in valid_doc_ids:
                remove_path(doc_dir, args.dry_run)

    # 2. Clean up wiki/source/<doc_id>.md
    if context.source_wiki_dir.exists():
        for source_page in context.source_wiki_dir.glob("*.md"):
            if source_page.stem not in valid_doc_ids:
                remove_path(source_page, args.dry_run)
                
    if args.dry_run:
        print("Dry run complete. No files were deleted.")

if __name__ == "__main__":
    main()
