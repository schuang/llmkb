#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path

from llmkb.kb_common import (
    KBContext,
    ensure_directory,
    load_json,
    page_preview,
    utc_now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract per-page text from cataloged PDFs.")
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
    """Perform OCR on a PDF by converting pages to images and running Tesseract.
    
    Returns:
        list[str]: A list of strings, one for each page.
    """
    if not shutil.which("tesseract"):
        print("Warning: 'tesseract' not found in PATH. Skipping OCR.")
        return []
    if not shutil.which("pdftoppm"):
        print("Warning: 'pdftoppm' not found in PATH. Skipping OCR.")
        return []

    pages = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Convert PDF to high-res PNGs
        print(f"OCR: Converting {pdf_path.name} to images...")
        subprocess.run(
            ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(tmp_path / "page")],
            check=True
        )
        
        # Sort images numerically
        img_files = sorted(tmp_path.glob("*.png"), key=lambda x: x.name)
        
        for i, img in enumerate(img_files, start=1):
            print(f"OCR: Processing page {i}/{len(img_files)}...", end="\r")
            result = subprocess.run(
                ["tesseract", str(img), "stdout"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                pages.append(result.stdout)
            else:
                pages.append("")
        print() # New line after the progress carriage return
    return pages


def should_process(doc_id_filters: list[str], doc_id: str) -> bool:
    if not doc_id_filters:
        return True
    return doc_id in doc_id_filters


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    catalog_path = args.catalog or context.catalog_path
    extract_dir = args.extract_dir or context.extract_dir

    ensure_directory(extract_dir)
    payload = load_json(catalog_path)
    documents = payload["documents"]

    stats = {
        "processed": 0,
        "skipped": 0,
        "duplicates_skipped": 0,
    }

    for document in documents:
        doc_id = document["doc_id"]
        if not should_process(args.doc_id, doc_id):
            continue

        paths = context.extraction_paths(doc_id)
        metadata_path = paths["metadata"]

        if document["source_class"] == "duplicate":
            stats["duplicates_skipped"] += 1
            if not metadata_path.exists():
                ensure_directory(paths["dir"])
                write_json(
                    metadata_path,
                    {
                        "doc_id": doc_id,
                        "status": "skipped_duplicate",
                        "canonical_doc_id": document["canonical_doc_id"],
                        "source_sha256": document["sha256"],
                        "updated_at": utc_now_iso(),
                    },
                )
            continue

        if metadata_path.exists() and not args.force:
            metadata = load_json(metadata_path)
            if metadata.get("source_sha256") == document["sha256"] and metadata.get("status") == "extracted":
                stats["skipped"] += 1
                continue

        ensure_directory(paths["dir"])
        pdf_path = Path(document["path"])
        # If kb_root is not CWD, ensure path is absolute
        if not pdf_path.is_absolute():
            pdf_path = context.root / pdf_path

        text = extract_pdf_text(str(pdf_path))
        raw_pages = text.split("\f")
        if raw_pages and not raw_pages[-1].strip():
            raw_pages = raw_pages[:-1]

        # Detection: If text density is extremely low, it is likely a scanned image
        use_ocr = False
        if len(raw_pages) > 0:
            avg_chars = sum(len(p) for p in raw_pages) / len(raw_pages)
            if avg_chars < 50:
                use_ocr = True

        flags = []
        if use_ocr:
            ocr_results = run_ocr(pdf_path)
            if ocr_results:
                raw_pages = ocr_results
                text = "\f".join(raw_pages)
                flags.append("ocr_extracted")

        pages = []
        for index, page_text in enumerate(raw_pages, start=1):
            pages.append(
                {
                    "page_number": index,
                    "char_count": len(page_text),
                    "preview": page_preview(page_text),
                    "text": page_text,
                }
            )

        paths["full_text"].write_text(text)
        write_json(paths["pages"], {"doc_id": doc_id, "pages": pages})

        if not text.strip() and "ocr_extracted" not in flags:
            flags.append("empty_text")
        if document.get("page_count") and document["page_count"] != len(pages):
            flags.append("page_count_mismatch")
        if pages and sum(page["char_count"] for page in pages) / max(len(pages), 1) < 80:
            flags.append("low_text_density")

        write_json(
            metadata_path,
            {
                "doc_id": doc_id,
                "status": "extracted",
                "source_sha256": document["sha256"],
                "source_path": document["path"],
                "page_count": len(pages),
                "pdf_page_count": document.get("page_count"),
                "text_bytes": len(text.encode("utf-8")),
                "quality_flags": flags,
                "updated_at": utc_now_iso(),
            },
        )
        stats["processed"] += 1

    print(
        f"processed={stats['processed']} skipped={stats['skipped']} duplicates_skipped={stats['duplicates_skipped']}"
    )


if __name__ == "__main__":
    main()
