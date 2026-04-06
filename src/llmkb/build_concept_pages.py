#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from llmkb.kb_common import (
    KBContext,
    compact_whitespace,
    ensure_directory,
    load_json,
    page_signal_penalty,
    query_terms,
    render_frontmatter,
    score_text,
    slugify,
    tokenize,
    utc_now_iso,
    write_json,
)


GENERIC_TOKENS = {
    "address",
    "author",
    "authors",
    "bibliography",
    "book",
    "books",
    "cambridge",
    "chapter",
    "chapters",
    "contents",
    "copyright",
    "edition",
    "editions",
    "editor",
    "editors",
    "exercise",
    "exercises",
    "file",
    "files",
    "foreword",
    "format",
    "guide",
    "handbook",
    "house",
    "imprint",
    "introduction",
    "isbn",
    "issn",
    "kingdom",
    "manual",
    "note",
    "notes",
    "part",
    "parts",
    "preface",
    "press",
    "printing",
    "publisher",
    "publishing",
    "references",
    "remark",
    "remarks",
    "reserved",
    "reproduced",
    "section",
    "sections",
    "series",
    "textbook",
    "texts",
    "transmitted",
    "university",
    "using",
}

GENERIC_PHRASES = {
    "all rights reserved",
    "author index",
    "cambridge cb2",
    "cambridge cb2 8bs",
    "data exchange",
    "designations used",
    "digital data exchange",
    "distinguish products",
    "document file",
    "document file format",
    "file format",
    "second edition",
    "first edition",
    "fourth edition",
    "imprint elsevier",
    "john wiley",
    "john wiley sons",
    "massachusetts institute technology",
    "many designations used",
    "manufacturers sellers distinguish",
    "may reproduced",
    "morgan kaufmann",
    "printing house",
    "printing house cambridge",
    "san francisco",
    "saddle river nj",
    "sellers distinguish products",
    "third edition",
    "table of contents",
    "transmitted form",
    "upper saddle river",
    "used manufacturers sellers",
}

GENERIC_BIGRAM_TOKENS = {
    "8bs",
    "author",
    "authors",
    "cambridge",
    "cb2",
    "data",
    "design",
    "document",
    "elsevier",
    "exchange",
    "file",
    "first",
    "form",
    "francisco",
    "house",
    "imprint",
    "index",
    "john",
    "kaufmann",
    "means",
    "morgan",
    "new",
    "reproduced",
    "san",
    "sons",
    "summary",
    "time",
    "transmitted",
    "united",
    "wiley",
    "states",
    "volume",
    "will",
    "york",
}

NOISY_TEXT_FRAGMENTS = (
    "all rights reserved",
    "author index",
    "cambridge cb2",
    "claimed as trademarks",
    "copyright",
    "designations used by manufacturers and sellers",
    "document file format",
    "electronic document file format",
    "imprint of elsevier",
    "isbn",
    "issn",
    "john wiley",
    "many of the designations used",
    "morgan kaufmann",
    "pearson education",
    "printing house",
    "protected by copyright",
    "san francisco",
    "sellers to distinguish their products",
    "transmitted in any form",
    "university printing house",
    "upper saddle river",
    "written permission should be obtained",
)

DISPLAY_TOKEN_MAP = {
    "ai": "AI",
    "aws": "AWS",
    "cfd": "CFD",
    "cpp": "C++",
    "cuda": "CUDA",
    "gpu": "GPU",
    "llm": "LLM",
    "mpi": "MPI",
    "nlp": "NLP",
    "openmp": "OpenMP",
    "pdf": "PDF",
    "pde": "PDE",
    "petsc": "PETSc",
    "vtk": "VTK",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build concept pages from source-page index data.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--index",
        type=Path,
        help="Path to the source-page index JSON. Defaults to <kb-root>/artifacts/compile/search_index.json",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        help="Directory containing extracted text. Defaults to <kb-root>/artifacts/extract",
    )
    parser.add_argument(
        "--wiki-concepts-dir",
        type=Path,
        help="Directory to write wiki concept pages. Defaults to <kb-root>/wiki/concepts",
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        help="Path to write the concept index JSON. Defaults to <kb-root>/artifacts/compile/concept_index.json",
    )
    parser.add_argument("--max-concepts", default=90, type=int)
    parser.add_argument("--max-sources-per-concept", default=6, type=int)
    return parser.parse_args()


