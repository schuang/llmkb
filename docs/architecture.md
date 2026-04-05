# LLM Knowledge Base Architecture

## Goals

- Keep `raw/` as the immutable source of truth.
- Build a personal research wiki that is primarily maintained by an LLM.
- Support a wide range of formats: PDF, ePub, Microsoft Word, Markdown, Text, HTML, and more.
- Preserve all source files, including duplicates, excerpts, and manual overrides.
- Make provenance explicit enough that citations remain trustworthy (using "Section-Based Citing" for non-paginated formats).
- Separate the execution engine (code) from the knowledge base (data).

## System Design: Code vs. Data

 The system is refactored into two distinct repositories to separate the general-purpose execution engine from personal data.

### 1. The Engine (`llmkb`)
Contains all the Python logic, CLI tools, and schema definitions. It is designed to be a reusable tool that can be run against any compatible data directory.

### 2. The Data Repository (Knowledge Base)
Contains your private source PDFs, configuration overrides, intermediate artifacts, and the final generated Markdown wiki.
## Repository Layout (Knowledge Base Root)

```text
raw/                     Original source files (PDFs)
  incoming/              Inbox for new, unorganized files
  library/               Managed area for automatically renamed files
  manual/                Archive for files with manually curated names
artifacts/
...
  catalog/               Machine-readable manifests about raw sources
  extract/               Extracted text, page splits, PDF metadata
  compile/               Intermediate products (search indices, chapter indices)
config/
  source_overrides.json  Manual metadata corrections and source-class overrides
wiki/
  source/                One markdown page per canonical source
  concepts/              LLM-authored concept pages
  syntheses/             Research notes and comparisons
docs/                    Project-specific notes and logs
```

## Source Model

Each raw file gets a stable `doc_id`, initially derived from the filename or automatically generated during managed ingestion. The source catalog tracks document metadata, hash, identifiers (DOI/ISBN), and relationships.

See [schema.md](schema.md) for the detailed file formats and data structures.

## Manual Notes & Personal Knowledge Management
The `wiki/source/` and `wiki/concepts/` directories are **managed entirely by the engine**. If you manually type notes into `wiki/source/canuto-spectral-methods.md`, they will be completely obliterated the next time you run `llmkb-update --force`.

To preserve your manual notes, the system relies on a strict **Zettelkasten-style workflow**:
- **Your Domain**: You create your own personal markdown files anywhere *outside* of the `source/` and `concepts/` folders (e.g., `wiki/my-notes/` or directly in the root of your Obsidian vault).
- **The Engine's Domain**: The engine provides the immutable evidence base.
- **The Workflow**: When you are reading the Canuto book and have an insight, you write it in *your* note, and then you cite the engine's evidence using a block reference:
  > *"Canuto argues that the Galerkin method is superior here `[[source/canuto-spectral-methods#p115]]` because it explicitly enforces boundary conditions."*

This guarantees that the engine can ruthlessly regenerate, optimize, and update its catalog without ever risking a single character of your personal human-authored research.

## Canonicalization Rules

1. Exact duplicates are detected by file hash.
2. Near-duplicate sources are detected from extracted text.
3. One document in each duplicate set is selected as canonical.
4. Redundant copies are retained as stubs in the wiki, pointing to the canonical source.

## Citation Model

The default citation target is page-level using Obsidian-style anchors:
- Source page: `[[source/<doc_id>]]`
- Page anchor: `[[source/<doc_id>#p123]]`

## Build Pipeline

The pipeline consists of five major stages:
1. **Catalog**: Scans `raw/` (recursively, multiple formats), extracts identifiers (DOI, ISBN), resolves metadata via academic APIs, and builds `artifacts/catalog/sources.json`.
2. **Extraction**: Extracts text and metadata into `artifacts/extract/<doc_id>/`. Uses `pdftotext` for PDFs and `pandoc` for reflowable formats (ePub, Word, etc.).
3. **Source Pages**: Generates `wiki/source/<doc_id>.md` and chapter-level data.
4. **Concept Compilation**: Aggregates sources into `wiki/concepts/*.md`.
5. **Synthesis**: CLI-driven creation of research notes in `wiki/syntheses/`.

## Incremental Ingest

The system supports incremental updates. Only new or changed files are re-processed. State is tracked via hashes and timestamps in `artifacts/compile/`.

