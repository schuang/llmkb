#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reject/Archive a source from the knowledge base.")
    parser.add_argument("doc_id", help="The doc_id of the source to reject.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--reason",
        help="Optional reason for rejection (saved to overrides).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without moving files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)

    if not context.catalog_path.exists():
        print(f"Error: Catalog not found at {context.catalog_path}. Run llmkb-catalog first.")
        return

    catalog = load_json(context.catalog_path)
    entry = next((doc for doc in catalog.get("documents", []) if doc["doc_id"] == args.doc_id), None)

    if not entry:
        print(f"Error: doc_id '{args.doc_id}' not found in catalog.")
        return

    # 1. Determine paths
    rel_path = entry["path"]
    source_path = Path(rel_path)
    if not source_path.is_absolute():
        source_path = context.root / rel_path

    rejected_dir = context.root / "raw" / "rejected"
    new_path = rejected_dir / source_path.name

    print(f"Rejecting '{args.doc_id}'...")

    # 2. Move the physical file
    if not source_path.exists():
        print(f"Warning: Source file not found at {source_path}")
    else:
        if args.dry_run:
            print(f"  [Dry Run] Would move file: {source_path} -> {new_path}")
        else:
            rejected_dir.mkdir(parents=True, exist_ok=True)
            # Handle collisions in rejected folder
            counter = 1
            while new_path.exists():
                new_path = rejected_dir / f"{source_path.stem}-{counter}{source_path.suffix}"
                counter += 1
            
            print(f"  Moving file to: {new_path.relative_to(context.root)}")
            source_path.rename(new_path)

    # 3. Update source_overrides.json
    if not args.dry_run:
        overrides = load_json(context.overrides_path) if context.overrides_path.exists() else {}
        
        doc_override = overrides.get(args.doc_id, {})
        doc_override["status"] = "rejected"
        if args.reason:
            doc_override["rejection_reason"] = args.reason
        
        overrides[args.doc_id] = doc_override
        write_json(context.overrides_path, overrides)
        print(f"  Updated overrides for '{args.doc_id}'.")

    # 4. Cleanup Generated Artifacts (similar to llmkb-clean logic)
    # We don't delete here; we recommend running llmkb-clean or let llmkb-update handle it.
    # But since we want "Soft Deletion" to feel immediate, let's at least mention it.
    
    if not args.dry_run:
        print("\nRejection complete.")
        print("Run 'llmkb-update' (or 'llmkb-clean') to remove the document from your wiki and search index.")


if __name__ == "__main__":
    main()
