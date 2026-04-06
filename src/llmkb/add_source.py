#!/usr/bin/env python3
"""Metadata extraction and indexing engine for the LLM Knowledge Base.

This script scans a directory for PDF files, extracts their metadata (Title, Author, DOI, ISBN, etc.),
and compiles them into a canonical 'sources.json' manifest.

The '--overrides' Option:
-------------------------
The engine uses automated heuristics and API queries to guess document metadata. If it guesses 
incorrectly (e.g., misclassifying a book as a paper or corrupting a title), you can provide a 
manual 'source_overrides.json' file. 

This file acts as a permanent correction layer. At the end of every catalog pass, the engine 
checks the overrides file and applies your manual corrections to the machine-generated data 
before writing the final manifest. This ensures your corrections are preserved across rebuilds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, extract_doi, extract_isbn, slugify, normalize_author_string
from llmkb.metadata_resolver import resolve_doi, resolve_isbn


SOURCE_CLASSES = [
    "book",
    "paper",
    "notes",
    "manual",
    "solution_manual",
    "excerpt",
    "duplicate",
    "reference",
    "unknown",
]

PDFINFO_FIELD_RE = re.compile(r"^([^:]+):\s*(.*)$")
YEAR_PREFIX_RE = re.compile(r"^(?P<year>\d{4})-(?P<slug>.+)$")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".docx", ".md", ".txt", ".rst", ".html", ".htm"}

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the metadata extraction and indexing script.

    The most important arguments are:
    - --kb-root: The base directory of your knowledge base.
    - --overrides: Path to a JSON file containing manual metadata corrections. This file 
      acts as a final correction layer applied at the end of the cataloging process.

    Returns:
        argparse.Namespace: The parsed arguments including paths and flags.
    """

    parser = argparse.ArgumentParser(
        description="Scan raw files (PDF, ePub, Word, MD, etc.), extract metadata, and create a master JSON index (sources.json)."
    )
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="Directory containing source documents. Defaults to <kb-root>/raw",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write the catalog JSON. Defaults to <kb-root>/artifacts/catalog/sources.json",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="Optional JSON file with per-document metadata overrides. Defaults to <kb-root>/config/source_overrides.json",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Optional: Scan the raw directory recursively (including all subdirectories). Defaults to false.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        action="append",
        default=[],
        help="Optional: Path to specific file(s) to process. You can provide multiple --file options to process multiple files. If provided, skips the full directory scan.",
    )
    parser.add_argument(
        "--probe-text",
        action="store_true",
        help="Measure extracted text byte counts using pdftotext.",
    )
    return parser.parse_args()


