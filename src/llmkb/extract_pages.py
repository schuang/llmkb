#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Any

from llmkb.kb_common import (
    KBContext,
    ensure_directory,
    load_json,
    page_preview,
    slugify,
    utc_now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract text from cataloged documents (PDF, ePub, Word, etc.).")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Path to the catalog JSON. Defaults to <kb-root>/artifacts/catalog/sources.json",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        help="Directory to write extracted text. Defaults to <kb-root>/artifacts/extract",
    )
    parser.add_argument("--doc-id", action="append", default=[], help="Limit extraction to selected doc_ids.")
    parser.add_argument("--force", action="store_true", help="Re-extract even if current artifacts exist.")
    return parser.parse_args()


def extract_pdf_text(path: str) -> str:
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        text=False,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def run_ocr(pdf_path: Path) -> list[str]:
    """Perform OCR on a PDF by converting pages to images and running Tesseract."""
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        print("Warning: 'tesseract' or 'pdftoppm' not found. Skipping OCR.")
        return []

    pages = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"OCR: Converting {pdf_path.name} to images...")
        subprocess.run(
            ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(tmp_path / "page")],
            check=True
        )
        img_files = sorted(tmp_path.glob("*.png"), key=lambda x: x.name)
        for i, img in enumerate(img_files, start=1):
            print(f"OCR: Processing page {i}/{len(img_files)}...", end="\r")
            result = subprocess.run(["tesseract", str(img), "stdout"], capture_output=True, text=True, check=False)
            pages.append(result.stdout if result.returncode == 0 else "")
        print()
    return pages


def extract_non_pdf_sections(path: Path) -> list[dict[str, Any]]:
    """Convert a non-PDF document to Markdown via Pandoc and split by headers."""
    if not shutil.which("pandoc"):
        print(f"Warning: 'pandoc' not found. Skipping {path.name}")
        return []

    result = subprocess.run(
        ["pandoc", str(path), "-t", "markdown_strict", "--wrap=none"],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []

    text = result.stdout
    header_pattern = re.compile(r'^(#+\s+.*)$', re.MULTILINE)
    sections = []
    last_end = 0
    current_header = "Frontmatter"
    
    for match in header_pattern.finditer(text):
        content = text[last_end:match.start()].strip()
        if content or last_end == 0:
            sections.append({"page_number": slugify(current_header), "title": current_header, "text": content})
        current_header = match.group(1).strip("# ").strip()
        last_end = match.end()
    
    content = text[last_end:].strip()
    if content:
        sections.append({"page_number": slugify(current_header), "title": current_header, "text": content})
        
    return [
        {
            "page_number": s["page_number"],
            "section_title": s["title"],
            "char_count": len(s["text"]),
            "preview": page_preview(s["text"]),
            "text": s["text"]
        } for s in sections
    ]


def should_process(doc_id_filters: list[str], doc_id: str) -> bool:
    return not doc_id_filters or doc_id in doc_id_filters


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    payload = load_json(args.catalog or context.catalog_path)
    ensure_directory(args.extract_dir or context.extract_dir)

    stats = {"processed": 0, "skipped": 0, "duplicates_skipped": 0}

    for document in payload["documents"]:
        doc_id = document["doc_id"]
        if not should_process(args.doc_id, doc_id):
            continue

        paths = context.extraction_paths(doc_id)
        if document["source_class"] == "duplicate":
            stats["duplicates_skipped"] += 1
            if not paths["metadata"].exists():
                ensure_directory(paths["dir"])
                write_json(paths["metadata"], {"doc_id": doc_id, "status": "skipped_duplicate", "canonical_doc_id": document["canonical_doc_id"], "source_sha256": document["sha256"], "updated_at": utc_now_iso()})
            continue

        if paths["metadata"].exists() and not args.force:
            m = load_json(paths["metadata"])
            if m.get("source_sha256") == document["sha256"] and m.get("status") == "extracted":
                stats["skipped"] += 1
                continue

        ensure_directory(paths["dir"])
        source_path = Path(document["path"])
        if not source_path.is_absolute():
            source_path = context.root / source_path

        ext = source_path.suffix.lower()
        pages, text, flags = [], "", []

        if ext == ".pdf":
            text = extract_pdf_text(str(source_path))
            raw_pages = [p for p in text.split("\f") if p.strip() or p == text.split("\f")[0]]
            if len(raw_pages) > 0 and (sum(len(p) for p in raw_pages) / len(raw_pages)) < 50:
                ocr_results = run_ocr(source_path)
                if ocr_results:
                    raw_pages, text = ocr_results, "\f".join(ocr_results)
                    flags.append("ocr_extracted")
            for i, p_text in enumerate(raw_pages, start=1):
                pages.append({"page_number": i, "char_count": len(p_text), "preview": page_preview(p_text), "text": p_text})
        else:
            pages = extract_non_pdf_sections(source_path)
            text = "\n\n".join([p["text"] for p in pages])
            flags.append("section_chunked")

        paths["full_text"].write_text(text, encoding="utf-8")
        write_json(paths["pages"], {"doc_id": doc_id, "pages": pages})

        if not text.strip() and "ocr_extracted" not in flags:
            flags.append("empty_text")

        write_json(paths["metadata"], {
            "doc_id": doc_id, "status": "extracted", "source_sha256": document["sha256"],
            "source_path": document["path"], "page_count": len(pages),
            "source_page_count": document.get("page_count"), "text_bytes": len(text.encode("utf-8")),
            "quality_flags": flags, "updated_at": utc_now_iso()
        })
        stats["processed"] += 1

    print(f"processed={stats['processed']} skipped={stats['skipped']} duplicates_skipped={stats['duplicates_skipped']}")


if __name__ == "__main__":
    main()
