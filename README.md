# LLM Knowledge Base Engine (`llmkb`)

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
   llmkb-update
   ```

The engine will automatically catalog your files, extract their text, and generate a searchable research wiki in the `wiki/` directory.

## Documentation

- **[User Manual](docs/user-manual.md)**: **Recommended Reading.** Daily workflows for adding, renaming, moving, and deleting documents.
- **[Architecture & Pipeline](docs/architecture.md)**: Deep dive into the system design, pipeline stages, and "Librarian vs. Researcher" philosophy.
- **[Schema Reference](docs/schema.md)**: Detailed specifications for JSON artifacts and generated Markdown.
- **[Multi-Format Plan](docs/multi-format-support.md)**: The technical roadmap for non-PDF document support.

## CLI Reference

- `llmkb-update`: Runs the full end-to-end update pipeline.
- `llmkb-catalog`: Scans files, resolves metadata, and builds the manifest.
- `llmkb-clean`: Garbage collects artifacts and wiki pages for removed files.
- `llmkb-recover-metadata`: Uses an LLM to recover missing metadata from OCR'd text and automatically rename files.
- `llmkb-rename`: Safely renames a `doc_id` and heals all wiki links.
- `llmkb-test-metadata`: Utility to test live API resolution for a DOI/ISBN.
- `llmkb-search`: Natural-language search across the generated knowledge base.
