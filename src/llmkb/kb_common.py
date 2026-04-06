#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_RE = re.compile(r"\s+")
ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
SECTION_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\b")
CHAPTER_NUMBER_RE = re.compile(r"^chapter\s+(\d+)\b", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ISBN_RE = re.compile(r"(?:ISBN(?:-1[03])?:?\s+)?(?=[0-9X]{10}$|(?=(?:[0-9]+[- ]){3})[- 0-9X]{13}$|97[89][0-9]{10}$|(?=(?:[0-9]+[- ]){4})[- 0-9]{17}$)(?:97[89][- ]?)?[0-9]{1,5}[- ]?[0-9]+[- ]?[0-9]+[- ]?[0-9X]", re.IGNORECASE)

EXPLICIT_KEYWORD_PATTERNS = (
    re.compile(r"\bfinite difference methods?\b", re.IGNORECASE),
    re.compile(r"\bfinite volume methods?\b", re.IGNORECASE),
    re.compile(r"\bfractional-step methods?\b", re.IGNORECASE),
    re.compile(r"\bsimple method\b", re.IGNORECASE),
    re.compile(r"\bsimpler\b", re.IGNORECASE),
    re.compile(r"\bsimplec\b", re.IGNORECASE),
    re.compile(r"\bpiso\b", re.IGNORECASE),
    re.compile(r"\bcompressible flows?\b", re.IGNORECASE),
    re.compile(r"\bincompressible flows?\b", re.IGNORECASE),
    re.compile(r"\bpressure-correction equations?\b", re.IGNORECASE),
    re.compile(r"\bpressure-correction methods?\b", re.IGNORECASE),
    re.compile(r"\bboundary conditions?\b", re.IGNORECASE),
    re.compile(r"\bnavier[-–]stokes equations?\b", re.IGNORECASE),
    re.compile(r"\bturbulence models?\b", re.IGNORECASE),
    re.compile(r"\bspectral methods?\b", re.IGNORECASE),
    re.compile(r"\bmultigrid methods?\b", re.IGNORECASE),
    re.compile(r"\bheterogeneous parallel computing\b", re.IGNORECASE),
    re.compile(r"\bparallel programming languages and models\b", re.IGNORECASE),
    re.compile(r"\bcuda memory model\b", re.IGNORECASE),
    re.compile(r"\bcuda thread execution model\b", re.IGNORECASE),
    re.compile(r"\bgpu hardware performance features\b", re.IGNORECASE),
    re.compile(r"\bcuda device memory types\b", re.IGNORECASE),
    re.compile(r"\bmatrix[- ]matrix multiplication\b", re.IGNORECASE),
    re.compile(r"\bconvolution\b", re.IGNORECASE),
    re.compile(r"\bparallel scan\b", re.IGNORECASE),
    re.compile(r"\bsparse matrix[- ]vector multiplication\b", re.IGNORECASE),
    re.compile(r"\bopencl\b", re.IGNORECASE),
    re.compile(r"\bopenacc\b", re.IGNORECASE),
    re.compile(r"\bmpi/cuda\b", re.IGNORECASE),
)
PRIORITY_BOOK_KEYWORDS = {
    "boundary conditions",
    "compressible flows",
    "direct numerical simulation",
    "finite difference method",
    "finite volume method",
    "fractional-step method",
    "gpu hardware performance features",
    "heterogeneous parallel computing",
    "incompressible flows",
    "matrix-matrix multiplication",
    "multigrid method",
    "navier-stokes equation",
    "openacc",
    "opencl",
    "parallel programming languages and models",
    "parallel scan",
    "piso method",
    "pressure-correction equation",
    "pressure-correction method",
    "sparse matrix-vector multiplication",
    "simple method",
    "simplec method",
    "simpler method",
    "spectral method",
    "turbulence models",
    "cuda device memory types",
    "cuda memory model",
    "cuda thread execution model",
    "convolution",
}
BOOK_KEYWORD_SKIP_PHRASES = {
    "iterative method",
    "steady unsteady flows",
    "strategies steady unsteady",
    "calculation strategies steady unsteady",
    "non-iterative implicit methods unsteady flows",
    "pressure-correction methods arbitrary mach number",
    "organization of the book",
    "references and further reading",
    "chapter outline",
    "background",
    "simpler method",
    "simpler",
    "simple method",
    "boundary conditions",
}

STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

NOISY_SENTENCE_FRAGMENTS = (
    "all rights reserved",
    "assistant director",
    "cambridge, massachusetts",
    "all rights reserved",
    "cataloging-in-publication",
    "copyright",
    "department of computer science",
    "email",
    "information science and statistics",
    "library of congress",
    "mit press",
    "printed and bound",
    "professor",
    "series editors",
    "springer nature",
    "cambridge university press",
    "isbn",
    "issn",
    "doi.org",
    "electronic supplementary material",
)

PAPER_SUMMARY_CUE_PHRASES = (
    "in this paper",
    "in this study",
    "in this work",
    "the present paper",
    "the present study",
    "the present work",
    "we propose",
    "we show",
    "we demonstrate",
    "we investigate",
    "our results show",
    "we conclude",
)

SUMMARY_CUE_PHRASES = (
    "this book",
    "this textbook",
    "this text",
    "we wrote this book",
    "the goal of this book",
    "the aim of this book",
    "in this book",
    "we introduce",
    "we present",
    "we describe",
    "we develop",
    "focuses on",
    "covers",
    "provides",
    "introduction to",
    "unified probabilistic approach",
)

BOOK_OVERVIEW_TERMS = (
    "aimed at",
    "broad coverage",
    "comprehensive introduction",
    "detailed introduction",
    "focus",
    "goal",
    "introduction to the field",
    "provides a",
    "suitable for",
    "target audience",
    "this book",
    "this textbook",
    "we wrote this book",
)

BOOK_PAGE_CUES = (
    "preface",
    "introduction",
    "plan of this book",
    "organization",
    "what is",
)

KEYWORD_SINGLE_TOKEN_BLACKLIST_BASE = {
    "approach",
    "approaches",
    "approximation",
    "approximations",
    "basic",
    "case",
    "cases",
    "concept",
    "concepts",
    "detail",
    "details",
    "equation",
    "equations",
    "example",
    "examples",
    "first",
    "flow",
    "fluid",
    "general",
    "good",
    "grid",
    "grids",
    "implementation",
    "many",
    "mass",
    "may",
    "method",
    "methods",
    "model",
    "models",
    "momentum",
    "numerical",
    "one",
    "problem",
    "problems",
    "reader",
    "readers",
    "second",
    "solution",
    "solutions",
    "system",
    "systems",
    "third",
    "two",
    "used",
    "using",
    "value",
    "values",
    "will",
}

KEYWORD_PHRASE_GENERIC_TOKENS = {
    "analysis",
    "approach",
    "approaches",
    "basic",
    "book",
    "books",
    "chapter",
    "chapters",
    "components",
    "concepts",
    "contents",
    "course",
    "detail",
    "details",
    "example",
    "examples",
    "first",
    "general",
    "implementation",
    "introduction",
    "many",
    "one",
    "plan",
    "preface",
    "problem",
    "problems",
    "reader",
    "readers",
    "summary",
    "section",
    "sections",
    "second",
    "third",
    "this",
    "two",
    "used",
    "using",
}

KEYWORD_ALLOWED_EDGE_TOKENS = {
    "algorithm",
    "algorithms",
    "conditions",
    "dynamics",
    "equation",
    "equations",
    "flow",
    "flows",
    "method",
    "methods",
}

KEYWORD_DOMAIN_TOKENS = {
    "boundary",
    "cfd",
    "compressible",
    "conservation",
    "cuda",
    "convolution",
    "computing",
    "csr",
    "execution",
    "dynamics",
    "finite",
    "flow",
    "flows",
    "fractional-step",
    "fractional",
    "grid",
    "gpu",
    "incompressible",
    "kernel",
    "mach",
    "matrix",
    "mesh",
    "method",
    "methods",
    "memory",
    "models",
    "multigrid",
    "navier-stokes",
    "numerical",
    "openacc",
    "opencl",
    "parallel",
    "piso",
    "pressure",
    "processors",
    "reynolds",
    "scan",
    "scalar",
    "shock",
    "simple",
    "spmv",
    "spectral",
    "step",
    "sparse",
    "thread",
    "transport",
    "turbulence",
    "turbulent",
    "unsteady",
    "velocity",
    "volume",
}

SUMMARY_GENERIC_TOKENS = {
    "book",
    "books",
    "chapter",
    "chapters",
    "contents",
    "edition",
    "editions",
    "editor",
    "editors",
    "exercise",
    "exercises",
    "figure",
    "figures",
    "introduction",
    "note",
    "notes",
    "part",
    "parts",
    "preface",
    "problem",
    "problems",
    "section",
    "sections",
    "series",
    "table",
    "tables",
    "university",
}

KEYWORD_SINGLE_TOKEN_BLACKLIST = SUMMARY_GENERIC_TOKENS | KEYWORD_SINGLE_TOKEN_BLACKLIST_BASE

NOISY_PREVIEWS = {
    "",
    "acknowledgments",
    "acknowledgements",
    "contents",
    "copyright",
    "dedication",
    "index",
}


def normalize_author_string(author_str: str | None) -> str | None:
    """Normalize messy author strings from various APIs into a standard format.
    
    Transforms:
    - "Last, First" -> "First Last"
    - "J.Smith" -> "J. Smith"
    - "J.R. Tolkien" -> "J. R. Tolkien"
    - "Moser, Robert D.; Kim, John" -> "Robert D. Moser; John Kim"
    """
    if not author_str:
        return None
        
    authors = [a.strip() for a in author_str.split(";") if a.strip()]
    normalized = []
    
    for author in authors:
        # Handle "Last, First" format from Crossref/DataCite
        if "," in author:
            parts = [p.strip() for p in author.split(",")]
            if len(parts) == 2:
                author = f"{parts[1]} {parts[0]}"
                
        # Clean up weird spacing
        author = re.sub(r'\s+', ' ', author)
        
        # Ensure initials have a space after the period if followed by a letter (e.g., "J.Smith" -> "J. Smith")
        author = re.sub(r'([A-Z]\.)([A-Z][a-z])', r'\1 \2', author)
        
        # Ensure initials have a space between them (e.g., "J.R. Smith" -> "J. R. Smith")
        author = re.sub(r'([A-Z]\.)([A-Z]\.)', r'\1 \2', author)
        
        normalized.append(author.strip())
        
    return "; ".join(normalized)

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
    if match:
        return match.group(0).rstrip('.')
    return None


def extract_isbn(text: str) -> str | None:
    match = ISBN_RE.search(text)
    if match:
        isbn = match.group(0).upper()
        isbn = re.sub(r'[^0-9X]', '', isbn)
        if len(isbn) in (10, 13):
            return isbn
    return None


def normalize_token(token: str) -> str:
    token = token.lower()
    token = token.replace("c++", "cpp")
    token = token.replace("c#", "c-sharp")
    token = token.replace("&", "and")
    token = token.strip(".-_/")
    return token


def slugify(value: str) -> str:
    value = normalize_token(value)
    value = NON_ALNUM_RE.sub("-", value)
    return value.strip("-")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text.lower()):
        token = normalize_token(raw)
        token = NON_ALNUM_RE.sub("-", token).strip("-")
        if token:
            tokens.append(token)
    return tokens