def run_command(args: list[str]) -> str:
    """Execute a shell command and return its standard output.
    
    Args:
        args: A list of string arguments forming the command to execute.
    
    Returns:
        str: The standard output of the command.
    """
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def compute_sha256(path: Path) -> str:
    """Compute the SHA-256 hash of a file.
    
    Args:
        path: The Path to the file.
    
    Returns:
        str: The hexadecimal representation of the SHA-256 hash.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """Load manual metadata overrides from a JSON file.
    
    Args:
        path: The Path to the JSON overrides file.
    
    Returns:
        dict: A dictionary mapping doc_ids to their override properties.
    """
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    overrides = payload.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("config/source_overrides.json must contain an object at overrides")
    return overrides


def parse_pdfinfo(path: Path) -> dict[str, str]:
    """Extract metadata from a PDF using the 'pdfinfo' utility.
    
    Args:
        path: The Path to the PDF file.
    
    Returns:
        dict: A dictionary of metadata key-value pairs (e.g., Title, Author, Pages).
    """
    metadata: dict[str, str] = {}
    if path.suffix.lower() != ".pdf":
        return metadata
    
    try:
        output = run_command(["pdfinfo", str(path)])
    except Exception:
        return metadata
    for line in output.splitlines():
        match = PDFINFO_FIELD_RE.match(line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            metadata[key] = value
    return metadata



def run_micro_ocr(pdf_path: Path) -> str:
    """Perform OCR on ONLY the first page of a PDF to find identifiers."""
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return ""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Convert ONLY page 1 to image
        subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", "-r", "300", str(pdf_path), str(tmp_path / "title")],
            capture_output=True, check=False
        )
        img_files = list(tmp_path.glob("*.png"))
        if not img_files:
            return ""
            
        result = subprocess.run(
            ["tesseract", str(img_files[0]), "stdout"],
            capture_output=True, text=True, check=False
        )
        return result.stdout if result.returncode == 0 else ""


def extract_identifiers(path: Path) -> tuple[str | None, str | None]:
    """Skim the beginning of a document to extract DOI and ISBN identifiers.
    
    Args:
        path: The Path to the document.
    
    Returns:
        tuple: A tuple containing (doi, isbn) where either or both may be None.
    """
    ext = path.suffix.lower()
    text = ""
    if ext == ".pdf":
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "5", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            text = result.stdout
            
        # If text is empty/useless, trigger Micro-OCR on the title page
        if len(text.strip()) < 50:
            print(f"  Identifier check: No text layer found in {path.name}. Running Micro-OCR...")
            text = run_micro_ocr(path)
    elif ext in {".epub", ".docx"}:
        # Use pandoc to quickly dump plain text
        result = subprocess.run(
            ["pandoc", str(path), "-t", "plain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            text = result.stdout[:15000]
    elif ext in {".md", ".txt", ".rst", ".html", ".htm"}:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:15000]
        except Exception:
            pass

    return extract_doi(text), extract_isbn(text)


def probe_text_bytes(path: Path) -> int | None:
    """Measure the byte size of the extracted text.
    
    Args:
        path: The Path to the document.
    
    Returns:
        int | None: The byte length of the extracted text, or None if extraction failed.
    """
    ext = path.suffix.lower()
    if ext == ".pdf":
        result = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True,
            text=False,
            check=False,
        )
        if result.returncode != 0:
            return None
        return len(result.stdout)
    elif ext in {".md", ".txt", ".rst", ".html", ".htm"}:
        try:
            return len(path.read_bytes())
        except Exception:
            return None
    else:
        # ePub/Word: Just return file size as a rough heuristic for now
        try:
            return path.stat().st_size
        except Exception:
            return None


def infer_doc_id(path: Path) -> tuple[str, int | None]:
    """Infer a document ID and publication year from a file path.
    
    Args:
        path: The Path to the file.
    
    Returns:
        tuple: A tuple containing the inferred doc_id slug and the year (or None).
    """
    stem = path.stem
    match = YEAR_PREFIX_RE.match(stem)
    if not match:
        return slugify(stem), None
    year = int(match.group("year"))
    return slugify(stem), year


def choose_canonical(entries: list[dict[str, Any]]) -> str:
    """Select the best canonical document ID from a list of duplicate entries.
    
    Args:
        entries: A list of catalog entry dictionaries representing duplicates.
    
    Returns:
        str: The doc_id chosen as canonical based on filename heuristics.
    """
    def score(entry: dict[str, Any]) -> tuple[int, int, int, str]:
        filename = entry["filename"].lower()
        penalties = 0
        for token in ("duplicate", "copy", "scratch", "tmp", "untitled"):
            if token in filename:
                penalties += 1
        if filename.endswith("2.pdf"):
            penalties += 1
        year_rank = entry.get("year") or 0
        length_rank = len(filename)
        return (penalties, -year_rank, length_rank, filename)

    return min(entries, key=score)["doc_id"]


def infer_source_class(entry: dict[str, Any]) -> str:
    """Infer the source class (e.g., book, paper, manual) using metadata and page counts.
    
    Args:
        entry: The catalog entry dictionary.
    
    Returns:
        str: The inferred source class label.
    """
    filename = entry["filename"].lower()
    title = (entry.get("title") or "").lower()
    pages = entry.get("page_count") or 0

    if any(token in filename or token in title for token in ("solution", "booksol")):
        return "solution_manual"
    if any(token in filename or token in title for token in ("manual", "handbook", "guide")):
        return "manual"
    if any(token in filename or token in title for token in ("notes", "lecture", "tutorial")):
        return "notes"
    if any(token in filename or token in title for token in ("excerpt", "preview", "sample")):
        return "excerpt"
    if any(token in filename or token in title for token in ("encyclopedia", "reference")):
        return "reference"
    if pages >= 150:
        return "book"
    if 1 <= pages <= 80:
        return "paper"
    if 81 <= pages <= 149:
        return "reference"
    return "unknown"


def apply_override(entry: dict[str, Any], override: dict[str, Any]) -> None:
    """Apply manual overrides to a catalog entry in place.
    
    Args:
        entry: The catalog entry to modify.
        override: A dictionary of key-value pairs to override in the entry.
    """
    for key, value in override.items():
        entry[key] = value


def generate_canonical_filename(entry: dict[str, Any], original_ext: str) -> str:
    """Generate a canonical, strictly lowercase, dash-separated filename.
    
    Format: yyyy-author(s)-short-title<ext>
    """
    year = entry.get("year")
    title = entry.get("title") or ""
    author_str = entry.get("author") or ""
    
    author_part = ""
    if author_str:
        authors = [a.strip() for a in author_str.split(";") if a.strip()]
        
        def get_last_name(person_str: str) -> str:
            if "," in person_str:
                return person_str.split(",")[0].strip()
            return person_str.split(" ")[-1].strip()
            
        if len(authors) == 1:
            author_part = get_last_name(authors[0])
        elif len(authors) == 2:
            author_part = f"{get_last_name(authors[0])}-{get_last_name(authors[1])}"
        elif len(authors) >= 3:
            author_part = f"{get_last_name(authors[0])}-etal"
            
    # Take first 4 meaningful words of title
    title_words = [w for w in re.split(r'\W+', title) if w.lower() not in {"a", "an", "the", "in", "on", "of", "and"}]
    short_title = " ".join(title_words[:4])
    
    parts = []
    if year:
        parts.append(str(year))
    if author_part:
        parts.append(author_part)
    if short_title:
        parts.append(short_title)
        
    # If we have NO metadata (no authors and no title), 
    # use the original filename stem (doc_id) as the description.
    if not author_part and not short_title:
        fallback = entry.get("doc_id", "untitled")
        # If the fallback starts with the year we already added, strip it
        if year and fallback.startswith(str(year)):
            fallback = fallback[len(str(year)):].lstrip("-_ ")
        if fallback:
            parts.append(fallback)
        
    if not parts:
        return "untitled-document" + original_ext
        
    raw_name = "-".join(parts)
    # Final safety: deduplicate adjacent identical slugs (e.g. 1965-1965)
    slug = slugify(raw_name)
    slug_parts = slug.split("-")
    deduped = []
    for p in slug_parts:
        if not deduped or p != deduped[-1]:
            deduped.append(p)
            
    return "-".join(deduped) + original_ext


def process_incoming_file(entry: dict[str, Any], original_path: Path, kb_root: Path, existing_hashes: set[str]) -> Path:
    """Move a file from raw/incoming to raw/library using a canonical filename.

    Args:
        entry: The catalog entry containing metadata.
        original_path: The current path of the file.
        kb_root: The root of the knowledge base.
        existing_hashes: A set of SHA-256 hashes already present in the library.

    Returns:
        Path: The new path to the file.
    """
    if "incoming" not in original_path.parts:
        return original_path

    # 1. Duplicate Rejection (Phase 0.1)
    file_hash = entry["sha256"]
    if file_hash in existing_hashes:
        rejected_dir = kb_root / "raw" / "rejected" / "duplicates"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        new_path = rejected_dir / original_path.name

        # Handle collisions in the rejected folder
        counter = 1
        while new_path.exists():
            new_path = rejected_dir / f"{original_path.stem}-{counter}{original_path.suffix}"
            counter += 1

        print(f"Warning: Duplicate detected. Moving '{original_path.name}' -> 'rejected/duplicates/'")
        original_path.rename(new_path)

        # Mark entry as redundant for downstream cleanup if necessary
        entry["is_duplicate_rejected"] = True
        return new_path

    # 2. Normal Ingestion
    library_dir = kb_root / "raw" / "library"
    library_dir.mkdir(parents=True, exist_ok=True)
    original_ext = original_path.suffix.lower()
    canonical_name = generate_canonical_filename(entry, original_ext)
    new_path = library_dir / canonical_name
    
    # Handle collisions in the filesystem
    counter = 1
    while new_path.exists() and new_path != original_path:
        if original_ext:
            new_name = canonical_name.replace(original_ext, f"-{counter}{original_ext}")
        else:
            new_name = f"{canonical_name}-{counter}"
        new_path = library_dir / new_name
        counter += 1
        
    print(f"Ingesting: Moving '{original_path.name}' -> 'library/{new_path.name}'")
    original_path.rename(new_path)
    
    try:
        entry["path"] = str(new_path.relative_to(kb_root))
    except ValueError:
        entry["path"] = str(new_path)
        
    entry["filename"] = new_path.name
    return new_path


def build_entry(path: Path, kb_root: Path, probe_text: bool, existing_hashes: set[str]) -> dict[str, Any]:
    """Build a complete catalog entry dictionary for a single PDF file.
    
    Args:
        path: The Path to the PDF file.
        kb_root: The root Path of the knowledge base (for calculating relative paths).
        probe_text: Boolean indicating whether to probe text bytes.
        existing_hashes: A set of SHA-256 hashes already present in the library.
    
    Returns:
        dict: The fully constructed catalog entry, including resolved API metadata.
    """
    pdfinfo = parse_pdfinfo(path)
    doc_id, year = infer_doc_id(path)
    
    # Store path relative to kb_root if possible
    try:
        display_path = str(path.relative_to(kb_root))
    except ValueError:
        display_path = str(path)

    page_count = None
    if pdfinfo.get("Pages"):
        try:
            page_count = int(pdfinfo["Pages"])
        except ValueError:
            page_count = None

    sha256 = compute_sha256(path)
    doi, isbn = extract_identifiers(path)
    metadata_source = "heuristic"
    resolved_meta = None

    if doi:
        resolved_meta = resolve_doi(doi)
    if not resolved_meta and isbn:
        resolved_meta = resolve_isbn(isbn)

    if resolved_meta:
        metadata_source = resolved_meta.get("metadata_source", metadata_source)
        title = resolved_meta.get("title") or pdfinfo.get("Title") or None
        author = resolved_meta.get("author") or pdfinfo.get("Author") or None
        year = resolved_meta.get("year") or year
        publisher = resolved_meta.get("publisher") or pdfinfo.get("Producer") or None
    else:
        title = pdfinfo.get("Title") or None
        author = pdfinfo.get("Author") or None
        publisher = pdfinfo.get("Producer") or None

    author = normalize_author_string(author)

    entry: dict[str, Any] = {
        "doc_id": doc_id,
        "filename": path.name,
        "path": display_path,
        "year": year,
        "sha256": sha256,
        "size_bytes": path.stat().st_size,
        "page_count": page_count,
        "title": title,
        "author": author,
        "doi": doi,
        "isbn": isbn,
        "metadata_source": metadata_source,
        "producer": publisher,
        "source_class": "unknown",
        "canonical_doc_id": doc_id,
        "relationship": None,
        "wiki_link": f"[[source/{doc_id}]]",
        "notes": None,
    }
    
    # Perform Managed Ingestion (Rename and Move)
    new_path = process_incoming_file(entry, path, kb_root, existing_hashes)
    if entry.get("is_duplicate_rejected"):
        # If rejected, don't return a full entry to the main catalog loop
        return entry

    # The doc_id should ideally match the new canonical filename stem to prevent future renaming chaos
    if new_path != path:
        new_doc_id = new_path.stem
        entry["doc_id"] = new_doc_id
        entry["canonical_doc_id"] = new_doc_id
        entry["wiki_link"] = f"[[source/{new_doc_id}]]"
    
    if probe_text:
        entry["text_bytes"] = probe_text_bytes(new_path)
    entry["source_class"] = infer_source_class(entry)
    return entry


def assign_duplicates(entries: list[dict[str, Any]]) -> None:
    """Identify exact duplicates by SHA-256 hash and assign canonical relationships in place.
    
    Args:
        entries: A list of catalog entry dictionaries.
    """
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_hash.setdefault(entry["sha256"], []).append(entry)

    for group in by_hash.values():
        if len(group) == 1:
            continue
        canonical_doc_id = choose_canonical(group)
        for entry in group:
            entry["canonical_doc_id"] = canonical_doc_id
            if entry["doc_id"] != canonical_doc_id:
                entry["source_class"] = "duplicate"
                entry["relationship"] = {
                    "kind": "exact_duplicate_of",
                    "target_doc_id": canonical_doc_id,
                }


def finalize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile the final catalog payload, aggregating statistics and sorting entries.
    
    Args:
        entries: A list of fully processed catalog entry dictionaries.
    
    Returns:
        dict: The final catalog payload ready to be written to JSON.
    """
    counts: dict[str, int] = {name: 0 for name in SOURCE_CLASSES}
    duplicate_groups = 0
    hashes_seen: dict[str, int] = {}

    for entry in entries:
        counts.setdefault(entry["source_class"], 0)
        counts[entry["source_class"]] += 1
        hashes_seen[entry["sha256"]] = hashes_seen.get(entry["sha256"], 0) + 1

    duplicate_groups = sum(1 for group_size in hashes_seen.values() if group_size > 1)

    return {
        "schema_version": 1,
        "source_classes": SOURCE_CLASSES,
        "stats": {
            "document_count": len(entries),
            "duplicate_group_count": duplicate_groups,
            "class_counts": counts,
        },
        "documents": sorted(entries, key=lambda item: item["doc_id"]),
    }


