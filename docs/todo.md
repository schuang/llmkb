# LLM Knowledge Base Todo

This document tracks unfinished tasks, design gaps, and future improvements for the LLM Knowledge Base Engine.

## Metadata and Extraction
- [x] Implement automated identification of DOI (papers) and ISBN (books) in raw text.
- [x] Build `metadata_resolver.py` to query Crossref and Open Library APIs.
- [x] Integrate API resolution into `llmkb-catalog`.
- [x] **Multi-Format Support**: Update `catalog_raw.py` to scan for `.epub`, `.docx`, `.md`, `.txt`, `.rst`, `.html`.
- [x] Implement LLM-based metadata extraction fallback.
- [x] **Unified Extraction**: Refactor `extract_pages.py` to use `pandoc` for non-PDF formats.
- [x] **Section Chunking**: Implement logical heading-based chunking for reflowable formats in `extract_pages.py`.
- [x] **OCR Fallback (Tesseract)**: Implement automatic detection of image-only scanned PDFs (e.g., extremely low text-to-page ratio). Convert pages to images via `pdftoppm` and extract text using `tesseract`. Add `ocr_extracted` to `quality_flags` to warn downstream LLM tasks of potential transcription errors.
- [x] Implement author normalization (currently inconsistent).
- [x] Refine near-duplicate detection heuristics (implemented path-aware Duplicate Shield and immediate rename pruning).
- [ ] Add richer extraction quality fields/flags to metadata.

## Content Generation
- [x] Reduce noise in source summaries (integrated LLM semantic summarization).
- [x] **Map-Reduce Book Summarization**: Implemented gated chapter-by-chapter summarization to capture whole-book context without token limit issues.
- [ ] Improve concept candidate selection and naming.
- [ ] Add generated timestamps to all markdown page types (currently missing on some).
- [ ] Implement normalized `kind` and `status` fields for synthesis pages.

## Incremental Updates
- [x] Improve state tracking for incremental rebuilds (implemented hash-based state comparison in `catalog_raw.py`).
- [x] **Ingestion Reports**: Automatically generate Markdown reports in `wiki/logs/` summarizing all changes and step outputs.
- [x] Add richer incremental patching (implemented search index caching and keyword-based concept generation for instant updates).

## Synthesis and Q&A
- [ ] Add higher-quality synthesis workflows using LLMs over retrieved evidence.
- [ ] Implement concept-to-concept relationship refinement beyond simple source-overlap heuristics.
- [ ] Develop more advanced retrieval strategies for complex research questions.

## Tooling and Infrastructure
- [x] Add a dummy test suite with public-domain PDFs (implemented `tests/` with unit and live API mocks).
- [x] **Managed Ingestion**: Implement auto-renaming and moving from `raw/incoming/` to `raw/library/`.
- [x] **Duplicate Shield**: Prevent duplicate files from being added during ingestion.
- [x] **Zotero Integration**: Create `src/llmkb/export_bibtex.py` to generate a `.bib` file from the catalog for Zotero import.
- [x] **Soft Deletion (`llmkb-reject`)**: Implement a CLI command to safely archive/reject low-quality sources.
- [ ] Add linting and formatting (e.g., `ruff`, `black`) to the engine codebase.
- [ ] Consider migrating from `argparse` to a more robust CLI framework (e.g., `Click` or `Typer`).
