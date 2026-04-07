#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, load_json


BIBTEX_ESCAPE_RE = re.compile(r'([\\{}$&#%_^~])')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the KB catalog to a BibTeX (.bib) file for Zotero sync.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for the .bib file. Defaults to <kb-root>/artifacts/compile/library.bib",
    )
    return parser.parse_args()


def escape_bibtex_value(value: Any) -> str:
    """Escape characters that would otherwise break BibTeX field values."""
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "%": r"\%",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    text = str(value)
    return BIBTEX_ESCAPE_RE.sub(lambda match: replacements[match.group(1)], text)


def should_export_doc(doc: dict[str, Any]) -> bool:
    """Limit export to intentionally citeable records."""
    if not doc.get("title") or not doc.get("year"):
        return False
    if doc.get("zotero_include") or doc.get("export_bibtex"):
        return True
    return bool(doc.get("doi") or doc.get("isbn"))


def format_authors_bibtex(author_string: str) -> str:
    """Convert 'First Last; First Last' to 'Last, First and Last, First'."""
    if not author_string:
        return "Unknown"

    authors = [a.strip() for a in author_string.split(";") if a.strip()]
    formatted_authors = []

    for author in authors:
        compact = " ".join(author.split())
        if "," in compact:
            parts = [part.strip() for part in compact.split(",") if part.strip()]
            if len(parts) >= 2:
                family = parts[0]
                given = " ".join(parts[1:])
                formatted_authors.append(f"{family}, {given}")
                continue
        parts = compact.split(" ")
        if len(parts) > 1:
            family = parts[-1]
            given = " ".join(parts[:-1])
            formatted_authors.append(f"{family}, {given}")
            continue
        formatted_authors.append(compact)

    return " and ".join(formatted_authors)


def generate_bibtex_entry(doc: dict[str, Any]) -> str | None:
    """Generate a BibTeX string for a single catalog document."""

    if not should_export_doc(doc):
        return None

    doc_id = doc["doc_id"]
    title = escape_bibtex_value(doc.get("title", ""))
    author = escape_bibtex_value(format_authors_bibtex(doc.get("author", "")))
    year = doc.get("year", "")

    doi = doc.get("doi")
    isbn = doc.get("isbn")
    journal = doc.get("journal")
    publisher = doc.get("publisher") or doc.get("producer")

    # Determine type
    entry_type = "misc"
    if doi and journal:
        entry_type = "article"
    elif isbn or (doc.get("source_class") == "book"):
        entry_type = "book"
    elif doi:
        entry_type = "article"

    lines = [f"@{entry_type}{{{doc_id},"]
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  author = {{{author}}},")
    lines.append(f"  year = {{{year}}},")

    if journal:
        lines.append(f"  journal = {{{escape_bibtex_value(journal)}}},")
    if publisher:
        lines.append(f"  publisher = {{{escape_bibtex_value(publisher)}}},")
    if doi:
        lines.append(f"  doi = {{{escape_bibtex_value(doi)}}},")
    if isbn:
        lines.append(f"  isbn = {{{escape_bibtex_value(isbn)}}},")

    # Link the physical file. Better BibTeX can resolve this if Zotero's 
    # "Linked Attachment Base Directory" is set to the KB root.
    file_path = doc.get("path")
    if file_path:
        lines.append(f"  file = {{{escape_bibtex_value(file_path)}}},")

    lines.append("}")

    return "\n".join(lines)


def collect_bibtex_entries(documents: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for doc in sorted(documents, key=lambda item: item.get("doc_id", "")):
        if doc.get("source_class") == "duplicate" or doc.get("is_redundant") or doc.get("status") == "rejected":
            continue
        entry = generate_bibtex_entry(doc)
        if entry:
            entries.append(entry)
    return entries


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    
    output_path = args.output or (context.root / "artifacts" / "compile" / "library.bib")

    if not context.catalog_path.exists():
        print(f"Error: Catalog not found at {context.catalog_path}. Run llmkb-add first.")
        return

    catalog = load_json(context.catalog_path)
    documents = catalog.get("documents", [])

    print(f"Exporting library to BibTeX...")

    bibtex_entries = collect_bibtex_entries(documents)

    if not bibtex_entries:
        print("Warning: No citeable documents found for BibTeX export.")
        return

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the complete .bib file
    output_path.write_text("\n\n".join(bibtex_entries) + "\n", encoding="utf-8")

    print(f"Successfully generated {len(bibtex_entries)} BibTeX entries.")
    print(f"File saved to: {output_path}")
    print("You can now import this file into Zotero or another BibTeX-compatible reference manager.")


if __name__ == "__main__":
    main()