def compact_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def page_preview(text: str, max_chars: int = 160) -> str:
    lines = [compact_whitespace(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    preview = lines[0]
    if len(preview) > max_chars:
        return preview[: max_chars - 3].rstrip() + "..."
    return preview


def text_lines(text: str, limit: int | None = None) -> list[str]:
    lines = [compact_whitespace(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if limit is None:
        return lines
    return lines[:limit]


def chapter_summary_text(page: dict[str, Any]) -> str:
    kept: list[str] = []
    for line in text_lines(page.get("text", "")):
        lowered = line.lower()
        if not kept:
            if lowered == "chapter" or lowered.startswith("chapter "):
                continue
            if lowered.startswith("chapter outline"):
                continue
            if line.isdigit() or ROMAN_RE.fullmatch(line):
                continue
            if SECTION_NUMBER_RE.match(line):
                continue
            if "...." in line or "....." in line:
                continue
        # More aggressive filtering
        if len(line.split()) < 4:  # Remove very short lines
            continue
        if line.isupper():  # Remove all-caps lines
            continue
        if sum(c.isdigit() for c in line) > len(line) * 0.4:  # Remove lines with many numbers
            continue
        kept.append(line)
    return compact_whitespace(" ".join(kept))


def informative_tokens(text: str) -> list[str]:
    return [
        token
        for token in tokenize(text)
        if len(token) >= 3 and token not in STOPWORDS and token not in SUMMARY_GENERIC_TOKENS and not token.isdigit()
    ]


def preview_is_noisy(preview: str) -> bool:
    preview = compact_whitespace(preview).lower()
    if preview in NOISY_PREVIEWS:
        return True
    if preview.isdigit() or ROMAN_RE.fullmatch(preview):
        return True
    if preview.startswith("contents"):
        return True
    if preview.startswith("table of contents"):
        return True
    return False


def page_noise_penalty(page: dict[str, Any], source_class: str | None) -> float:
    preview = compact_whitespace(page.get("preview", ""))
    text = compact_whitespace(page.get("text", ""))
    lowered = text.lower()
    penalty = page_signal_penalty(preview)
    if not text:
        return penalty + 10.0
    if preview_is_noisy(preview):
        penalty += 8.0
    for fragment in NOISY_SENTENCE_FRAGMENTS:
        if fragment in lowered:
            penalty += 4.0
    if lowered.startswith("contents ") or lowered.startswith("table of contents"):
        penalty += 8.0
    if "series editors" in lowered:
        penalty += 8.0
    if "library of congress" in lowered:
        penalty += 6.0
    if "all rights reserved" in lowered:
        penalty += 8.0
    if "printed and bound" in lowered:
        penalty += 5.0
    if source_class == "book" and page.get("page_number", 0) <= 6:
        penalty += 2.0
    return penalty


def topic_profile(title: str | None, pages: list[dict[str, Any]], source_class: str | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if title:
        for token in informative_tokens(title):
            counts[token] += 8

    page_budget = 80 if source_class == "book" else 20
    for page in pages[: min(len(pages), page_budget)]:
        if page_noise_penalty(page, source_class) >= 10:
            continue
        text = compact_whitespace(page.get("text", ""))
        if len(text) < 120:
            continue
        for token in informative_tokens(text[:2000]):
            counts[token] += 1
    return counts


def page_summary_score(
    page: dict[str, Any],
    title_terms: set[str],
    profile: Counter[str],
    source_class: str | None,
) -> float:
    text = compact_whitespace(page.get("text", ""))
    if len(text) < 140:
        return -1000.0

    lowered = text.lower()
    preview = compact_whitespace(page.get("preview", "")).lower()
    score = -page_noise_penalty(page, source_class)
    page_number = page.get("page_number", 0)

    terms = set(informative_tokens(text[:2000]))
    score += sum(3.0 for token in title_terms if token in terms)
    score += sum(min(profile.get(token, 0), 5) * 0.35 for token in terms)

    if source_class == "book":
        if lowered.startswith("preface ") or "preface introduction" in lowered[:200]:
            score += 12.0
        if lowered.startswith("introduction "):
            score += 10.0
        if preview in {"preface", "1. introduction"} or preview.startswith("1. introduction"):
            score += 10.0
        if preview.startswith("chapter 1"):
            score += 5.0
        if "introduction" in preview:
            score += 4.0
        if 7 <= page_number <= 40:
            score += 4.0
        elif 20 <= page_number <= 80:
            score += 2.0
        elif 7 <= page_number <= 120:
            score += 1.0
        if page_number <= 6:
            score -= 10.0
    else:
        if page_number <= 3:
            score += 5.0
        elif page_number <= 8:
            score += 2.0

    return score


def sentence_summary_score(
    sentence: str,
    title_terms: set[str],
    profile: Counter[str],
    source_class: str | None,
) -> float:
    lowered = sentence.lower()
    terms = set(informative_tokens(sentence))
    if not terms:
        return -1000.0

    score = 0.0
    score += sum(4.0 for token in title_terms if token in terms)
    score += sum(min(profile.get(token, 0), 6) * 0.45 for token in terms)
    score += min(len(terms), 14) * 0.15

    for phrase in SUMMARY_CUE_PHRASES:
        if phrase in lowered:
            score += 3.0

    if source_class == "book":
        if "this book" in lowered or "this textbook" in lowered:
            score += 3.0
        if "this chapter" in lowered or "in this chapter" in lowered:
            score += 5.0
        if not any(phrase in lowered for phrase in SUMMARY_CUE_PHRASES + BOOK_OVERVIEW_TERMS):
            score -= 6.0
        if "chapter" in lowered and "introduc" not in lowered:
            score -= 2.0
        if sentence.count(":") >= 2:
            score -= 5.0

    if any(fragment in lowered for fragment in NOISY_SENTENCE_FRAGMENTS):
        score -= 12.0
    if any(fragment in lowered for fragment in ("figure ", "section ", "equation", "exercise", "table ", "example:")):
        score -= 6.0
    if "@" in sentence or "http" in lowered or "www." in lowered:
        score -= 8.0
    if sentence.isupper():
        score -= 4.0
    if sum(char.isdigit() for char in sentence) >= 8:
        score -= 5.0
    if len(terms) < 5:
        score -= 3.0
    return score


def sentence_is_structural_noise(sentence: str) -> bool:
    lowered = sentence.lower()
    if SECTION_NUMBER_RE.match(sentence):
        return True
    if any(fragment in lowered for fragment in NOISY_SENTENCE_FRAGMENTS):
        return True
    if any(
        fragment in lowered
        for fragment in (
            "interested readers may find",
            "not be covered in this book",
            "special thanks",
            "we also hope",
            "for this reason, the references",
            "how to use the book",
            "phase 1",
            "phase 2",
            "phase 3",
            "final project",
            "project workshop",
            "project report",
            "lecture slots",
            "programming assignments",
            "teaching assistants",
            "class symposium",
            "ece408",
            "ece498",
        )
    ):
        return True
    if any(fragment in lowered for fragment in ("figure ", "table ", "equation", "exercise", "appendix ")):
        return True
    if sentence.count(":") >= 3:
        return True
    if sum(char.isdigit() for char in sentence) >= 8:
        return True
    return False


def keyword_phrase_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()]


def valid_keyword_phrase(tokens: list[str], title_terms: set[str]) -> bool:
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if all(token in KEYWORD_PHRASE_GENERIC_TOKENS for token in tokens):
        return False
    if tokens[0] in KEYWORD_PHRASE_GENERIC_TOKENS and tokens[0] not in KEYWORD_ALLOWED_EDGE_TOKENS:
        return False
    if tokens[-1] in KEYWORD_PHRASE_GENERIC_TOKENS and tokens[-1] not in KEYWORD_ALLOWED_EDGE_TOKENS:
        return False
    if sum(1 for token in tokens if token in KEYWORD_DOMAIN_TOKENS or token in title_terms) == 0:
        return False
    if sum(1 for token in tokens if token not in KEYWORD_PHRASE_GENERIC_TOKENS) < 2:
        return False
    phrase = " ".join(tokens)
    if phrase in {"fluid dynamics", "computational methods", "numerical methods"}:
        return True
    return True


def score_keyword_phrase(tokens: list[str], title_terms: set[str], source_class: str | None) -> float:
    score = 0.0
    domain_hits = sum(1 for token in tokens if token in KEYWORD_DOMAIN_TOKENS)
    title_hits = sum(1 for token in tokens if token in title_terms)
    score += domain_hits * 2.5
    score += title_hits * 2.0
    if len(tokens) >= 2:
        score += 1.0
    if tokens[-1] in {"flow", "flows", "method", "methods", "equations", "conditions", "algorithm", "algorithms"}:
        score += 1.0
    if source_class == "book" and any(token in {"simple", "fractional-step", "compressible", "incompressible"} for token in tokens):
        score += 1.5
    return score


def add_keyword_phrases(
    counts: Counter[str],
    text: str,
    weight: float,
    title_terms: set[str],
    source_class: str | None,
) -> None:
    tokens = keyword_phrase_tokens(text)
    if len(tokens) < 2:
        return
    seen: set[str] = set()
    for size in (2, 3, 4):
        for index in range(0, len(tokens) - size + 1):
            phrase_tokens = tokens[index : index + size]
            if not valid_keyword_phrase(phrase_tokens, title_terms):
                continue
            phrase = " ".join(phrase_tokens)
            if phrase in seen:
                continue
            seen.add(phrase)
            counts[phrase] += weight + score_keyword_phrase(phrase_tokens, title_terms, source_class)


def cleaned_preview_phrase(preview: str) -> str:
    preview = compact_whitespace(preview)
    preview = re.sub(r"^chapter\s+\d+\s*", "", preview, flags=re.IGNORECASE)
    preview = re.sub(r"^\d+(?:\.\d+)*\s*", "", preview)
    preview = preview.replace("–", " ").replace("—", " ")
    return compact_whitespace(preview)


def parse_chapter_number(text: str) -> int | None:
    lowered = compact_whitespace(text).lower()
    match = CHAPTER_NUMBER_RE.match(lowered)
    if match:
        return int(match.group(1))
    return None


def section_heading_info(preview: str) -> tuple[int, str] | None:
    cleaned = compact_whitespace(preview)
    match = SECTION_HEADING_RE.match(cleaned)
    if not match:
        return None
    return int(match.group(1)), compact_whitespace(match.group(3))


def chapter_start_info(pages: list[dict[str, Any]], index: int) -> tuple[int, str] | None:
    page = pages[index]
    preview = compact_whitespace(page.get("preview", ""))
    lowered_text = compact_whitespace(page.get("text", "")).lower()
    if preview_is_noisy(preview) and "chapter" not in preview.lower():
        if "contents" in lowered_text[:300]:
            return None
    if lowered_text.startswith("contents ") or lowered_text.startswith("table of contents"):
        return None
    chapter_number = parse_chapter_number(preview)
    if chapter_number is None and (preview_is_noisy(preview) or preview.upper() == "CHAPTER"):
        for line in text_lines(page.get("text", ""), limit=8):
            chapter_number = parse_chapter_number(line)
            if chapter_number is not None:
                break
    if chapter_number is None and preview.upper() == "CHAPTER":
        lines = text_lines(page.get("text", ""), limit=8)
        saw_chapter = False
        for line in lines:
            upper = line.upper()
            if upper == "CHAPTER":
                saw_chapter = True
                continue
            if saw_chapter and line.isdigit():
                chapter_number = int(line)
                break
        if chapter_number is None:
            for lookahead in range(index + 1, min(index + 4, len(pages))):
                info = section_heading_info(pages[lookahead].get("preview", ""))
                if info:
                    chapter_number = info[0]
                    break
    if chapter_number is None:
        return None

    title = chapter_title_from_pages(pages, index, chapter_number)
    return chapter_number, title or f"Chapter {chapter_number}"


def chapter_title_from_pages(pages: list[dict[str, Any]], start_index: int, chapter_number: int) -> str:
    page = pages[start_index]
    ignore_lines = {
        "chapter",
        f"chapter {chapter_number}",
        "chapter outline",
    }
    title_lines: list[str] = []
    for line in text_lines(page.get("text", ""), limit=14):
        lowered = line.lower()
        if lowered in ignore_lines:
            continue
        if line.isdigit() or ROMAN_RE.fullmatch(line):
            if title_lines:
                break
            continue
        if SECTION_NUMBER_RE.match(line):
            if title_lines:
                break
            continue
        if lowered.startswith("references"):
            break
        if lowered.startswith("chapter outline"):
            break
        if "...." in line or "....." in line:
            continue
        if not any(char.isalpha() for char in line):
            continue
        if len(tokenize(line)) <= 8:
            title_lines.append(line)
            continue
        if title_lines:
            break

    if title_lines:
        return compact_whitespace(" ".join(title_lines[:3]))

    for lookahead in range(start_index, min(start_index + 5, len(pages))):
        preview = cleaned_preview_phrase(pages[lookahead].get("preview", ""))
        info = section_heading_info(preview)
        if info and info[0] == chapter_number:
            return info[1]
        if preview and not preview_is_noisy(preview):
            if parse_chapter_number(preview) is not None:
                continue
            if "...." in preview or "....." in preview:
                continue
            if len(tokenize(preview)) <= 8:
                return preview
    return f"Chapter {chapter_number}"


def normalize_keyword_phrase(phrase: str) -> str:
    phrase = compact_whitespace(phrase).lower().replace("–", "-").replace("—", "-")
    phrase = phrase.replace("finite-volume", "finite volume")
    phrase = phrase.replace("finite-difference", "finite difference")
    phrase = re.sub(r"^calculation strategies for ", "", phrase)
    phrase = re.sub(r"^methods designed for ", "", phrase)
    phrase = re.sub(r"^implementation of ", "", phrase)
    phrase = re.sub(r"^solution of the ", "", phrase)
    phrase = re.sub(r"^simulation of ", "", phrase)
    phrase = re.sub(r"^the choice of ", "", phrase)
    phrase = re.sub(r"^approximation of ", "", phrase)
    phrase = re.sub(r"^introduction to ", "", phrase)
    phrase = re.sub(r"^properties of ", "", phrase)
    phrase = re.sub(r": part \d+$", "", phrase)
    phrase = re.sub(r"\bsimpler\b", "simpler method", phrase)
    phrase = re.sub(r"\bsimplec\b", "simplec method", phrase)
    phrase = re.sub(r"\bpiso\b", "piso method", phrase)
    phrase = re.sub(r"\bturbulence with models\b", "turbulence models", phrase)
    phrase = re.sub(r"\bmethods? arbitrary mach number\b", "pressure-correction method", phrase)
    phrase = re.sub(r"\bdirect numerical simulation dns\b", "direct numerical simulation", phrase)
    phrase = re.sub(r"\bpressure-correction pressure-correction method\b", "pressure-correction method", phrase)
    phrase = re.sub(r"\b(method|equation|algorithm|flow|flows)\b(?: \1\b)+", r"\1", phrase)
    tokens = phrase.split()
    if not tokens:
        return phrase
    replacements = {
        "methods": "method",
        "flows": "flows",
        "equations": "equation",
        "algorithms": "algorithm",
        "conditions": "conditions",
    }
    if tokens[-1] in replacements:
        tokens[-1] = replacements[tokens[-1]]
    phrase = " ".join(tokens)
    if phrase == "compressible flow":
        return "compressible flows"
    if phrase == "incompressible flow":
        return "incompressible flows"
    return phrase


def extract_explicit_keyword_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for pattern in EXPLICIT_KEYWORD_PATTERNS:
        for match in pattern.finditer(text):
            phrases.append(normalize_keyword_phrase(match.group(0)))
    return phrases


def extract_chapter_keywords(
    title: str | None,
    author: str | None,
    pages: list[dict[str, Any]],
    max_keywords: int,
) -> list[str]:
    source_class = "book"

    # All phrases, weighted by appearance count and position
    phrase_counts: Counter[str] = Counter()
    title_terms = set(keyword_phrase_tokens(title or ""))

    text = " ".join(
        chapter_summary_text(page) for page in pages
    )
    add_keyword_phrases(
        phrase_counts, text, 0.2, title_terms, source_class
    )
    if title:
        add_keyword_phrases(
            phrase_counts,
            title,
            5.0,
            title_terms,
            source_class,
        )

    ranked = sorted(
        phrase_counts.items(),
        key=lambda item: (-item[1], -len(item[0].split()), item[0]),
    )

    keywords: list[str] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for phrase, _score in ranked:
        if phrase in BOOK_KEYWORD_SKIP_PHRASES:
            continue
        tokens = phrase.split()
        if len(tokens) > 4:
            continue
        signature = tuple(
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for token in tokens
        )
        if signature in seen_signatures:
            continue
        if len(tokens) == 1 and tokens[0] in KEYWORD_SINGLE_TOKEN_BLACKLIST:
            continue
        seen_signatures.add(signature)
        keywords.append(phrase)
        if len(keywords) >= max_keywords:
            break
    return keywords


def extract_book_keywords(
    title: str | None,
    author: str | None,
    pages: list[dict[str, Any]],
    max_keywords: int,
) -> list[str]:
    phrase_counts: Counter[str] = Counter()
    title_terms = set(keyword_phrase_tokens(title or ""))
    seen_preview_phrases: set[str] = set()
    seen_preview_explicit: set[str] = set()

    if title:
        normalized_title = normalize_keyword_phrase(title)
        if len(normalized_title.split()) >= 2:
            phrase_counts[normalized_title] += 10.0
        for phrase in extract_explicit_keyword_phrases(title):
            phrase_counts[normalize_keyword_phrase(phrase)] += 14.0
    for page in pages:
        preview = cleaned_preview_phrase(page.get("preview", ""))
        if preview and not preview_is_noisy(preview):
            normalized_preview = normalize_keyword_phrase(preview)
            preview_tokens = keyword_phrase_tokens(normalized_preview)
            if 2 <= len(preview_tokens) <= 6 and (
                any(token in KEYWORD_DOMAIN_TOKENS for token in preview_tokens)
                or any(token in title_terms for token in preview_tokens)
            ):
                phrase = " ".join(preview_tokens)
                if phrase not in seen_preview_phrases:
                    seen_preview_phrases.add(phrase)
                    phrase_counts[phrase] += 12.0
                    if phrase in PRIORITY_BOOK_KEYWORDS:
                        phrase_counts[phrase] += 8.0
            for phrase in extract_explicit_keyword_phrases(preview):
                normalized = normalize_keyword_phrase(phrase)
                if normalized not in seen_preview_explicit:
                    seen_preview_explicit.add(normalized)
                    phrase_counts[normalized] += 16.0
                if normalized in PRIORITY_BOOK_KEYWORDS:
                    phrase_counts[normalized] += 10.0

    # Early structural headings are strong topical signals for books.
    for page in pages[: min(len(pages), 140)]:
        preview = cleaned_preview_phrase(page.get("preview", ""))
        if not preview or preview_is_noisy(preview):
            continue
        phrase = normalize_keyword_phrase(preview)
        tokens = keyword_phrase_tokens(phrase)
        if not (2 <= len(tokens) <= 6):
            continue
        if phrase in BOOK_KEYWORD_SKIP_PHRASES:
            continue
        if sum(1 for token in tokens if token in KEYWORD_PHRASE_GENERIC_TOKENS) >= len(tokens) - 1:
            continue
        if any(token in title_terms for token in tokens):
            phrase_counts[phrase] += 10.0
        if sum(1 for token in tokens if token in KEYWORD_DOMAIN_TOKENS) >= 2:
            phrase_counts[phrase] += 8.0

    for page in pages[: min(len(pages), 80)]:
        preview = compact_whitespace(page.get("preview", "")).lower()
        text = compact_whitespace(page.get("text", ""))
        if len(text) < 120:
            continue
        if preview == "preface" or preview.startswith("contents") or "plan of this book" in preview:
            for phrase in extract_explicit_keyword_phrases(text[:5000]):
                normalized = normalize_keyword_phrase(phrase)
                phrase_counts[normalized] += 10.0
                if normalized in PRIORITY_BOOK_KEYWORDS:
                    phrase_counts[normalized] += 10.0
        elif page_noise_penalty(page, "book") < 8:
            for phrase in extract_explicit_keyword_phrases(text[:1800]):
                normalized = normalize_keyword_phrase(phrase)
                phrase_counts[normalized] += 4.0
                if normalized in PRIORITY_BOOK_KEYWORDS:
                    phrase_counts[normalized] += 6.0

    ranked = sorted(
        phrase_counts.items(),
        key=lambda item: (-item[1], -len(item[0].split()), item[0]),
    )

    keywords: list[str] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for phrase, _score in ranked:
        phrase = normalize_keyword_phrase(phrase)
        if phrase in BOOK_KEYWORD_SKIP_PHRASES:
            continue
        tokens = phrase.split()
        if len(tokens) > 4:
            continue
        signature = tuple(token[:-1] if token.endswith("s") and len(token) > 4 else token for token in tokens)
        if signature in seen_signatures:
            continue
        if len(tokens) == 1 and tokens[0] in KEYWORD_SINGLE_TOKEN_BLACKLIST:
            continue
        seen_signatures.add(signature)
        keywords.append(phrase)
        if len(keywords) >= max_keywords:
            break
    return keywords


def summarize_chapter_pages(chapter_title: str, pages: list[dict[str, Any]], max_sentences: int = 3) -> str:
    title_terms = set(informative_tokens(chapter_title or ""))
    profile = topic_profile(chapter_title, pages, None)
    candidate_pages = [
        page
        for page in pages[: min(len(pages), 8)]
        if len(compact_whitespace(page.get("text", ""))) >= 120 and page_noise_penalty(page, "book") < 10
    ]
    if not candidate_pages:
        candidate_pages = sorted(
            pages,
            key=lambda page: (
                -page_summary_score(page, title_terms, profile, None),
                page.get("page_number", 0),
            ),
        )[:6]

    sentence_candidates: list[tuple[float, str]] = []
    for page in candidate_pages:
        chapter_text = chapter_summary_text(page)
        for raw_sentence in SENTENCE_RE.split(chapter_text):
            sentence = compact_whitespace(raw_sentence)
            if len(sentence) < 60 or len(sentence) > 320:
                continue
            if sentence_is_structural_noise(sentence):
                continue
            lowered = sentence.lower()
            terms = set(informative_tokens(sentence))
            score = sentence_summary_score(sentence, title_terms, profile, None)
            if lowered.startswith("chapter "):
                score -= 12.0
            if title_terms:
                score += sum(1.5 for token in title_terms if token in terms)
            if "this chapter" in lowered or "in this chapter" in lowered:
                score += 4.0
            if "we will" in lowered or "we describe" in lowered or "we discuss" in lowered:
                score += 1.5
            if sum(1 for token in title_terms if token in terms) < 1 and len(terms & set(profile)) < 3:
                score -= 4.0
            if score > 0:
                sentence_candidates.append((score, sentence))

    chosen: list[str] = []
    chosen_terms: set[str] = set()
    for _score, sentence in sorted(sentence_candidates, key=lambda item: (-item[0], item[1])):
        terms = set(informative_tokens(sentence))
        if chosen_terms and len(terms & chosen_terms) >= max(5, len(terms) // 2):
            continue
        chosen.append(sentence)
        chosen_terms.update(terms)
        if len(chosen) >= max_sentences:
            break
    if chosen:
        return " ".join(chosen)
    return chapter_title or "No summary available yet."


def compile_book_chapters(
    doc_id: str,
    title: str | None,
    pages: list[dict[str, Any]],
    max_keywords: int = 10,
) -> list[dict[str, Any]]:
    starts: list[tuple[int, int, str]] = []
    seen_numbers: set[int] = set()
    for index in range(len(pages)):
        info = chapter_start_info(pages, index)
        if not info:
            continue
        chapter_number, chapter_title = info
        if chapter_number in seen_numbers:
            continue
        seen_numbers.add(chapter_number)
        starts.append((index, chapter_number, chapter_title))

    chapters: list[dict[str, Any]] = []
    for pos, (start_index, chapter_number, chapter_title) in enumerate(starts):
        end_index = starts[pos + 1][0] - 1 if pos + 1 < len(starts) else len(pages) - 1
        chapter_pages = pages[start_index : end_index + 1]
        if not chapter_pages:
            continue
        page_start = chapter_pages[0]["page_number"]
        page_end = chapter_pages[-1]["page_number"]
        summary = summarize_chapter_pages(chapter_title, chapter_pages)
        keywords = extract_chapter_keywords(chapter_title, None, chapter_pages, max_keywords)
        section_previews: list[str] = []
        seen_previews: set[str] = set()
        for page in chapter_pages[: min(len(chapter_pages), 12)]:
            preview = cleaned_preview_phrase(page.get("preview", ""))
            info = section_heading_info(preview)
            if not info or info[0] != chapter_number:
                continue
            label = info[1]
            if label in seen_previews:
                continue
            seen_previews.add(label)
            section_previews.append(label)
            if len(section_previews) >= 6:
                break
        chapters.append(
            {
                "chapter_number": chapter_number,
                "title": chapter_title,
                "page_start": page_start,
                "page_end": page_end,
                "summary": summary,
                "keywords": keywords,
                "wiki_link": f"[[source/{doc_id}#p{page_start}]]",
                "section_previews": section_previews,
            }
        )
    return chapters


def book_overview_pages(pages: list[dict[str, Any]], title_terms: set[str], profile: Counter[str]) -> list[dict[str, Any]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for page in pages[: min(len(pages), 60)]:
        text = compact_whitespace(page.get("text", ""))
        if len(text) < 160:
            continue
        preview = compact_whitespace(page.get("preview", "")).lower()
        lowered = text.lower()
        score = -page_noise_penalty(page, "book")
        if preview == "preface" or lowered.startswith("preface "):
            score += 20.0
        if "preface" in preview:
            score += 8.0
        if preview.startswith("1.1 introduction") or preview.startswith("1. introduction"):
            score += 12.0
        elif preview.startswith("chapter 1"):
            score += 4.0
        if any(cue in lowered[:800] for cue in BOOK_PAGE_CUES):
            score += 6.0
        if any(phrase in lowered[:2000] for phrase in BOOK_OVERVIEW_TERMS):
            score += 10.0
        terms = set(informative_tokens(text[:2000]))
        score += sum(2.5 for token in title_terms if token in terms)
        score += sum(min(profile.get(token, 0), 4) * 0.2 for token in terms)
        ranked.append((score, page))
    ranked.sort(key=lambda item: (-item[0], item[1].get("page_number", 0)))
    return [page for score, page in ranked if score > 0][:8]


def summarize_book_pages(title: str | None, pages: list[dict[str, Any]], max_sentences: int = 4) -> str:
    title_terms = set(informative_tokens(title or ""))
    profile = topic_profile(title, pages, "book")
    preface_pages = [
        page
        for page in pages[: min(len(pages), 24)]
        if compact_whitespace(page.get("preview", "")).lower() == "preface"
        or compact_whitespace(page.get("text", "")).lower().startswith("preface ")
    ]
    if preface_pages:
        first_preface_page = preface_pages[0].get("page_number", 0)
        candidate_pages = [
            page
            for page in pages[: min(len(pages), 24)]
            if first_preface_page <= page.get("page_number", 0) <= first_preface_page + 1
        ]
    else:
        candidate_pages = book_overview_pages(pages, title_terms, profile)
    if not candidate_pages:
        candidate_pages = sorted(
            pages[: min(len(pages), 60)],
            key=lambda page: (
                -page_summary_score(page, title_terms, profile, "book"),
                page.get("page_number", 0),
            ),
        )[:8]

    sentence_candidates: list[tuple[float, str]] = []
    for page in candidate_pages:
        text = compact_whitespace(page.get("text", ""))
        for raw_sentence in SENTENCE_RE.split(text):
            sentence = compact_whitespace(raw_sentence)
            if sentence.lower().startswith("preface "):
                sentence = compact_whitespace(sentence[8:])
            if len(sentence) < 70 or len(sentence) > 320:
                continue
            if title and sentence.lower() == title.lower():
                continue
            if title and sentence.lower().startswith((title or "").lower() + " "):
                sentence = compact_whitespace(sentence[len(title or "") :])
            if sentence_is_structural_noise(sentence):
                continue
            lowered = sentence.lower()
            terms = set(informative_tokens(sentence))
            score = sentence_summary_score(sentence, title_terms, profile, "book")
            if title and compact_whitespace(title.lower()) in lowered:
                score += 8.0
            if not any(phrase in lowered for phrase in SUMMARY_CUE_PHRASES + BOOK_OVERVIEW_TERMS):
                score -= 5.0
            if "we assume" in lowered or "we have" in lowered or "we describe" in lowered:
                score += 2.0
            if "this book" in lowered or "this textbook" in lowered or "we wrote this book" in lowered:
                score += 6.0
            if "we shall concentrate" in lowered or "we shall discuss" in lowered:
                score += 4.0
            if "the basic ideas" in lowered or "emphasis on" in lowered:
                score += 4.0
            if "not be covered in this book" in lowered or "interested readers may find" in lowered:
                score -= 20.0
            if "for example" in lowered and "ranging" in lowered:
                score -= 2.0
            if sum(1 for token in title_terms if token in terms) < 1 and len(terms & set(profile)) < 3:
                score -= 6.0
            if score > 0:
                sentence_candidates.append((score, sentence))

    chosen: list[str] = []
    chosen_terms: set[str] = set()
    for _score, sentence in sorted(sentence_candidates, key=lambda item: (-item[0], item[1])):
        terms = set(informative_tokens(sentence))
        if chosen_terms and len(terms & chosen_terms) >= max(5, len(terms) // 2):
            continue
        chosen.append(sentence)
        chosen_terms.update(terms)
        if len(chosen) >= max_sentences:
            break

    if chosen:
        return " ".join(chosen)
    return title or "No summary available yet."


def summarize_paper_pages(
    title: str | None,
    pages: list[dict[str, Any]],
    source_class: str | None = None,
    max_sentences: int = 4,
) -> str:
    # Try to find the abstract on the first couple of pages
    abstract_text = ""
    for page in pages[:2]:
        text = page.get("text", "")
        lowered = text.lower()
        if "abstract" in lowered.replace(" ", ""):
            # Try to find the start of the abstract
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "abstract" in line.lower().replace(" ", ""):
                    # Get the text after "abstract"
                    abstract_text = line[line.lower().rfind("abstract") + 8 :]
                    # and the rest of the lines on the page
                    abstract_text += " ".join(lines[i + 1 :])
                    break
            if abstract_text:
                # The keywords might be mixed in
                if "keywords" in abstract_text.lower():
                    abstract_text = abstract_text.lower().split("keywords")[0]
                # The introduction might follow, so split by "introduction"
                if "introduction" in abstract_text.lower():
                    abstract_text = abstract_text.lower().split("introduction")[0]
                break

    if abstract_text:
        # We have the abstract, so let's use it for the summary
        sentences = SENTENCE_RE.split(abstract_text)
        return " ".join(sentences[:max_sentences])

    # If we didn't find a clear abstract, fall back to the scoring method
    title_terms = set(informative_tokens(title or ""))
    profile = topic_profile(title, pages, source_class)

    candidate_pages = sorted(
        pages[:8],
        key=lambda page: (
            -page_summary_score(page, title_terms, profile, source_class),
            page.get("page_number", 0),
        ),
    )

    sentence_candidates: list[tuple[float, str]] = []
    for page in candidate_pages:
        text = compact_whitespace(page.get("text", ""))
        for raw_sentence in SENTENCE_RE.split(text):
            sentence = compact_whitespace(raw_sentence)
            if len(sentence) < 60 or len(sentence) > 400:
                continue
            if title and sentence.lower() == title.lower():
                continue
            if title and sentence.lower().startswith((title or "").lower() + " "):
                sentence = compact_whitespace(sentence[len(title or "") :])
            score = sentence_summary_score(sentence, title_terms, profile, source_class)
            lowered = sentence.lower()
            if any(phrase in lowered for phrase in PAPER_SUMMARY_CUE_PHRASES):
                score += 5.0
            if "abstract" in lowered:
                score += 10.0
            if "introduction" in lowered:
                score += 2.0
            if score <= 0:
                continue
            sentence_candidates.append((score, sentence))

    chosen: list[str] = []
    chosen_terms: set[str] = set()
    for _score, sentence in sorted(sentence_candidates, key=lambda item: (-item[0], item[1])):
        terms = set(informative_tokens(sentence))
        if chosen_terms and len(terms & chosen_terms) >= max(5, len(terms) // 2):
            continue
        chosen.append(sentence)
        chosen_terms.update(terms)
        if len(chosen) >= max_sentences:
            break

    if chosen:
        return " ".join(chosen)

    return title or "No summary available yet."


def summarize_pages(
    title: str | None,
    pages: list[dict[str, Any]],
    source_class: str | None = None,
    max_sentences: int = 4,
) -> str:
    if source_class == "book":
        return summarize_book_pages(title, pages, max_sentences=max_sentences)
    if source_class == "paper":
        return summarize_paper_pages(title, pages, source_class, max_sentences=max_sentences)

    title_terms = set(informative_tokens(title or ""))
    profile = topic_profile(title, pages, source_class)

    ranked_pages = sorted(
        (
            page
            for page in pages
            if source_class != "book" or page.get("page_number", 0) <= 60
        ),
        key=lambda page: (
            -page_summary_score(page, title_terms, profile, source_class),
            page.get("page_number", 0),
        ),
    )

    sentence_candidates: list[tuple[float, str]] = []
    page_limit = 12 if source_class == "book" else 8
    for page in ranked_pages[:page_limit]:
        text = compact_whitespace(page.get("text", ""))
        for raw_sentence in SENTENCE_RE.split(text):
            sentence = compact_whitespace(raw_sentence)
            if len(sentence) < 60 or len(sentence) > 320:
                continue
            if title and sentence.lower() == title.lower():
                continue
            if title and sentence.lower().startswith((title or "").lower() + " "):
                sentence = compact_whitespace(sentence[len(title or "") :])
            score = sentence_summary_score(sentence, title_terms, profile, source_class)
            if score <= 0:
                continue
            sentence_candidates.append((score, sentence))

    chosen: list[str] = []
    chosen_terms: set[str] = set()
    for _score, sentence in sorted(sentence_candidates, key=lambda item: (-item[0], item[1])):
        terms = set(informative_tokens(sentence))
        if chosen_terms and len(terms & chosen_terms) >= max(5, len(terms) // 2):
            continue
        chosen.append(sentence)
        chosen_terms.update(terms)
        if len(chosen) >= max_sentences:
            break

    if chosen:
        return " ".join(chosen)

    return title or "No summary available yet."


def extract_paper_keywords(
    title: str | None,
    author: str | None,
    pages: list[dict[str, Any]],
    source_class: str | None = None,
    max_keywords: int = 12,
) -> list[str]:
    # First, look for an explicit "Keywords" section
    for page in pages[:2]:
        text = compact_whitespace(page.get("text", ""))
        lowered = text.lower()
        if "keywords:" in lowered:
            # Get the text after "keywords:"
            keywords_text = lowered.split("keywords:")[1]
            # The abstract might follow, so split by "abstract"
            if "abstract" in keywords_text:
                keywords_text = keywords_text.split("abstract")[0]
            # Split by common delimiters
            keywords = re.split(r"[,;]", keywords_text)
            return [kw.strip() for kw in keywords if kw.strip() and len(kw.strip()) < 50]

    phrase_counts: Counter[str] = Counter()
    title_terms = set(keyword_phrase_tokens(title or ""))

    if title:
        add_keyword_phrases(phrase_counts, title, 10.0, title_terms, source_class)

    # First page is likely to contain the abstract
    if pages:
        first_page_text = compact_whitespace(pages[0].get("text", ""))
        add_keyword_phrases(phrase_counts, first_page_text, 5.0, title_terms, source_class)

    ranked = sorted(
        phrase_counts.items(),
        key=lambda item: (-item[1], -len(item[0].split()), item[0]),
    )

    keywords: list[str] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for phrase, _score in ranked:
        phrase = normalize_keyword_phrase(phrase)
        tokens = phrase.split()
        if len(tokens) > 4:
            continue
        signature = tuple(token[:-1] if token.endswith("s") and len(token) > 4 else token for token in tokens)
        if signature in seen_signatures:
            continue
        if len(tokens) == 1 and tokens[0] in KEYWORD_SINGLE_TOKEN_BLACKLIST:
            continue
        seen_signatures.add(signature)
        keywords.append(phrase)
        if len(keywords) >= max_keywords:
            break
    return keywords


def extract_keywords(
    title: str | None,
    author: str | None,
    pages: list[dict[str, Any]],
    source_class: str | None = None,
    max_keywords: int = 12,
) -> list[str]:
    if source_class == "book":
        return extract_book_keywords(title, author, pages, max_keywords)
    if source_class == "paper":
        return extract_paper_keywords(title, author, pages, source_class, max_keywords)

    counts: Counter[str] = Counter()

    def add_tokens(text: str, weight: int) -> None:
        for token in tokenize(text):
            if (
                len(token) < 3
                or token.isdigit()
                or token in STOPWORDS
                or token in KEYWORD_SINGLE_TOKEN_BLACKLIST
            ):
                continue
            counts[token] += weight

    if title:
        add_tokens(title, 5)
    if author:
        add_tokens(author, 2)

    for page in pages[: min(len(pages), 80 if source_class == "book" else 20)]:
        if page_noise_penalty(page, source_class) >= 10:
            continue
        add_tokens(page.get("text", "")[:3000], 1)

    keywords = [token for token, _ in counts.most_common(max_keywords * 3)]
    deduped: list[str] = []
    for keyword in keywords:
        if keyword not in deduped:
            deduped.append(keyword)
        if len(deduped) >= max_keywords:
            break
    return deduped


def query_terms(query: str) -> list[str]:
    return [token for token in tokenize(query) if token not in STOPWORDS and len(token) >= 2]


def score_text(query: str, text: str, weight: float = 1.0) -> float:
    terms = query_terms(query)
    if not terms or not text:
        return 0.0
    haystack = tokenize(text)
    if not haystack:
        return 0.0
    counts = Counter(haystack)
    score = 0.0
    for term in terms:
        occurrences = counts.get(term, 0)
        if occurrences:
            score += weight * (1.0 + min(occurrences - 1, 4) * 0.5)
    lowered = text.lower()
    if compact_whitespace(query.lower()) in lowered:
        score += weight * 3.0
    return score


def page_signal_penalty(preview: str) -> float:
    preview = compact_whitespace(preview)
    if not preview:
        return 4.0

    lowered = preview.lower()
    penalty = 0.0
    if lowered in {"contents", "preface", "index", "acknowledgments"}:
        penalty += 5.0
    if preview.isdigit() or ROMAN_RE.fullmatch(preview):
        penalty += 4.0
    if len(preview) <= 4:
        penalty += 2.0
    if preview.isupper() and len(preview) <= 16:
        penalty += 1.5
    return penalty


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


class KBContext:
    def __init__(self, root: Path | str = "."):
        self.root = Path(root).resolve()

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    @property
    def catalog_path(self) -> Path:
        return self.path("artifacts", "catalog", "sources.json")

    @property
    def extract_dir(self) -> Path:
        return self.path("artifacts", "extract")

    @property
    def compile_dir(self) -> Path:
        return self.path("artifacts", "compile")

    @property
    def wiki_dir(self) -> Path:
        return self.path("wiki")

    @property
    def source_wiki_dir(self) -> Path:
        return self.wiki_dir / "source"

    @property
    def concept_wiki_dir(self) -> Path:
        return self.wiki_dir / "concepts"

    @property
    def synthesis_wiki_dir(self) -> Path:
        return self.wiki_dir / "syntheses"

    @property
    def config_dir(self) -> Path:
        return self.path("config")

    @property
    def overrides_path(self) -> Path:
        return self.config_dir / "source_overrides.json"

    @property
    def search_index_path(self) -> Path:
        return self.compile_dir / "search_index.json"

    @property
    def concept_index_path(self) -> Path:
        return self.compile_dir / "concept_index.json"

    @property
    def chapter_index_path(self) -> Path:
        return self.compile_dir / "chapter_index.json"

    @property
    def source_resolution_path(self) -> Path:
        return self.compile_dir / "source_resolution.json"

    @property
    def source_pages_state_path(self) -> Path:
        return self.compile_dir / "source_pages_state.json"

    def extraction_paths(self, doc_id: str) -> dict[str, Path]:
        doc_dir = self.extract_dir / doc_id
        return {
            "dir": doc_dir,
            "metadata": doc_dir / "metadata.json",
            "pages": doc_dir / "pages.json",
            "full_text": doc_dir / "full.txt",
        }


def load_catalog(context: KBContext) -> dict[str, Any]:
    return load_json(context.catalog_path)


def catalog_documents(context: KBContext) -> list[dict[str, Any]]:
    payload = load_catalog(context)
    return payload["documents"]


def render_yaml_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def render_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append("  -")
                        for item_key, item_value in item.items():
                            lines.append(f"      {item_key}: {render_yaml_value(item_value)}")
                    else:
                        lines.append(f"  - {render_yaml_value(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for item_key, item_value in value.items():
                lines.append(f"  {item_key}: {render_yaml_value(item_value)}")
        else:
            lines.append(f"{key}: {render_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)
