# llmkb

[![Unit Tests](https://github.com/schuang/llmkb/actions/workflows/test.yml/badge.svg)](https://github.com/schuang/llmkb/actions/workflows/test.yml)

A specialized command-line engine for building and maintaining a personal research wiki from a collection of raw academic documents (PDF, ePub, Word, etc.).

**Deterministic Retrieval, Probabilistic Synthesis**: This engine provides the rigid, trustworthy framework required to organize thousands of sources with perfect page-level provenance, while utilizing LLMs to perform high-level summarization and concept aggregation.

## Core Features

- **Automated Metadata**: Resolves DOI/ISBN identifiers via academic APIs (Crossref, Open Library).
- **Multi-Format Support**: Native processing for PDF, ePub, Microsoft Word, Markdown, and HTML.
- **OCR Fallback**: Automatically detects scanned image-only PDFs and extracts text using Tesseract.
- **Managed Ingestion**: Auto-renaming and de-duplication at the folder level.
- **Zettelkasten-Ready**: Generates Obsidian-style Markdown pages with stable internal links.
- **Data/Code Separation**: Keeps your private research data separate from the execution logic.
- **Level-Triggered Sync**: Efficiently handles moves, renames, and deletions via hash-based diffing.

## Installation

The engine is designed as a standalone Python package.

```bash
# 1. Clone the engine
git clone https://github.com/schuang/llmkb.git
cd llmkb

# 2. Setup environment (e.g. venv or conda)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode
pip install -e .
```

## Quick Start

1. **Prepare your KB**: Create a data directory with a `raw/incoming/` folder.
2. **Add Files**: Drop your research PDFs into `raw/incoming/`.
3. **Run Update**:
   ```bash
   cd /path/to/your/knowledge-base
   llmkb-add
   ```

The engine will automatically catalog your files, extract their text, and generate a searchable research wiki in the `wiki/` directory.

## Documentation

- **[User Manual](docs/user-manual.md)**: Daily workflows for adding, renaming, moving, and deleting documents.
- **[Architecture & Pipeline](docs/architecture.md)**: The system design, pipeline stages, and "Librarian vs. Researcher" philosophy.
- **[Schema Reference](docs/schema.md)**: Specifications for JSON artifacts and generated Markdown.
- **[Multi-Format Plan](docs/multi-format-support.md)**: The technical roadmap for non-PDF document support.

## CLI Reference

- `llmkb-add`: Runs the full end-to-end update pipeline.
- `llmkb-add`: Scans files (inc. `raw/incoming/`), resolves metadata, auto-renames/moves, and builds the manifest.
- `llmkb-clean`: Garbage collects artifacts and wiki pages for removed files.
- `llmkb-recover-metadata`: Uses an LLM to recover missing metadata from OCR'd text and automatically rename files.
- `llmkb-rename`: Safely renames a `doc_id` and heals all wiki links.
- `llmkb-test-metadata`: Utility to test live API resolution for a DOI/ISBN.
- `llmkb-search`: Natural-language search across the generated knowledge base.
- `llmkb-zotero-sync`: Two-way API bridge state manager with one-way sync policy (`local -> Zotero`) using `pyzotero`.

## Zotero API Sync (pyzotero)

This project now supports direct Zotero Web API sync via `pyzotero` using a local mapping state (`artifacts/zotero/sync_state.json`).

### 1. Set credentials

Store credentials in `.env` (project) or `~/.env`:

```bash
ZOTERO_API_KEY=...
ZOTERO_USER_ID=...
# or:
# ZOTERO_LIBRARY_ID=...
```

### 2. Initialize sync config

From your KB root:

```bash
llmkb-zotero-sync --kb-root /path/to/your/knowledge-base --init-config
```

Then edit `config/zotero_sync.json`:
- Set `library_type` to `user` or `group`.
- Optionally set `library_id` directly (otherwise it is read from env).
- Optional `collection_key` to target a specific Zotero collection.
- `include_attachments` controls linked-file attachment creation.
- `min_request_interval_ms` controls pacing (default `1000`) to reduce rate-limit risk.

### 3. Bootstrap safely

Preview first:

```bash
llmkb-zotero-sync --kb-root /path/to/your/knowledge-base --dry-run
```

Run a small initial batch:

```bash
llmkb-zotero-sync --kb-root /path/to/your/knowledge-base --limit 20
```

Then run full sync:

```bash
llmkb-zotero-sync --kb-root /path/to/your/knowledge-base
```

### 4. Ongoing usage

Re-run `llmkb-zotero-sync` after local add/rename/delete operations to keep Zotero consistent with local state.

Current policy is one-way source of truth: local catalog drives Zotero updates/deletes/creates.
