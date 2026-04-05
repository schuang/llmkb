#!/usr/bin/env python3

from __future__ import annotations

import argparse
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
    parser.add_argument("--force", action="store_true", help="Regenerate all selected source pages.")
    return parser.parse_args()


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


def build_page(document: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    title = document.get("title") or document["doc_id"]
    author = document.get("author")
    summary = summarize_pages(title, pages, source_class=document.get("source_class"))
    keywords = extract_keywords(title, author, pages, source_class=document.get("source_class"))
    chapters = (
        compile_book_chapters(document["doc_id"], title, pages)
        if document.get("source_class") == "book"
        else []
    )
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
        lines.extend(
            [
                f"### p{page['page_number']}",
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
    args = parse_args()
    context = KBContext(args.kb_root)
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
                # Preserve index rebuild even when page markdown is unchanged.
                if paths["pages"].exists():
                    payload = load_json(paths["pages"])
                    pages = payload.get("pages", [])
                    _, index_entry = build_page(document, pages)
                    index_entry["is_redundant"] = False
                    index_entry["dedupe_kind"] = None
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
        markdown, index_entry = build_page(document, pages)
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
