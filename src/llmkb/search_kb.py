#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from llmkb.kb_common import KBContext, load_json, page_signal_penalty, query_terms, score_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the knowledge base by natural-language query.")
    parser.add_argument("query", help="Natural-language query.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--index",
        type=Path,
        help="Path to the source index JSON. Defaults to <kb-root>/artifacts/compile/search_index.json",
    )
    parser.add_argument(
        "--concept-index",
        type=Path,
        help="Path to the concept index JSON. Defaults to <kb-root>/artifacts/compile/concept_index.json",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        help="Directory containing extracted text. Defaults to <kb-root>/artifacts/extract",
    )
    parser.add_argument("--top-docs", default=5, type=int, help="Backward-compatible alias for result count.")
    parser.add_argument("--top-results", type=int, help="Total number of results to return.")
    parser.add_argument("--top-pages", default=3, type=int)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text.")
    return parser.parse_args()


def page_matches(query: str, context: KBContext, doc_id: str, limit: int) -> list[dict]:
    pages_path = context.extraction_paths(doc_id)["pages"]
    if not pages_path.exists():
        return []
    payload = load_json(pages_path)
    scored = []
    for page in payload.get("pages", []):
        score = score_text(query, page.get("text", ""), weight=1.0)
        score -= page_signal_penalty(page.get("preview", ""))
        if score > 0:
            scored.append(
                {
                    "page_number": page["page_number"],
                    "score": round(score, 2),
                    "preview": page.get("preview", ""),
                    "link": f"[[source/{doc_id}#p{page['page_number']}]]",
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["page_number"]))
    return scored[:limit]


def chapter_matches(query: str, document: dict, limit: int) -> list[dict]:
    scored = []
    for chapter in document.get("chapters", []):
        score = 0.0
        score += score_text(query, chapter.get("title", ""), weight=4.0)
        score += score_text(query, " ".join(chapter.get("keywords", [])), weight=3.0)
        score += score_text(query, chapter.get("summary", ""), weight=2.0)
        score += score_text(query, " ".join(chapter.get("section_previews", [])), weight=1.5)
        if score > 0:
            scored.append(
                {
                    "chapter_number": chapter["chapter_number"],
                    "title": chapter.get("title"),
                    "page_start": chapter.get("page_start"),
                    "page_end": chapter.get("page_end"),
                    "link": chapter.get("wiki_link"),
                    "score": round(score, 2),
                    "keywords": chapter.get("keywords", []),
                    "summary": chapter.get("summary", ""),
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["chapter_number"]))
    return scored[:limit]


def doc_score(query: str, document: dict) -> float:
    score = 0.0
    score += score_text(query, document.get("title", ""), weight=4.0)
    score += score_text(query, " ".join(document.get("keywords", [])), weight=3.0)
    score += score_text(query, document.get("summary", ""), weight=2.0)
    score += score_text(query, document.get("search_text", ""), weight=1.0)
    chapter_bonus = 0.0
    for chapter in chapter_matches(query, document, limit=2):
        chapter_bonus += chapter["score"] * 0.6
    score += chapter_bonus
    if document.get("source_class") == "duplicate":
        score *= 0.25
    if document.get("is_redundant"):
        score *= 0.15 if document.get("dedupe_kind") == "near_duplicate_of" else 0.05
    return score


