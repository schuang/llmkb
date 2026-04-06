# LLM Knowledge Base - User Manual

This manual describes the day-to-day workflows for managing documents in your knowledge base (`kb`). The `llmkb` engine is designed to act as an automated digital librarian, minimizing manual data entry while maintaining perfectly connected Markdown notes.

---

## Installation & Setup

Before running any commands, you must ensure the `llmkb` Python package is installed and your virtual environment is active.

1. **Activate the Virtual Environment**:
   Navigate to the engine repository and activate the environment:
   ```bash
   cd ~/work/llmkb
   source .venv/bin/activate
   ```
   *(Note: Adjust `.venv` to match your specific environment name, e.g., `miniforge` or `conda` if applicable).*

2. **Install the Engine**:
   Install the engine in "editable" mode so updates are applied instantly:
   ```bash
   pip install -e .
   ```

3. **External Dependencies**:
   Ensure you have the following system utilities installed:
   - `poppler-utils` (provides `pdftotext` and `pdfinfo` for PDFs).
   - `pandoc` (for ePub, Word, and Markdown extraction).
   - `tesseract-ocr` (for automatically extracting text from scanned image-only PDFs).

Once activated, all `llmkb-*` commands are available globally in your terminal.

---

## Key Directories: Where to put your files

The engine organizes your physical files into three distinct zones within the `raw/` directory. Understanding these zones is the key to using the system effectively:

- **`raw/incoming/` (The Inbox)**: Drop new, unorganized files here. The engine will automatically identify them, pull their metadata from the internet, rename them to a clean format (`yyyy-author-short-title.pdf`), and move them into `library/`.
- **`raw/library/` (The Managed Zone)**: The automated repository. Files here have been cleanly named and organized by the engine. You should not manually rename files in this folder.
- **`raw/manual/` (The Human Zone)**: Your safe archive. If you have files you have already named perfectly, or informal documents (like personal memos) where auto-renaming doesn't make sense, put them here. The engine will extract their text and synthesize them into your wiki, but it will **never** alter their filenames.

---

## Scenario 1: Adding a New Document

**The Goal**: You downloaded a new research paper or book and want to add it to your knowledge base.

**The Action**: 
Copy or move the raw file (e.g., `random_download_123.pdf`) into the **`raw/incoming/`** directory.

**The Command**:
Run the update orchestrator from the root of your knowledge base:
```bash
llmkb-update
```

**The Consequences (What Happens)**:
1. **Duplicate Shield**: The engine immediately computes the SHA-256 hash of the file. If you already have this exact file in your library, it stops processing and moves the file to `raw/rejected/duplicates/`.
2. **Metadata Resolution**: It extracts the first few pages and scans for a DOI or ISBN. It then queries free academic APIs (Crossref or Open Library) to retrieve the perfect, canonical metadata (Title, Authors, Journal, Year).
3. **Auto-Renaming**: It generates a strict, lowercase, dash-separated filename (e.g., `2017-vaswani-etal-attention-is-all.pdf`).
4. **Moving**: It physically moves the file from `raw/incoming/` to `raw/library/` using the new canonical name.
5. **Processing**: It extracts the full text, generates a `wiki/source/<doc_id>.md` summary page, and uses the LLM to weave its text into your `wiki/concepts/` pages.

*(Note: If the document is an unpublished manuscript without a DOI/ISBN, the engine falls back to heuristic/LLM extraction, but still processes it into your wiki).*

---

## Scenario 2: Renaming a Document

**The Goal**: You want to change the filename (and consequently, the `doc_id`) of a document that is already in your `raw/library/` or `raw/manual/` folders.

**The Action**: 
**DO NOT** rename the file using your operating system's file explorer. Doing so will orphan your extracted text and break all existing `[[source/doc_id]]` links in your Obsidian notes.

**The Command**:
Use the built-in rename tool:
```bash
llmkb-rename <old-doc-id> <new-doc-id>
```
*(Tip: You can add `--dry-run` to the end of this command to see exactly what will be modified without actually changing anything).*

**The Consequences (What Happens)**:
1. **File Rename**: The physical file in `raw/library/` is renamed.
2. **Artifact Migration**: The heavy extracted text folders in `artifacts/extract/` are renamed, preventing you from having to re-run expensive text extraction.
3. **Wiki Page Rename**: The `wiki/source/<old-id>.md` page is renamed.
4. **Link Healing**: The engine recursively scans your **entire** `wiki/` directory (including your personal manual notes) and performs a find-and-replace, updating every `[[source/<old-id>]]` link to `[[source/<new-id>]]`. Your notes will never break.

---

## Scenario 3: Deleting a Document

**The Goal**: A document is low-quality, irrelevant, or no longer needed, and you want to completely remove it from your knowledge base.

**The Action**: 
Delete the physical PDF file from the `raw/library/` (or `raw/manual/`) directory using your operating system's file explorer (e.g., move it to your computer's Trash).

**The Command**:
Run the update orchestrator:
```bash
llmkb-update
```

**The Consequences (What Happens)**:
1. **Catalog Update**: The `llmkb-catalog` step notices the file is missing from the disk and removes it from the master `sources.json` manifest.
2. **Garbage Collection**: The `llmkb-clean` step detects that the document is no longer in the catalog. It automatically deletes the orphaned `artifacts/extract/<doc_id>/` folder (freeing up disk space) and deletes the `wiki/source/<doc_id>.md` page.
3. **Concept Scrubbing**: During the `llmkb-build-concept` phase, the engine rebuilds the concept pages without the deleted document, cleanly erasing its presence from the synthesized knowledge base.

---

## Scenario 4: Moving a Document (Without Renaming)

**The Goal**: You want to move a file from `raw/library/` to `raw/manual/` so the engine stops trying to manage its filename.

**The Action**:
Move the physical file using your operating system's file explorer.

**The Command**:
Run the update orchestrator:
```bash
llmkb-update
```

**The Consequences (What Happens)**:
1. **Hash Matching**: The cataloger sees a "Missing" file at the old path and a "New" file at the new path. Because the SHA-256 hash is identical, the engine immediately recognizes it's the exact same file.
2. **Path Update**: It simply updates the `path` field in `sources.json`. It **does not** re-extract the text or consume any LLM tokens. All your existing Markdown links continue to work flawlessly because the `doc_id` did not change.

---

## Scenario 5: Rejecting/Archiving a Document

**The Goal**: You want to remove a low-quality or irrelevant document from your active wiki and search index, but you want to keep the physical file in a "rejected" folder rather than deleting it.

**The Action**:
Run the rejection command with the `doc_id` of the document.

**The Command**:
```bash
llmkb-reject <doc_id> --reason "Irrelevant content"
```

**The Consequences (What Happens)**:
1. **File Move**: The physical file is moved from its current location (e.g., `raw/library/`) to **`raw/rejected/`**.
2. **Override Update**: An entry is added to `config/source_overrides.json` marking the status as `rejected`. This ensures that even if you manually move the file back, the engine remembers it was rejected.
3. **Automated Cleanup**: You should run `llmkb-update` immediately after. The engine will:
    - Remove the document from the master `sources.json` catalog (because it ignores the `rejected/` folder).
    - Trigger `llmkb-clean` to delete the orphaned extracted text and the generated `wiki/source/` page.
    - Scrub the document from all `wiki/concepts/` pages.
