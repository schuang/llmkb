#!/usr/bin/env python3

from __future__ import annotations

import argparse

try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

from llmkb.kb_common import (
    KBContext,
    compile_book_chapters,
    ensure_directory,
    extract_keywords,
    load_json,
    page_preview,
    render_frontmatter,
    score_text,
    summarize_pages,
    utc_now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate wiki source pages and a search index.")
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
        help="Directory containing extracted text. Defaults to <kb-root>/artifacts/extract",
    )
    parser.add_argument(
        "--resolution",
        type=Path,
        help="Path to the resolution JSON. Defaults to <kb-root>/artifacts/compile/source_resolution.json",
    )
    parser.add_argument(
        "--wiki-source-dir",
        type=Path,
        help="Directory to write wiki source pages. Defaults to <kb-root>/wiki/source",
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        help="Path to write the search index. Defaults to <kb-root>/artifacts/compile/search_index.json",
    )
    parser.add_argument(
        "--chapter-output",
        type=Path,
        help="Path to write the chapter index. Defaults to <kb-root>/artifacts/compile/chapter_index.json",
    )
    parser.add_argument(
        "--state-output",
        type=Path,
        help="Path to write the state JSON. Defaults to <kb-root>/artifacts/compile/source_pages_state.json",
    )
    parser.add_argument("--doc-id", action="append", default=[], help="Limit build to selected doc_ids.")
    parser.add_argument("--summarize-books", action="store_true", help="Enable expensive LLM-powered chapter-by-chapter book summarization.")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gemini/gemini-2.5-flash"), help="LiteLLM model string.")
    parser.add_argument("--force", action="store_true", help="Regenerate all selected source pages.")
    return parser.parse_args()




def summarize_chapter_with_llm(title: str, chapter_title: str, text_chunk: str, model: str) -> str:
    """Summarize a single chapter using LLM."""
    prompt = f"""
You are an expert academic research assistant. 
Read the following excerpt from a chapter titled "{chapter_title}" from the book "{title}".

Write a single, highly concise sentence summarizing the core objective or finding of this specific chapter.
Do NOT use intro phrases. Just the fact.

CHAPTER TEXT:
================
{text_chunk}
================
"""
    try:
        from litellm import completion
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""

def summarize_book_map_reduce(title: str, chapters: list[dict[str, Any]], pages: list[dict[str, Any]], model: str) -> str:
    """Summarize a book by first summarizing its chapters (Map) and then combining them (Reduce)."""
    chapter_summaries = []
    
    print(f"    Map-Reduce: Summarizing {len(chapters)} chapters...")
    for i, chapter in enumerate(chapters):
        # Find pages for this chapter
        # chapters have page_start/page_end which might be ints or strings
        # For now, let's just grab the first page of the chapter
        start_page_val = chapter.get("page_start")
        chapter_pages = [p for p in pages if p["page_number"] == start_page_val]
        if not chapter_pages:
            continue
            
        text_chunk = chapter_pages[0].get("text", "")[:4000]
        if not text_chunk.strip():
            continue
            
        print(f"      Summarizing Chapter {chapter.get('chapter_number', i+1)}: {chapter.get('title')}...", end="\r")
        summary = summarize_chapter_with_llm(title, chapter.get("title", ""), text_chunk, model)
        if summary:
            chapter_summaries.append(f"Chapter {chapter.get('chapter_number', i+1)} ({chapter.get('title')}): {summary}")
    
    print("\n    Map-Reduce: Generating final book summary...")
    combined_chapters = "\n".join(chapter_summaries)
    
    prompt = f"""
You are an expert academic research assistant. 
Here are the summaries of the chapters of a book titled "{title}":

{combined_chapters}

Based on these chapter summaries, write a concise, high-level summary of the entire book (maximum 5 sentences).
Focus on the overall thesis, methodology, and target audience.
Do NOT use intro phrases. Just the facts.
"""
    try:
        from litellm import completion
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"      Warning: Map-Reduce final step failed: {e}")
        return "Book summary generation failed."


