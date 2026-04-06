#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, load_json


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


def format_authors_bibtex(author_string: str) -> str:
    """Convert 'First Last; First Last' to 'Last, First and Last, First'."""
    if not author_string:
        return "Unknown"
    
    authors = [a.strip() for a in author_string.split(";")]
    formatted_authors = []
    
    for author in authors:
        parts = author.split(" ")
        if len(parts) > 1:
            # Assume last word is family name
            family = parts[-1]
            given = " ".join(parts[:-1])
            formatted_authors.append(f"{family}, {given}")
        else:
            formatted_authors.append(author)
            
    return " and ".join(formatted_authors)


def generate_bibtex_entry(doc: dict[str, Any]) -> str | None:
    """Generate a BibTeX string for a single catalog document."""
    
    # 1. Validation (Track C Exclusion)
    # We only export formal documents with enough metadata to be useful in a bibliography.
    # If the user really wants an informal document exported, they can manually add a "doi" or "isbn" override.
    if not doc.get("title") or not doc.get("year"):
        return None
        
    doc_id = doc["doc_id"]
    title = doc.get("title", "")
    author = format_authors_bibtex(doc.get("author", ""))
    year = doc.get("year", "")
    
    doi = doc.get("doi")
    isbn = doc.get("isbn")
    journal = doc.get("journal")
    publisher = doc.get("producer") or doc.get("publisher")
    
    # Determine type
    entry_type = "misc"
    if doi and journal:
        entry_type = "article"
    elif isbn or (doc.get("source_class") == "book"):
        entry_type = "book"
    elif doi:
        entry_type = "article" # Fallback for DOIs without journals (like preprints)
        
    lines = [f"@{entry_type}{{{doc_id},"]
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  author = {{{author}}},")
    lines.append(f"  year = {{{year}}},")
    
    if journal:
        lines.append(f"  journal = {{{journal}}},")
    if publisher:
        lines.append(f"  publisher = {{{publisher}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if isbn:
        lines.append(f"  isbn = {{{isbn}}},")
        
    # We also inject a special field pointing back to our local KB wiki note!
    # This allows Zotero to link directly to your LLM summaries.
    lines.append(f"  note = {{LLMKB: [[source/{doc_id}]]}},")
    lines.append("}")
    
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    
    output_path = args.output or (context.root / "artifacts" / "compile" / "library.bib")
    
    if not context.catalog_path.exists():
        print(f"Error: Catalog not found at {context.catalog_path}. Run llmkb-catalog first.")
        return
        
    catalog = load_json(context.catalog_path)
    documents = catalog.get("documents", [])
    
    bibtex_entries = []
    
    print(f"Exporting library to BibTeX...")
    
    for doc in documents:
        # Skip duplicates and rejected files
        if doc.get("source_class") == "duplicate" or doc.get("is_redundant") or doc.get("status") == "rejected":
            continue
            
        entry = generate_bibtex_entry(doc)
        if entry:
            bibtex_entries.append(entry)
            
    if not bibtex_entries:
        print("Warning: No suitable documents found for BibTeX export (missing required metadata).")
        return
        
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the complete .bib file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(bibtex_entries))
        f.write("\n")
        
    print(f"Successfully generated {len(bibtex_entries)} BibTeX entries.")
    print(f"File saved to: {output_path}")
    print("You can now point Zotero (via Better BibTeX plugin) to sync with this file!")


if __name__ == "__main__":
    main()
