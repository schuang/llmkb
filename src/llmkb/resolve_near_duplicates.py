#!/usr/bin/env python3

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, STOPWORDS, compact_whitespace, load_json, tokenize, utc_now_iso, write_json


EXCLUDED_RELATIONSHIP_KINDS = {
    "companion_to",
    "excerpt_of",
    "exact_duplicate_of",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve near-duplicate sources using extracted text.")
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
        "--output",
        type=Path,
        help="Path to write the resolution JSON. Defaults to <kb-root>/artifacts/compile/source_resolution.json",
    )
    parser.add_argument("--doc-id", action="append", default=[], help="Limit analysis to selected doc_ids.")
    parser.add_argument("--shingle-size", default=5, type=int)
    parser.add_argument("--window-chars", default=5000, type=int)
    parser.add_argument("--min-similarity", default=0.82, type=float)
    parser.add_argument("--high-similarity", default=0.9, type=float)
    return parser.parse_args()


def should_process(doc_id_filters: list[str], doc_id: str) -> bool:
    if not doc_id_filters:
        return True
    return doc_id in doc_id_filters


def normalize_terms(text: str) -> list[str]:
    return [token for token in tokenize(text) if len(token) >= 3 and not token.isdigit() and token not in STOPWORDS]


def sample_text(text: str, window_chars: int) -> str:
    text = compact_whitespace(text)
    if not text:
        return ""
    if len(text) <= window_chars * 3:
        return text
    starts = {
        0,
        max(0, len(text) // 2 - window_chars // 2),
        max(0, len(text) - window_chars),
    }
    windows = []
    for start in sorted(starts):
        windows.append(text[start : start + window_chars])
    return "\n".join(windows)


def shingle_set(text: str, shingle_size: int, window_chars: int) -> set[str]:
    tokens = normalize_terms(sample_text(text, window_chars))
    if len(tokens) < 3:
        return set(tokens)
    size = min(shingle_size, max(3, len(tokens)))
    if len(tokens) < size:
        return {" ".join(tokens)}
    shingles = set()
    for index in range(0, len(tokens) - size + 1):
        shingles.add(" ".join(tokens[index : index + size]))
    return shingles


def token_jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def relationship_kind(document: dict[str, Any]) -> str | None:
    relationship = document.get("relationship")
    if not relationship:
        return None
    return relationship.get("kind")


def title_tokens(document: dict[str, Any]) -> set[str]:
    title = document.get("title") or document["doc_id"]
    return set(normalize_terms(title))


def author_tokens(document: dict[str, Any]) -> set[str]:
    return set(normalize_terms(document.get("author") or ""))


def page_count_close(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_pages = left.get("page_count") or 0
    right_pages = right.get("page_count") or 0
    if not left_pages or not right_pages:
        return True
    allowance = max(2, round(max(left_pages, right_pages) * 0.02))
    return abs(left_pages - right_pages) <= allowance


def load_full_text(context: KBContext, doc_id: str) -> str:
    paths = context.extraction_paths(doc_id)
    full_text_path = paths["full_text"]
    if full_text_path.exists():
        return full_text_path.read_text()
    pages_path = paths["pages"]
    if not pages_path.exists():
        return ""
    payload = load_json(pages_path)
    return "\n".join(page.get("text", "") for page in payload.get("pages", []))


def document_penalty(document: dict[str, Any]) -> tuple[int, int, int, str]:
    filename = document["filename"].lower()
    penalties = 0
    for token in ("copy", "scan", "ocr", "tmp", "untitled"):
        if token in filename:
            penalties += 1
    if not document.get("title"):
        penalties += 1
    if not document.get("author"):
        penalties += 1
    if filename.endswith("2.pdf"):
        penalties += 1
    year_rank = -(document.get("year") or 0)
    length_rank = len(filename)
    return (penalties, year_rank, length_rank, filename)


def choose_canonical(documents: list[dict[str, Any]]) -> str:
    return min(documents, key=document_penalty)["doc_id"]


def pair_is_near_duplicate(
    left: dict[str, Any],
    right: dict[str, Any],
    signatures: dict[str, set[str]],
    args: argparse.Namespace,
) -> tuple[bool, dict[str, Any]]:
    left_doc_id = left["doc_id"]
    right_doc_id = right["doc_id"]
    shingle_similarity = token_jaccard(signatures[left_doc_id], signatures[right_doc_id])
    title_similarity = token_jaccard(title_tokens(left), title_tokens(right))
    author_similarity = token_jaccard(author_tokens(left), author_tokens(right))
    same_class = left.get("source_class") == right.get("source_class")
    similar_pages = page_count_close(left, right)

    matched = False
    reasons = []
    if shingle_similarity >= args.high_similarity and similar_pages:
        matched = True
        reasons.append("very_high_text_similarity")
    elif (
        shingle_similarity >= args.min_similarity
        and similar_pages
        and (title_similarity >= 0.5 or author_similarity >= 0.5 or same_class)
    ):
        matched = True
        reasons.append("high_text_similarity")
    elif shingle_similarity >= 0.75 and title_similarity >= 0.8 and similar_pages:
        matched = True
        reasons.append("title_and_text_alignment")

    details = {
        "similarity": round(shingle_similarity, 4),
        "title_similarity": round(title_similarity, 4),
        "author_similarity": round(author_similarity, 4),
        "page_count_a": left.get("page_count"),
        "page_count_b": right.get("page_count"),
        "reasons": reasons,
    }
    return matched, details


def cluster_documents(matches: list[tuple[str, str, dict[str, Any]]]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right, _details in matches:
        union(left, right)

    groups: dict[str, set[str]] = {}
    for left, right, _details in matches:
        for item in (left, right):
            groups.setdefault(find(item), set()).add(item)
    return sorted(groups.values(), key=lambda group: sorted(group))


def main() -> None:
    args = parse_args()
    context = KBContext(args.kb_root)
    catalog_path = args.catalog or context.catalog_path
    output_path = args.output or context.source_resolution_path
    extract_dir = args.extract_dir or context.extract_dir

    catalog = load_json(catalog_path)
    documents = catalog.get("documents", [])
    documents_by_id = {document["doc_id"]: document for document in documents}

    eligible = []
    for document in documents:
        if not should_process(args.doc_id, document["doc_id"]):
            continue
        if document.get("source_class") == "duplicate":
            continue
        if relationship_kind(document) in EXCLUDED_RELATIONSHIP_KINDS:
            continue
        eligible.append(document)

    signatures: dict[str, set[str]] = {}
    for document in eligible:
        text = load_full_text(context, document["doc_id"])
        signatures[document["doc_id"]] = shingle_set(text, args.shingle_size, args.window_chars)

    matches: list[tuple[str, str, dict[str, Any]]] = []
    for left, right in combinations(eligible, 2):
        left_sig = signatures[left["doc_id"]]
        right_sig = signatures[right["doc_id"]]
        if not left_sig or not right_sig:
            continue
        matched, details = pair_is_near_duplicate(left, right, signatures, args)
        if matched:
            matches.append((left["doc_id"], right["doc_id"], details))

    details_by_pair = {
        tuple(sorted((left, right))): details for left, right, details in matches
    }

    resolutions: dict[str, dict[str, Any]] = {}
    clusters_payload = []
    for cluster in cluster_documents(matches):
        cluster_documents_payload = [documents_by_id[doc_id] for doc_id in cluster]
        canonical_doc_id = choose_canonical(cluster_documents_payload)
        members = []
        for doc_id in sorted(cluster):
            member = {
                "doc_id": doc_id,
                "canonical_doc_id": canonical_doc_id,
                "status": "canonical" if doc_id == canonical_doc_id else "near_duplicate",
            }
            if doc_id != canonical_doc_id:
                details = details_by_pair.get(tuple(sorted((doc_id, canonical_doc_id))))
                if details is None:
                    related = []
                    for other_doc_id in cluster:
                        if other_doc_id == doc_id:
                            continue
                        pair_details = details_by_pair.get(tuple(sorted((doc_id, other_doc_id))))
                        if pair_details:
                            related.append(pair_details)
                    if related:
                        details = max(related, key=lambda item: item["similarity"])
                similarity = details["similarity"] if details else 0.0
                member["relationship"] = {
                    "kind": "near_duplicate_of",
                    "target_doc_id": canonical_doc_id,
                }
                member["similarity"] = similarity
                member["reasons"] = details.get("reasons", []) if details else []
                resolutions[doc_id] = {
                    "doc_id": doc_id,
                    "canonical_doc_id": canonical_doc_id,
                    "status": "near_duplicate",
                    "relationship": member["relationship"],
                    "similarity": similarity,
                    "reasons": member["reasons"],
                }
            members.append(member)
        clusters_payload.append(
            {
                "canonical_doc_id": canonical_doc_id,
                "member_doc_ids": sorted(cluster),
                "members": members,
            }
        )

    for document in documents:
        resolutions.setdefault(
            document["doc_id"],
            {
                "doc_id": document["doc_id"],
                "canonical_doc_id": document.get("canonical_doc_id", document["doc_id"]),
                "status": "exact_duplicate"
                if relationship_kind(document) == "exact_duplicate_of"
                else "canonical",
                "relationship": document.get("relationship"),
            },
        )

    write_json(
        output_path,
        {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "near_duplicate_count": sum(
                1 for resolution in resolutions.values() if resolution["status"] == "near_duplicate"
            ),
            "cluster_count": len(clusters_payload),
            "clusters": clusters_payload,
            "documents": [resolutions[document["doc_id"]] for document in sorted(documents, key=lambda item: item["doc_id"])],
        },
    )
    print(
        f"near_duplicates={sum(1 for resolution in resolutions.values() if resolution['status'] == 'near_duplicate')} "
        f"clusters={len(clusters_payload)}"
    )


if __name__ == "__main__":
    main()