def summarize_with_llm(title: str, text_chunk: str, model: str) -> str:
    """Use an LLM to generate a concise, human-readable summary of the document."""
    if not LITELLM_AVAILABLE:
        return "LLM extraction skipped: litellm not installed."
        
    prompt = f"""
You are an expert academic research assistant. 
Read the following excerpt from the beginning of a document titled "{title}".

Write a single, highly concise paragraph (maximum 4 sentences) summarizing the core topic, methodology, or findings of the text. 
Focus only on high-signal academic information. Do NOT include phrases like "This document discusses" or "The text covers".
Just state the facts directly.

TEXT EXCERPT:
================
{text_chunk}
================
"""
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  Warning: LLM summarization failed: {e}")
        return "LLM summarization failed."


def should_process(doc_id_filters: list[str], doc_id: str) -> bool:
    if not doc_id_filters:
        return True
    return doc_id in doc_id_filters


def format_relationship(document: dict[str, Any]) -> list[str]:
    relationship = document.get("relationship")
    if not relationship:
        return []
    target = relationship.get("target_doc_id")
    kind = relationship.get("kind")
    if not target or not kind:
        return []
    return [f"{kind}: [[source/{target}]]"]


def resolved_document(document: dict[str, Any], resolution_payload: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(document)
    relationship = document.get("relationship") or {}
    base_kind = relationship.get("kind")
    resolutions = {item["doc_id"]: item for item in resolution_payload.get("documents", [])}
    resolution = resolutions.get(document["doc_id"])
    if not resolution:
        resolved["is_redundant"] = base_kind in {"exact_duplicate_of", "near_duplicate_of"} and (
            document["canonical_doc_id"] != document["doc_id"]
        )
        resolved["dedupe_kind"] = base_kind
        resolved["similarity"] = None
        return resolved
    resolved["canonical_doc_id"] = resolution.get("canonical_doc_id", document["canonical_doc_id"])
    if resolution.get("relationship"):
        resolved["relationship"] = resolution["relationship"]
    dedupe_kind = None
    if resolved.get("relationship"):
        dedupe_kind = resolved["relationship"].get("kind")
    resolved["dedupe_kind"] = dedupe_kind
    resolved["similarity"] = resolution.get("similarity")
    resolved["is_redundant"] = dedupe_kind in {"exact_duplicate_of", "near_duplicate_of"} and (
        resolved["canonical_doc_id"] != document["doc_id"]
    )
    return resolved


def redundancy_summary(document: dict[str, Any]) -> str:
    target = document["canonical_doc_id"]
    kind = document.get("dedupe_kind")
    if kind == "exact_duplicate_of":
        return f"Exact duplicate of [[source/{target}]]."
    if kind == "near_duplicate_of":
        similarity = document.get("similarity")
        if similarity is None:
            return f"Near-duplicate of [[source/{target}]]."
        return f"Near-duplicate of [[source/{target}]] (similarity={similarity})."
    raise ValueError(f"Unsupported redundancy kind: {kind}")


def stub_page(document: dict[str, Any]) -> str:
    title = document.get("title") or document["doc_id"]
    target = document["canonical_doc_id"]
    relationships = format_relationship(document)
    frontmatter = render_frontmatter(
        {
            "doc_id": document["doc_id"],
            "title": title,
            "source_class": document["source_class"],
            "canonical_doc_id": target,
            "keywords": [],
            "aliases": [document["filename"]],
            "related": relationships,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "## Status",
        "",
        redundancy_summary(document),
    ]
    if document.get("dedupe_kind") == "near_duplicate_of" and document.get("similarity") is not None:
        lines.extend(["", f"Detected near-duplicate similarity: `{document['similarity']}`"])
    return "\n".join(lines) + "\n"


def build_page(document: dict[str, Any], pages: list[dict[str, Any]], model: str = None, summarize_books: bool = False) -> tuple[str, dict[str, Any]]:
    title = document.get("title") or document["doc_id"]
    author = document.get("author")
    chapters = (
        compile_book_chapters(document["doc_id"], title, pages)
        if document.get("source_class") == "book"
        else []
    )
    
    summary = ""
    is_book = document.get("source_class") == "book"
    
    if is_book and summarize_books and model and LITELLM_AVAILABLE:
        summary = summarize_book_map_reduce(title, chapters, pages, model)
    elif not is_book and model and LITELLM_AVAILABLE:
        # Paper summary (first 10 pages)
        text_chunk = "\n".join([p.get("text", "") for p in pages[:10]])[:15000]
        if text_chunk.strip():
            print(f"  Summarizing paper '{document['doc_id']}' via LLM...")
            summary = summarize_with_llm(title, text_chunk, model)
        else:
            summary = "No text available to summarize."
    else:
        # Fallback to deterministic summary
        summary = summarize_pages(title, pages, source_class=document.get("source_class"))

    keywords = extract_keywords(title, author, pages, source_class=document.get("source_class"))
    relationships = format_relationship(document)

    top_previews = [
        {
            "page_number": page["page_number"],
            "preview": page_preview(page.get("text", "")),
        }
        for page in pages[: min(len(pages), 8)]
    ]

    frontmatter = render_frontmatter(
        {
            "doc_id": document["doc_id"],
            "title": title,
            "author": author,
            "year": document.get("year"),
            "source_class": document["source_class"],
            "canonical_doc_id": document["canonical_doc_id"],
            "keywords": keywords,
            "aliases": [document["filename"]],
            "related": relationships,
        }
    )

    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Keywords",
        "",
    ]
    for keyword in keywords:
        lines.append(f"- {keyword}")

    if chapters:
        lines.extend(["", "## Chapters", ""])
        for chapter in chapters:
            label = f"Chapter {chapter['chapter_number']}: {chapter['title']}"
            lines.extend(
                [
                    f"### {label}",
                    "",
                    f"- Pages: `p{chapter['page_start']}-p{chapter['page_end']}`",
                    f"- Link: `{chapter['wiki_link']}`",
                ]
            )
            if chapter["keywords"]:
                lines.append(f"- Keywords: {', '.join(chapter['keywords'])}")
            if chapter["section_previews"]:
                lines.append(f"- Sections: {', '.join(chapter['section_previews'])}")
            lines.extend(["", chapter["summary"], ""])

    lines.extend(
        [
            "## Metadata",
            "",
            f"- Source class: `{document['source_class']}`",
            f"- Doc ID: `{document['doc_id']}`",
            f"- Year: `{document.get('year')}`",
            f"- Pages: `{document.get('page_count')}`",
            f"- Raw file: `{document['path']}`",
            f"- Wiki link: `[[source/{document['doc_id']}]]`",
        ]
    )

    if relationships:
        lines.extend(["", "## Relationships", ""])
        for relationship in relationships:
            lines.append(f"- {relationship}")

    lines.extend(["", "## Page Anchors", ""])
    for page in pages:
        page_id = page["page_number"]
        # If it's a numeric page (PDF), prefix with 'p'. 
        # If it's a string slug (ePub/Word), use as is.
        if isinstance(page_id, int) or (isinstance(page_id, str) and page_id.isdigit()):
            anchor = f"p{page_id}"
            display_title = anchor
        else:
            anchor = page_id
            # Use section_title if available, otherwise capitalize slug
            display_title = page.get("section_title") or anchor.replace("-", " ").capitalize()
            
        lines.extend(
            [
                f"### {display_title}",
                "",
                f"Anchor: #{anchor}",
                "",
                page["preview"] or "No preview available.",
                "",
            ]
        )

    markdown = "\n".join(lines).rstrip() + "\n"

    index_entry = {
        "doc_id": document["doc_id"],
        "title": title,
        "author": author,
        "year": document.get("year"),
        "source_class": document["source_class"],
        "canonical_doc_id": document["canonical_doc_id"],
        "wiki_link": f"[[source/{document['doc_id']}]]",
        "summary": summary,
        "keywords": keywords,
        "relationships": relationships,
        "page_count": len(pages),
        "page_previews": top_previews,
        "chapters": chapters,
        "search_text": "\n".join(
            [
                title,
                author or "",
                " ".join(keywords),
                summary,
                "\n".join(
                    " ".join(
                        [
                            chapter["title"],
                            " ".join(chapter["keywords"]),
                            chapter["summary"],
                            " ".join(chapter["section_previews"]),
                        ]
                    )
                    for chapter in chapters
                ),
                "\n".join(page["preview"] for page in top_previews if page["preview"]),
            ]
        ),
    }
    return markdown, index_entry


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return load_json(path)


def fingerprint(document: dict[str, Any], extract_metadata: dict[str, Any] | None) -> str:
    parts = [
        "source-page-v3",
        document["sha256"],
        document["source_class"],
        str(document.get("relationship")),
        str(document.get("title")),
        str(document.get("author")),
        str(document.get("year")),
        document["canonical_doc_id"],
        str(document.get("dedupe_kind")),
        str(document.get("similarity")),
    ]
    if extract_metadata:
        parts.append(extract_metadata.get("updated_at", ""))
    return "|".join(parts)


def best_matching_pages(query: str, pages: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    scored = []
    for page in pages:
        score = score_text(query, page.get("text", ""), weight=1.0)
        if score > 0:
            scored.append((score, page))
    scored.sort(key=lambda item: (-item[0], item[1]["page_number"]))
    return [page for _, page in scored[:limit]]


def main() -> None:
    load_dotenv()
    load_dotenv(Path.home() / ".env")
    
    args = parse_args()
    context = KBContext(args.kb_root)
    
    if "gemini" in args.model.lower() and not os.environ.get("GEMINI_API_KEY"):
        print("Warning: GEMINI_API_KEY not found. LLM summarization will fail.")
    wiki_source_dir = args.wiki_source_dir or context.source_wiki_dir
    index_output = args.index_output or context.search_index_path
    chapter_output = args.chapter_output or context.chapter_index_path
    state_output = args.state_output or context.source_pages_state_path
    resolution_path = args.resolution or context.source_resolution_path
    catalog_path = args.catalog or context.catalog_path

    ensure_directory(wiki_source_dir)
    ensure_directory(index_output.parent)
    ensure_directory(chapter_output.parent)
    previous_state = load_state(state_output)
    previous_index = {}
    if index_output.exists():
        try:
            old_index_docs = load_json(index_output)
            previous_index = {doc["doc_id"]: doc for doc in old_index_docs}
        except Exception:
            pass
    resolution_payload = load_json(resolution_path) if resolution_path.exists() else {"documents": []}

    documents = load_json(catalog_path)["documents"]
    index_documents = []
    chapter_documents = []
    next_state: dict[str, str] = {}
    processed = 0
    skipped = 0

    for document in documents:
        doc_id = document["doc_id"]
        if not should_process(args.doc_id, doc_id):
            continue

        document = resolved_document(document, resolution_payload)
        page_path = wiki_source_dir / f"{doc_id}.md"
        paths = context.extraction_paths(doc_id)
        extract_metadata = load_json(paths["metadata"]) if paths["metadata"].exists() else None
        doc_fingerprint = fingerprint(document, extract_metadata)
        next_state[doc_id] = doc_fingerprint

        if not args.force and previous_state.get(doc_id) == doc_fingerprint and page_path.exists():
            skipped += 1
            if document["is_redundant"]:
                redundant_entry = {
                    "doc_id": doc_id,
                    "title": document.get("title") or doc_id,
                    "author": document.get("author"),
                    "year": document.get("year"),
                    "source_class": document["source_class"],
                    "canonical_doc_id": document["canonical_doc_id"],
                    "wiki_link": f"[[source/{doc_id}]]",
                    "summary": redundancy_summary(document),
                    "keywords": [],
                    "relationships": format_relationship(document),
                    "page_count": 0,
                    "page_previews": [],
                    "chapters": [],
                    "search_text": document.get("title") or doc_id,
                    "is_redundant": True,
                    "dedupe_kind": document.get("dedupe_kind"),
                }
                index_documents.append(redundant_entry)
                chapter_documents.append(
                    {
                        "doc_id": doc_id,
                        "title": redundant_entry["title"],
                        "source_class": document["source_class"],
                        "wiki_link": redundant_entry["wiki_link"],
                        "chapters": [],
                    }
                )
            else:
                # Reuse existing index entry if available to avoid re-summarization
                if doc_id in previous_index:
                    index_entry = previous_index[doc_id]
                    index_documents.append(index_entry)
                    chapter_documents.append({
                        "doc_id": doc_id,
                        "title": index_entry["title"],
                        "source_class": document["source_class"],
                        "wiki_link": index_entry["wiki_link"],
                        "chapters": index_entry.get("chapters", []),
                    })
                elif paths["pages"].exists():
                    payload = load_json(paths["pages"])
                    pages = payload.get("pages", [])
                    _, index_entry = build_page(document, pages, args.model, args.summarize_books)
                    index_entry["is_redundant"] = False
                    index_entry["dedupe_kind"] = None
                    index_documents.append(index_entry)
                    chapter_documents.append({
                        "doc_id": doc_id,
                        "title": index_entry["title"],
                        "source_class": document["source_class"],
                        "wiki_link": index_entry["wiki_link"],
                        "chapters": index_entry.get("chapters", []),
                    })
            continue

        if document["is_redundant"]:
            page_path.write_text(stub_page(document))
            redundant_entry = {
                "doc_id": doc_id,
                "title": document.get("title") or doc_id,
                "author": document.get("author"),
                "year": document.get("year"),
                "source_class": document["source_class"],
                "canonical_doc_id": document["canonical_doc_id"],
                "wiki_link": f"[[source/{doc_id}]]",
                "summary": redundancy_summary(document),
                "keywords": [],
                "relationships": format_relationship(document),
                "page_count": 0,
                "page_previews": [],
                "chapters": [],
                "search_text": document.get("title") or doc_id,
                "is_redundant": True,
                "dedupe_kind": document.get("dedupe_kind"),
            }
            index_documents.append(redundant_entry)
            chapter_documents.append(
                {
                    "doc_id": doc_id,
                    "title": redundant_entry["title"],
                    "source_class": document["source_class"],
                    "wiki_link": redundant_entry["wiki_link"],
                    "chapters": [],
                }
            )
            processed += 1
            continue

        if not paths["pages"].exists():
            raise FileNotFoundError(
                f"Missing extraction pages for {doc_id}. Run tools/extract_pages.py first."
            )

        payload = load_json(paths["pages"])
        pages = payload.get("pages", [])
        markdown, index_entry = build_page(document, pages, args.model, args.summarize_books)
        index_entry["is_redundant"] = False
        index_entry["dedupe_kind"] = None
        page_path.write_text(markdown)
        index_documents.append(index_entry)
        chapter_documents.append(
            {
                "doc_id": doc_id,
                "title": index_entry["title"],
                "source_class": document["source_class"],
                "wiki_link": index_entry["wiki_link"],
                "chapters": index_entry.get("chapters", []),
            }
        )
        processed += 1

    write_json(
        index_output,
        {
            "schema_version": 2,
            "updated_at": utc_now_iso(),
            "documents": sorted(index_documents, key=lambda item: item["doc_id"]),
        },
    )
    write_json(
        chapter_output,
        {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "documents": sorted(chapter_documents, key=lambda item: item["doc_id"]),
        },
    )
    write_json(state_output, next_state)
    print(f"processed={processed} skipped={skipped} indexed={len(index_documents)}")


if __name__ == "__main__":
    main()
