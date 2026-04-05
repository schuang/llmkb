# Implementation Plan: Automated Metadata Resolution

This document outlines the strategy for implementing high-quality, automated metadata extraction for research papers and books within the `llmkb` engine.

## Objectives
- **Zero-Touch Ingestion**: Automatically retrieve canonical metadata (title, author, year, publisher) when a new PDF is added.
- **Identifier-First**: Prioritize resolving unique identifiers (DOI for papers, ISBN for books) over guessing from filenames.
- **Local-First / Cloud-Light**: Perform identifier extraction locally; use free academic APIs for resolution; only use LLMs as a final fallback.

## The Zero-Touch Ingestion Workflow

The end-to-end process from dropping a raw PDF to a fully synced Zotero library and generated knowledge base follows two primary tracks depending on the document type.

### Track A: Research Papers
1. **PDF Drop**: User places a new paper into `raw/`.
2. **Identification (Local)**: `llmkb-catalog` extracts the first few pages and uses regex to find a **DOI** (e.g., `10.1016/...`).
3. **Query (API)**: The engine queries the free **Crossref API** using the DOI.
4. **Metadata Extraction**: Canonical metadata (Title, Authors, Journal, Year) is retrieved and saved to `sources.json`.
5. **Update Zotero**: The engine generates or updates a local `.bib` (BibTeX) file that Zotero is configured to automatically ingest/sync, bridging the knowledge base back to the reference manager.

### Track B: Books
1. **PDF Drop**: User places a new book into `raw/`.
2. **Identification (Local)**: `llmkb-catalog` extracts the first few pages and uses regex to find an **ISBN** (10 or 13).
3. **Query (API)**: The engine queries the free **Open Library API** (or Google Books API) using the ISBN.
4. **Metadata Extraction**: Canonical metadata (Title, Authors, Publisher, Year) is retrieved and saved to `sources.json`.
5. **Update Zotero**: The engine generates or updates the same local `.bib` file, completing the sync.

### Track C: Informal Documents (No DOI/ISBN)
For unpublished manuscripts, random reports, or notes that lack formal identifiers.
1. **PDF Drop**: User places the file into `raw/`.
2. **Identification Fails**: `llmkb-catalog` finds no DOI or ISBN.
3. **Fallback (LLM/Heuristic)**: The engine passes the first few pages to a lightweight LLM to extract a basic Title and Author, or falls back to filename guessing.
4. **Knowledge Base Ingestion**: The document is fully extracted, summarized, and synthesized into `wiki/` pages and concepts alongside formal literature.
5. **Zotero Exclusion**: Because it lacks canonical metadata, the engine deliberately **omits** this document from the `.bib` export. This keeps the Zotero database pristine and reserved strictly for formal citations, while the `kb/` remains a comprehensive "catch-all" research brain. *(Note: Users can manually force a document into the `.bib` export via `source_overrides.json` if they need to cite an unpublished manuscript).*

---

## Phase 0: Managed Ingestion & State-Based Sync
Instead of relying on external file watchers, the engine uses a **Level-Triggered Sync** approach based on filesystem diffing.

### 1. The Sync Engine
Every time `llmkb-update` is run, the engine performs a recursive scan of `raw/` and compares it against the last known state in `artifacts/catalog/sources.json`.
- **Added Files**: New hashes trigger the full identification and resolution pipeline.
- **Moved/Renamed Files**: Files with existing hashes but new paths trigger a link-update across the wiki (no re-extraction required).
- **Deleted Files**: Missing paths trigger the `llmkb-clean` garbage collection.

### 2. Managed Folders
- `raw/incoming/`: Files here are automatically identified. If the file is a duplicate (matching an existing SHA-256 hash in the library), it is moved to `raw/rejected/duplicates/`. Otherwise, it is renamed to a strictly lowercase, dash-separated format (`yyyy-author-short-title.pdf`), and moved to `library/`.
- `raw/library/`: The managed repository for canonicalized files.
- `raw/manual/`: Files here are processed but **never** renamed or moved by the engine.

### 3. The Ingestion Report (Logs)
Every run generates a Markdown report in `wiki/logs/report-YYYY-MM-DD.md`.
- Summarizes all changes (Added, Moved, Deleted).
- Highlights **Warnings**: Files where DOI/ISBN could not be found, or files with corrupted text that need manual attention.

## Phase 1: Identification (Local)
Modify `llmkb/kb_common.py` to include robust extraction logic for identifiers:
- **DOI Pattern**: Scan the first 3 pages for common DOI formats (e.g., `10.xxxx/...`).
- **ISBN Pattern**: Scan the first 5 pages for ISBN-10 and ISBN-13 strings.
- **Trigger**: Enhance `llmkb-catalog` to perform a "light extraction" of the first few pages of any new PDF to look for these identifiers.

## Phase 2: Resolution (API)
Create a new module `src/llmkb/metadata_resolver.py` to interface with free APIs:
- **Paper Resolution (Crossref API)**: 
  - Input: DOI
  - Output: Canonical Title, Authors (list), Year, Journal, Publisher.
- **Book Resolution (Open Library / Google Books API)**:
  - Input: ISBN
  - Output: Canonical Title, Authors (list), Year, Publisher.

## Phase 3: Fallback (LLM)
Implement a lightweight LLM task for documents where Phase 1/2 fail:
- Pass the text from the first 2 pages to an LLM.
- Use a strict JSON schema to extract title, authors, and year.

## Phase 4: Pipeline Integration
Update `llmkb-catalog` (`catalog_raw.py`):
1. Find a new PDF.
2. Extract identifiers (DOI/ISBN).
3. If found, query API and populate `sources.json`.
4. If not found, run LLM fallback.
5. If all fail, fall back to current filename/PDF-metadata guessing.

## Phase 5: Zotero Integration
Create a new module `src/llmkb/export_bibtex.py`:
1. Read the newly resolved canonical metadata from `sources.json`.
2. Format the metadata into a standard `.bib` (BibTeX) file (e.g., `artifacts/compile/library.bib`).
3. Allow Zotero or other reference managers to "Subscribe" or "Auto-sync" with this file, enabling a one-way bridge from `llmkb`'s metadata resolution into the user's reference library.

## Data Schema Updates
The `sources.json` and source markdown frontmatter should be updated to store:
- `doi`: String (optional)
- `isbn`: String (optional)
- `metadata_source`: String (e.g., "crossref", "openlibrary", "llm", "heuristic")