def concept_score(query: str, concept: dict) -> float:
    score = 0.0
    score += score_text(query, concept.get("title", ""), weight=5.0)
    score += score_text(query, " ".join(concept.get("keywords", [])), weight=3.0)
    score += score_text(query, concept.get("summary", ""), weight=2.0)
    score += score_text(query, concept.get("search_text", ""), weight=1.5)
    score += min(concept.get("source_count", 0), 8) * 0.25
    return score


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    index_path = args.index or context.search_index_path
    concept_index_path = args.concept_index or context.concept_index_path
    extract_dir = args.extract_dir or context.extract_dir

    payload = load_json(index_path)
    concept_payload = load_json(concept_index_path) if concept_index_path.exists() else {"concepts": []}
    total_results = args.top_results or args.top_docs
    candidates = []
    terms = query_terms(args.query)
    if not terms:
        raise SystemExit("Query must contain at least one meaningful term.")

    for concept in concept_payload.get("concepts", []):
        score = concept_score(args.query, concept)
        if score > 0:
            candidates.append({"kind": "concept", "entry": concept, "score": round(score, 2)})

    for document in payload.get("documents", []):
        score = doc_score(args.query, document)
        if score > 0:
            candidates.append({"kind": "source", "entry": document, "score": round(score, 2)})

    def sort_key(item: dict) -> tuple[float, int, str]:
        entry = item["entry"]
        kind_rank = 0 if item["kind"] == "concept" else 1
        entry_id = entry.get("concept_id") or entry.get("doc_id") or ""
        return (-item["score"], kind_rank, entry_id)

    candidates.sort(key=sort_key)
    shortlisted = candidates[: max(total_results * 4, 16)]

    results = []
    for item in shortlisted:
        if item["kind"] == "concept":
            concept = item["entry"]
            support = []
            support_bonus = 0.0
            for source in concept.get("supporting_sources", [])[: min(args.top_pages, 3)]:
                pages = page_matches(args.query, context, source["doc_id"], 1)
                support_bonus += sum(page["score"] for page in pages)
                support.append(
                    {
                        "doc_id": source["doc_id"],
                        "title": source.get("title"),
                        "wiki_link": source["wiki_link"],
                        "pages": pages,
                    }
                )
            results.append(
                {
                    "kind": "concept",
                    "concept_id": concept["concept_id"],
                    "title": concept.get("title"),
                    "wiki_link": concept["wiki_link"],
                    "summary": concept.get("summary"),
                    "keywords": concept.get("keywords", []),
                    "score": round(item["score"] + support_bonus, 2),
                    "supporting_sources": support,
                }
            )
        else:
            document = item["entry"]
            chapters = chapter_matches(args.query, document, min(args.top_pages, 3))
            pages = page_matches(args.query, context, document["doc_id"], args.top_pages)
            final_score = item["score"] + sum(page["score"] for page in pages) + sum(
                chapter["score"] for chapter in chapters
            )
            results.append(
                {
                    "kind": "source",
                    "doc_id": document["doc_id"],
                    "title": document.get("title"),
                    "wiki_link": document["wiki_link"],
                    "source_class": document["source_class"],
                    "is_redundant": document.get("is_redundant", False),
                    "dedupe_kind": document.get("dedupe_kind"),
                    "summary": document.get("summary"),
                    "keywords": document.get("keywords", []),
                    "score": round(final_score, 2),
                    "chapters": chapters,
                    "pages": pages,
                }
            )

    def result_sort_key(item: dict) -> tuple[float, int, str]:
        kind_rank = 0 if item["kind"] == "concept" else 1
        entry_id = item.get("concept_id") or item.get("doc_id") or ""
        return (-item["score"], kind_rank, entry_id)

    results.sort(key=result_sort_key)
    results = results[:total_results]

    if args.json:
        print(json.dumps({"query": args.query, "results": results}, indent=2))
        return

    print(f"Query: {args.query}")
    for index, result in enumerate(results, start=1):
        if result["kind"] == "concept":
            print(f"{index}. {result['title']} {result['wiki_link']} [concept] score={result['score']}")
            if result["keywords"]:
                print(f"   keywords: {', '.join(result['keywords'][:8])}")
            if result["summary"]:
                print(f"   summary: {result['summary']}")
            for source in result["supporting_sources"]:
                print(f"   source: {source['wiki_link']} {source['title']}")
                for page in source["pages"]:
                    preview = page["preview"] or "No preview available."
                    print(f"   page: {page['link']} score={page['score']} {preview}")
            continue

        print(
            f"{index}. {result['title']} {result['wiki_link']} "
            f"[{result['source_class']}] score={result['score']}"
        )
        if result.get("is_redundant") and result.get("dedupe_kind"):
            print(f"   status: {result['dedupe_kind']} -> canonical source")
        if result["keywords"]:
            print(f"   keywords: {', '.join(result['keywords'][:8])}")
        if result["summary"]:
            print(f"   summary: {result['summary']}")
        for chapter in result.get("chapters", []):
            print(
                f"   chapter: {chapter['link']} score={chapter['score']} "
                f"Chapter {chapter['chapter_number']}: {chapter['title']} "
                f"(p{chapter['page_start']}-p{chapter['page_end']})"
            )
        for page in result["pages"]:
            preview = page["preview"] or "No preview available."
            print(f"   page: {page['link']} score={page['score']} {preview}")


if __name__ == "__main__":
    main()
