#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from llmkb.kb_common import KBContext, load_json, page_signal_penalty, score_text, slugify, utc_now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a comparison note for two sources.")
    parser.add_argument("--doc-a", required=True, help="First doc_id.")
    parser.add_argument("--doc-b", required=True, help="Second doc_id.")
    parser.add_argument("--query", required=True, help="Topic or question to compare.")
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
        "--extract-dir",
        type=Path,
        help="Directory containing extracted text. Defaults to <kb-root>/artifacts/extract",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for generated notes. Defaults to <kb-root>/wiki/syntheses",
    )
    return parser.parse_args()


def top_pages(context: KBContext, doc_id: str, query: str, limit: int = 5) -> list[dict]:
    pages_path = context.extraction_paths(doc_id)["pages"]
    payload = load_json(pages_path)
    scored = []
    for page in payload.get("pages", []):
        score = score_text(query, page.get("text", ""), weight=1.0)
        score -= page_signal_penalty(page.get("preview", ""))
        if score > 0:
            scored.append((score, page))
    scored.sort(key=lambda item: (-item[0], item[1]["page_number"]))
    results = []
    for score, page in scored[:limit]:
        results.append(
            {
                "page_number": page["page_number"],
                "preview": page.get("preview") or "No preview available.",
                "score": round(score, 2),
                "link": f"[[source/{doc_id}#p{page['page_number']}]]",
            }
        )
    return results


def get_doc(index_payload: dict, doc_id: str) -> dict:
    for document in index_payload.get("documents", []):
        if document["doc_id"] == doc_id:
            return document
    raise KeyError(f"Unknown doc_id: {doc_id}")


def distinctive_keywords(doc: dict, other: dict, limit: int = 6) -> list[str]:
    own = [keyword for keyword in doc.get("keywords", []) if keyword not in other.get("keywords", [])]
    return own[:limit]


def render_section(label: str, document: dict, pages: list[dict]) -> list[str]:
    lines = [
        f"## {label}",
        "",
        f"- Source: {document['wiki_link']}",
        f"- Type: `{document['source_class']}`",
        f"- Keywords: {', '.join(document.get('keywords', [])[:10]) or 'None'}",
        "",
        "### Relevant Pages",
        "",
    ]
    if not pages:
        lines.append("- No directly matching pages were found for the query.")
        lines.append("")
        return lines

    for page in pages:
        lines.append(f"- {page['link']} score={page['score']}: {page['preview']}")
    lines.append("")
    return lines


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    index_path = args.index or context.search_index_path
    extract_dir = args.extract_dir or context.extract_dir
    output_dir = args.output_dir or context.synthesis_wiki_dir

    index_payload = load_json(index_path)
    doc_a = get_doc(index_payload, args.doc_a)
    doc_b = get_doc(index_payload, args.doc_b)

    pages_a = top_pages(context, args.doc_a, args.query)
    pages_b = top_pages(context, args.doc_b, args.query)

    shared_keywords = [keyword for keyword in doc_a.get("keywords", []) if keyword in doc_b.get("keywords", [])][:8]
    distinctive_a = distinctive_keywords(doc_a, doc_b)
    distinctive_b = distinctive_keywords(doc_b, doc_a)

    output_name = f"compare-{slugify(args.doc_a)}-vs-{slugify(args.doc_b)}-{slugify(args.query)[:48]}.md"
    output_path = args.output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f'query: "{args.query.replace("\"", "\\\"")}"',
        f'generated_at: "{utc_now_iso()}"',
        f'involved_sources: ["[[source/{args.doc_a}]]", "[[source/{args.doc_b}]]"]',
        "---",
        "",
        f"# Comparison: {doc_a['title']} vs {doc_b['title']}",
        "",
        "## Question",
        "",
        args.query,
        "",
        "## Shared Signals",
        "",
        f"- Shared keywords: {', '.join(shared_keywords) or 'None identified yet.'}",
        f"- Distinctive keywords for {doc_a['doc_id']}: {', '.join(distinctive_a) or 'None identified yet.'}",
        f"- Distinctive keywords for {doc_b['doc_id']}: {', '.join(distinctive_b) or 'None identified yet.'}",
        "",
        "## Working Notes",
        "",
        "- This note is a deterministic evidence pack, not a final interpretive essay.",
        "- Use the cited pages below as the starting point for an LLM-written synthesis or a manual comparison.",
        "",
    ]
    lines.extend(render_section(doc_a["title"], doc_a, pages_a))
    lines.extend(render_section(doc_b["title"], doc_b, pages_b))
    lines.extend(
        [
            "## Next Step",
            "",
            "- Read the cited pages from both sources and turn this evidence pack into a synthesized comparison note.",
            "",
        ]
    )

    output_path.write_text("\n".join(lines))
    print(output_path)


if __name__ == "__main__":
    main()
