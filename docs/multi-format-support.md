# Implementation Plan: Multi-Format Support

This document outlines the strategy for expanding `llmkb` to support multiple document formats beyond PDF, including ePub, Microsoft Word, Markdown, Text, reStructuredText, and HTML.

## Objectives
- **Format Agnostic**: Support a diverse library of document types.
- **Unified Citation Model**: Maintain the `[[source/doc_id#p123]]` citation convention across all formats, using "Virtual Pages" for non-paginated files.
- **Standardized Extraction**: Use Pandoc as the primary engine for converting non-PDF formats into structured text.

## Phase 1: Catalog Expansion
Modify `src/llmkb/catalog_raw.py`:
- **Recursive Scan**: Update the scanner to include extensions: `.pdf`, `.epub`, `.docx`, `.md`, `.txt`, `.rst`, `.html`, `.htm`.
- **Metadata Extraction**:
  - **ePub**: Extract metadata using internal XML structures or Pandoc.
  - **Markdown/rST**: Look for YAML frontmatter.
  - **Word**: Extract basic properties (Author, Title, Created Date) via Pandoc or specialized libraries.
  - **HTML**: Extract `<meta>` tags or `<title>`.

## Phase 2: Unified Extraction (Pandoc)
Refactor `src/llmkb/extract_pages.py`:
- **Dispatcher**: Determine extraction method based on file extension.
- **PDF Path**: Continue using `pdftotext` for native page-boundary extraction.
- **Reflowable Path (ePub, Word, HTML, etc.)**: 
  - Call `pandoc` to convert the source into a standardized Markdown intermediate.
  - **Section-Based Chunking**: Split the resulting text into discrete "chunks" based purely on structural headings (e.g., `#` and `##`), NOT arbitrary word counts or estimated pages.
- **Output**: Ensure all formats produce the same `pages.json` schema, allowing the rest of the pipeline (summarization, concept synthesis) to remain unchanged.

## Phase 3: Section-Based Citations
Define the citation logic in `src/llmkb/kb_common.py`:
- **Heading Anchors**: For non-PDF formats, the "page number" field in the schema is replaced with or mapped to the semantic section heading slug (e.g., `intro`, `chapter-1`).
- **Citation Model**: Maintain the `#` anchor format, but use semantic slugs for reflowable text so Obsidian links remain accurate and logically sound regardless of the viewer's screen size or font settings.
  - **PDF**: `[[source/doc_id#p123]]`
  - **ePub/Word/MD**: `[[source/doc_id#introduction]]` or `[[source/doc_id#chapter-2]]`

## Data Schema Updates
- `source_format`: New field in `sources.json` and wiki frontmatter (e.g., "pdf", "epub", "docx").
- `is_paginated`: Boolean flag indicating if the source has physical pages (`true` for PDF, `false` for ePub/Word/MD).

## Tooling Requirements
- **Pandoc**: Must be installed on the host system to process non-PDF files.