### Automated Ingestion (State-Based Sync)
To achieve a "zero-touch" workflow without external dependencies, the engine uses a **Level-Triggered Sync** approach. 

Every time `llmkb-update` is run:
1. **Scan**: The engine performs a recursive filesystem scan of the `raw/` directory.
2. **Diff**: It compares the scan results against the last known state in `artifacts/catalog/sources.json`.
3. **Analyze**: By comparing SHA-256 hashes and file paths, it distinguishes between new additions, deletions, and moves/renames.
4. **Report**: It generates an **Ingestion Report** in `wiki/logs/` documenting all changes and highlighting any documents that require manual metadata correction.

Because the engine is fully incremental, this state comparison happens in seconds, even for libraries with thousands of documents.

## LLM Boundaries

The defining philosophy of this architecture is **Deterministic Retrieval, Probabilistic Synthesis**. We never want the LLM deciding what page a quote is on (it will hallucinate). Instead, we use Python scripts to find the quote, hand it to the LLM with a hardcoded citation attached, and ask it to synthesize the text.

### Deterministic Logic (The Librarian / Code)
The scripts create a rigid, highly reliable framework that never hallucinates facts, paths, or relationships:
- **Ingestion & Fingerprinting**: Scanning the `raw/` folder (PDF, ePub, Word, MD, etc.), reading native metadata, and computing SHA-256 hashes.
- **Duplicate Detection**: Finding exact matches (via hash) and near-duplicates (via text-shingling).
- **Text Extraction**: Ripping raw text using format-aware tools (`pdftotext`, `pandoc`). Includes an automatic **OCR Fallback (Tesseract)**: if a PDF is detected as a scanned image (zero selectable text), the engine automatically converts the pages to high-resolution images and transcribes them.
- **Section Paging**: Creating stable semantic chunks for non-paginated formats (ePub, HTML, etc.) based purely on header structure, avoiding arbitrary virtual pages.
- **Structural Heuristics**: Using Regex to find chapter headings or extracting explicit phrases based on domain keywords.
- **State Management & Pathing**: Resolving `KBContext` paths, managing JSON artifacts, and orchestrating the update pipeline.
- **Link Generation**: Generating exact, functional Obsidian-style markdown links (e.g., `[[source/canuto-spectral-methods#p115]]`) that guarantee provenance.

### Probabilistic Logic (The Researcher / LLM)
Once the deterministic scripts have built a perfectly cited, text-searchable evidence pack, the LLM performs the heavy cognitive lifting:
- **Metadata Recovery**: Reading noisy OCR text from old scanned images to probabilistically identify missing titles, authors, and publication years, seamlessly bridging the gap back to deterministic renaming.
- **Semantic Summarization**: Reading dense introductions and synthesizing concise, high-level summaries for `wiki/source/` pages.
- **Classification Refinement**: Taking heuristically classified documents (e.g., "unknown" or "book") and intelligently categorizing them (e.g., "textbook," "monograph," "solution manual").
- **Concept Extraction & Naming**: Looking across the corpus, recognizing that multiple sources discuss the same underlying idea (despite different terminology), and generating unified "Concept Page" titles and summaries.
- **Synthesis & Q&A**: Reading the output of `llmkb-compare` (which provides an evidence pack of extracted texts from different books) and writing cohesive essays comparing their methodologies.

## Current Implementation Status

The system is fully functional as a decoupled CLI suite. All stages of the build pipeline are implemented and can be invoked globally or per-document.
- `llmkb-catalog`: Scans files, resolves metadata, and builds the manifest.
- `llmkb-clean`: Garbage collects artifacts for removed files.
- `llmkb-recover-metadata`: Uses an LLM to recover missing metadata from OCR'd text and triggers an auto-rename.
- `llmkb-rename`: Safely renames doc_ids and updates all wiki links.
- `llmkb-extract`: Extracts text and metadata (format-aware).
- `llmkb-resolve`: Identifies exact and near-duplicates.
- `llmkb-build-source`: Generates source markdown pages.
- `llmkb-build-concept`: Aggregates sources into topic pages.
- `llmkb-search`: Natural-language retrieval.
- `llmkb-test-metadata`: CLI utility to test live API resolution.
- `llmkb-update`: End-to-end pipeline orchestrator.
