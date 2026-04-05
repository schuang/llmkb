#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local KB update pipeline.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force rebuilds in extraction, source pages, and concept pages."
    )
    parser.add_argument("--doc-id", action="append", default=[], help="Limit the update to selected doc_ids.")
    return parser.parse_args()


def run_step(script: str, args: list[str]) -> None:
    module = f"llmkb.{script.replace('.py', '')}"
    command = [sys.executable, "-m", module, *args]
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    extra_args: list[str] = ["--kb-root", args.kb_root]
    for doc_id in args.doc_id:
        extra_args.extend(["--doc-id", doc_id])
    if args.force:
        extra_args.append("--force")

    run_step("catalog_raw.py", ["--kb-root", args.kb_root])
    run_step("clean_kb.py", ["--kb-root", args.kb_root])
    run_step("extract_pages.py", extra_args)
    run_step("resolve_near_duplicates.py", extra_args)
    run_step("build_source_pages.py", extra_args)
    run_step("build_concept_pages.py", ["--kb-root", args.kb_root])


if __name__ == "__main__":
    main()