def valid_phrase(tokens: list[str]) -> bool:
    if not tokens or len(tokens) > 3:
        return False
    if tokens[0] in GENERIC_TOKENS or tokens[-1] in GENERIC_TOKENS:
        return False
    if all(token in GENERIC_TOKENS for token in tokens):
        return False
    if any(token.isdigit() for token in tokens):
        return False
    if len(tokens) < 2:
        return False
    if any(token in GENERIC_BIGRAM_TOKENS for token in tokens):
        return False
    phrase = " ".join(tokens)
    if phrase in GENERIC_PHRASES:
        return False
    return True


def noisy_text(text: str) -> bool:
    lowered = compact_whitespace(text).lower()
    if not lowered:
        return True
    return any(fragment in lowered for fragment in NOISY_TEXT_FRAGMENTS)





def singularize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 4 and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def phrase_signature(phrase: str) -> tuple[str, ...]:
    return tuple(singularize_token(token) for token in phrase.split())


def is_phrase_subsumed(
    phrase: str,
    doc_ids: set[str],
    selected_concepts: list[dict[str, Any]],
) -> bool:
    signature = phrase_signature(phrase)
    for concept in selected_concepts:
        other_signature = phrase_signature(concept["phrase"])
        if signature == other_signature:
            return True
        shorter, longer = sorted((signature, other_signature), key=len)
        windows = [
            longer[index : index + len(shorter)]
            for index in range(0, len(longer) - len(shorter) + 1)
        ]
        if shorter not in windows:
            continue
        overlap = len(doc_ids & set(concept["supporting_doc_ids"]))
        threshold = min(len(doc_ids), len(concept["supporting_doc_ids"]))
        if threshold < 2:
            continue
        if overlap / threshold >= 0.8:
            return True
    return False





def title_case_phrase(phrase: str) -> str:
    words = []
    for token in phrase.split():
        if token in DISPLAY_TOKEN_MAP:
            words.append(DISPLAY_TOKEN_MAP[token])
        else:
            words.append(token.capitalize())
    return " ".join(words)


def page_matches_for_phrase(
    context: KBContext,
    doc_id: str,
    phrase: str,
    page_cache: dict[str, list[dict[str, Any]]],
    limit: int = 2,
) -> list[dict[str, Any]]:
    if doc_id not in page_cache:
        pages_path = context.extraction_paths(doc_id)["pages"]
        if not pages_path.exists():
            page_cache[doc_id] = []
        else:
            payload = load_json(pages_path)
            page_cache[doc_id] = payload.get("pages", [])
    pages = page_cache[doc_id]
    if not pages:
        return []
    scored = []
    for page in pages:
        score = score_text(phrase, page.get("text", ""), weight=1.0)
        score -= page_signal_penalty(page.get("preview", ""))
        if score > 0:
            scored.append(
                {
                    "page_number": page["page_number"],
                    "score": round(score, 2),
                    "preview": page.get("preview") or "No preview available.",
                    "link": f"[[source/{doc_id}#p{page['page_number']}]]",
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["page_number"]))
    return scored[:limit]