def ensure_unique_doc_ids(entries: list[dict[str, Any]]) -> None:
    """Detect and resolve doc_id collisions by appending numeric suffixes in place.
    
    Args:
        entries: A list of catalog entry dictionaries.
    """
    seen_ids: dict[str, int] = {}
    for entry in entries:
        base_id = entry["doc_id"]
        if base_id not in seen_ids:
            seen_ids[base_id] = 1
            continue
        
        # Collision detected
        seen_ids[base_id] += 1
        new_id = f"{base_id}-{seen_ids[base_id]}"
        print(f"Warning: doc_id collision for '{base_id}'. Renaming '{entry['path']}' to '{new_id}' in catalog.")
        entry["doc_id"] = new_id
        entry["canonical_doc_id"] = new_id
        entry["wiki_link"] = f"[[source/{new_id}]]"


def main() -> None:
    """Main entry point for the metadata extraction and indexing script.
    
    This function scans the knowledge base for raw PDF files, extracts their metadata 
    (such as titles, authors, DOIs, and ISBNs), queries external APIs for accurate bibliographic 
    data, detects duplicate files, and compiles a master manifest file ('sources.json'). 
    This manifest serves as the foundational inventory for all downstream processing.
    """
    args = parse_args()
    context = KBContext(args.kb_root)
    raw_dir = args.raw_dir or context.path("raw")
    output_path = args.output or context.catalog_path
    overrides_path = args.overrides or context.overrides_path
    overrides = load_overrides(overrides_path)

    existing_catalog = {}
    existing_hashes = set()
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_text())
            for doc in payload.get("documents", []):
                existing_catalog[doc["path"]] = doc
                existing_hashes.add(doc["sha256"])
        except json.JSONDecodeError:
            pass

    pdf_paths = args.file
    if not pdf_paths:
        file_iterator = raw_dir.rglob("*") if args.recursive else raw_dir.glob("*")
        pdf_paths = sorted(
            [p for p in file_iterator 
             if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS 
             and "rejected" not in p.parts]
        )
    
    entries = []
    processed_paths = set()
    
    for path in pdf_paths:
        # Resolve absolute path to ensure accurate collision detection
        path = path.resolve()
        processed_paths.add(path)
        try:
            display_path = str(path.relative_to(context.root))
        except ValueError:
            display_path = str(path)
            
        if display_path in existing_catalog:
            entry = existing_catalog[display_path]
            if path.stat().st_size == entry.get("size_bytes"):
                entries.append(entry)
                continue

        entry = build_entry(path, context.root, args.probe_text, existing_hashes)
        if not entry.get("is_duplicate_rejected"):
            entries.append(entry)
            # Add to set so subsequent files in this same run are also rejected
            existing_hashes.add(entry["sha256"])
        
    # If we only processed specific files, we must preserve the rest of the existing catalog
    if args.file and output_path.exists():
        for existing_path, entry in existing_catalog.items():
            # If the entry wasn't just explicitly processed, keep it
            absolute_existing = (context.root / existing_path).resolve()
            if absolute_existing not in processed_paths:
                entries.append(entry)
    
    ensure_unique_doc_ids(entries)
    assign_duplicates(entries)

    for entry in entries:
        override = overrides.get(entry["doc_id"])
        if override:
            apply_override(entry, override)

    payload = finalize(entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


if __name__ == "__main__":
    main()