def supporting_docs(
    phrase: str,
    documents: list[dict[str, Any]],
    doc_ids: set[str],
    context: KBContext,
    page_cache: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    lookup = {document["doc_id"]: document for document in documents}
    scored = []
    for doc_id in doc_ids:
        document = lookup[doc_id]
        score = score_text(phrase, document.get("title", ""), weight=5.0)
        score += score_text(phrase, " ".join(document.get("keywords", [])), weight=3.0)
        score += score_text(phrase, document.get("summary", ""), weight=2.0)
        score += score_text(phrase, document.get("search_text", ""), weight=1.0)
        if score <= 0:
            continue
        pages = page_matches_for_phrase(context, doc_id, phrase, page_cache, limit=2)
        score += sum(page["score"] for page in pages)
        scored.append(
            {
                "doc_id": doc_id,
                "title": document.get("title"),
                "wiki_link": document["wiki_link"],
                "source_class": document["source_class"],
                "score": round(score, 2),
                "pages": pages,
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["doc_id"]))
    return scored[:limit]


def concept_summary(label: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return f"This concept page collects materials related to {label.lower()}."
    links = ", ".join(source["wiki_link"] for source in sources[:4])
    return (
        f"This concept aggregates sources related to {label.lower()}. "
        f"Key supporting materials include {links}."
    )


def concept_keywords(phrase: str, sources: list[dict[str, Any]], limit: int = 12) -> list[str]:
    seen = []
    for token in phrase.split():
        if token not in seen:
            seen.append(token)
    for source in sources:
        for keyword in source.get("keywords", []):
            if keyword not in seen:
                seen.append(keyword)
            if len(seen) >= limit:
                return seen
    return seen[:limit]


def related_concepts(current_slug: str, current_doc_ids: set[str], concepts: list[dict[str, Any]]) -> list[str]:
    related = []
    for concept in concepts:
        if concept["concept_id"] == current_slug:
            continue
        overlap = len(current_doc_ids & set(concept["supporting_doc_ids"]))
        if overlap >= 2:
            related.append((overlap, concept["title"], concept["wiki_link"]))
    related.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in related[:6]]


def build_markdown(concept: dict[str, Any]) -> str:
    frontmatter = render_frontmatter(
        {
            "concept_id": concept["concept_id"],
            "title": concept["title"],
            "keywords": concept["keywords"],
            "supporting_sources": [source["wiki_link"] for source in concept["supporting_sources"]],
            "source_count": concept["source_count"],
            "generated_at": concept["generated_at"],
            "related": concept["related_concepts"],
        }
    )

    lines = [
        frontmatter,
        "",
        f"# {concept['title']}",
        "",
        "## Summary",
        "",
        concept["summary"],
        "",
        "## Key Sources",
        "",
    ]
    for source in concept["supporting_sources"]:
        lines.append(
            f"- {source['wiki_link']} [{source['source_class']}] score={source['score']}"
        )

    lines.extend(["", "## Supporting Pages", ""])
    for source in concept["supporting_sources"]:
        lines.append(f"### {source['title']}")
        lines.append("")
        if source["pages"]:
            for page in source["pages"]:
                lines.append(f"- {page['link']} score={page['score']}: {page['preview']}")
        else:
            lines.append("- No directly matching page snippets were found.")
        lines.append("")

    lines.extend(["## Related Concepts", ""])
    if concept["related_concepts"]:
        for link in concept["related_concepts"]:
            lines.append(f"- {link}")
    else:
        lines.append("- None identified yet.")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    wiki_concepts_dir = args.wiki_concepts_dir or context.concept_wiki_dir
    index_output = args.index_output or context.concept_index_path
    index_path = args.index or context.search_index_path
    extract_dir = args.extract_dir or context.extract_dir

    ensure_directory(wiki_concepts_dir)
    ensure_directory(index_output.parent)

    payload = load_json(index_path)
    documents = [
        document
        for document in payload.get("documents", [])
        if document.get("source_class") != "duplicate" and not document.get("is_redundant")
    ]

    phrase_docs: dict[str, set[str]] = defaultdict(set)
    phrase_scores: dict[str, float] = defaultdict(float)
    page_cache: dict[str, list[dict[str, Any]]] = {}

    for document in documents:
        # Use existing keywords from the search index
        for keyword in document.get("keywords", []):
            if len(keyword.split()) >= 2: # Only multi-word phrases for concepts
                phrase_docs[keyword.lower()].add(document["doc_id"])
                phrase_scores[keyword.lower()] += 5.0 # High weight for explicit keywords
        
        # Also include title bigrams/trigrams as candidates
        title = document.get("title", "")
        title_tokens = [] if noisy_text(title) else query_terms(title)
        for size in (2, 3):
            for start in range(0, max(len(title_tokens) - size + 1, 0)):
                phrase = " ".join(title_tokens[start : start + size])
                if valid_phrase(title_tokens[start : start + size]):
                    phrase_docs[phrase].add(document["doc_id"])
                    phrase_scores[phrase] += 4.0 + size


    ranked_candidates = []
    for phrase, doc_ids in phrase_docs.items():
        support = len(doc_ids)
        if support < 2:
            continue
        if support > 24:
            continue
        if len(phrase.split()) < 2:
            continue
        score = phrase_scores[phrase] + support * 4.0 + len(phrase.split()) * 1.5
        ranked_candidates.append((score, phrase, doc_ids))

    ranked_candidates.sort(key=lambda item: (-item[0], -len(item[1].split()), item[1]))

    concepts = []
    selected_phrases = set()
    for score, phrase, doc_ids in ranked_candidates:
        if len(concepts) >= args.max_concepts:
            break
        if phrase in selected_phrases:
            continue
        slug = slugify(phrase)
        if not slug:
            continue
        supporting = supporting_docs(
            phrase,
            documents,
            doc_ids,
            context,
            page_cache,
            args.max_sources_per_concept,
        )
        if len(supporting) < 2:
            continue
        if is_phrase_subsumed(phrase, doc_ids, concepts):
            continue
        label = title_case_phrase(phrase)
        summary = concept_summary(label, supporting)
        concept = {
            "phrase": phrase,
            "concept_id": slug,
            "title": label,
            "wiki_link": f"[[concepts/{slug}]]",
            "summary": summary,
            "keywords": concept_keywords(phrase, supporting),
            "supporting_sources": supporting,
            "supporting_doc_ids": [source["doc_id"] for source in supporting],
            "source_count": len(doc_ids),
            "score": round(score, 2),
            "generated_at": utc_now_iso(),
        }
        concepts.append(concept)
        selected_phrases.add(phrase)

    for concept in concepts:
        concept["related_concepts"] = related_concepts(
            concept["concept_id"], set(concept["supporting_doc_ids"]), concepts
        )

    existing = {path.stem: path for path in wiki_concepts_dir.glob("*.md")}
    written = set()
    index_documents = []
    for concept in concepts:
        path = wiki_concepts_dir / f"{concept['concept_id']}.md"
        path.write_text(build_markdown(concept))
        written.add(concept["concept_id"])
        index_documents.append(
            {
                "concept_id": concept["concept_id"],
                "title": concept["title"],
                "wiki_link": concept["wiki_link"],
                "summary": concept["summary"],
                "keywords": concept["keywords"],
                "source_count": concept["source_count"],
                "supporting_sources": concept["supporting_sources"],
                "related_concepts": concept["related_concepts"],
                "search_text": compact_whitespace(
                    "\n".join(
                        [
                            concept["title"],
                            " ".join(concept["keywords"]),
                            concept["summary"],
                            " ".join(source["title"] or "" for source in concept["supporting_sources"]),
                        ]
                    )
                ),
            }
        )

    for concept_id, path in existing.items():
        if concept_id not in written:
            path.unlink()

    write_json(
        index_output,
        {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "concepts": sorted(index_documents, key=lambda item: item["concept_id"]),
        },
    )
    print(f"concepts={len(index_documents)}")


if __name__ == "__main__":
    main()
