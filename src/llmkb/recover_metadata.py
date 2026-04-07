#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

from llmkb.kb_common import KBContext, load_json, write_json
from llmkb.catalog_raw import generate_canonical_filename
from llmkb.rename_kb import rename_document

try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

DEFAULT_LLM_MODEL = "openai/gpt-5.4-mini"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use LLM to recover missing metadata for poorly cataloged documents.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL),
        help="LiteLLM model string (e.g. 'openai/gpt-5.4-mini', 'gemini/gemini-2.5-flash', 'ollama/llama3').",
    )
    parser.add_argument(
        "--doc-id",
        help="Run recovery on a specific doc_id rather than all missing docs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the LLM and print the proposed metadata, but do not write overrides or rename the file.",
    )
    return parser.parse_args()


def extract_text_for_llm(context: KBContext, doc_id: str) -> str:
    """Read the first few pages of OCR/extracted text to give to the LLM."""
    pages_path = context.extract_dir / doc_id / "pages.json"
    if not pages_path.exists():
        return ""
    
    payload = load_json(pages_path)
    pages = payload.get("pages", [])
    
    # Grab up to the first 10 pages for scanned books where prefaces hide the title
    text_chunks = [p.get("text", "") for p in pages[:10]]
    combined_text = "\n".join(text_chunks)

    # Cap to ~25k chars to save tokens (Gemini Flash can easily handle this)
    return combined_text[:25000]

def query_llm_metadata(model: str, raw_text: str) -> dict[str, Any] | None:
    """Pass text to LiteLLM and ask it to extract JSON metadata."""
    prompt = f"""
    You are a highly accurate academic librarian. I will provide you with the raw, potentially messy text from the first several pages of a document.
    This text may be from an OCR scan. It often contains tables of contents, prefaces, or copyright pages before the actual title page.

    Your task is to scan through this text and extract the following bibliographic information:
    1. Title: The full title of the document or book.
    2. Author: The list of authors (e.g. "John Smith; Jane Doe").
    3. Year: The 4-digit publication year (e.g. 1985).

    If you cannot find a specific piece of information anywhere in the text, return null for that field.

    Return ONLY a raw JSON object with exactly these keys: "title", "author", "year". Do not wrap it in markdown code blocks like ```json.

    RAW TEXT:
    ================
    {raw_text}
    ================
    """
    try:
        from litellm import completion
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        # Clean up any potential markdown formatting the LLM ignored
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        return json.loads(content.strip())
    except Exception as e:
        print(f"LLM extraction failed: {e}")
        return None

def main() -> None:
    # 1. Load environment variables (precedence: shell env > current dir .env > ~/.env)
    import os
    from dotenv import load_dotenv
    load_dotenv() # Load from CWD if it exists
    load_dotenv(Path.home() / ".env") # Load from Home if it exists (won't overwrite shell/CWD vars)

    if not LITELLM_AVAILABLE:
        print("Error: 'litellm' is not installed. Please run: pip install litellm")
        return

    args = parse_args()

    # 2. Verify API key exists for the selected provider
    model_name = args.model.lower()
    if model_name.startswith("openai/") and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment or ~/.env.")
        print("Please export it or add it to your ~/.env file.")
        return
    if model_name.startswith("gemini/") and not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not found in environment or ~/.env.")
        print("Please export it or add it to your ~/.env file.")
        return

    context = KBContext(args.kb_root)

    if not context.catalog_path.exists():
        print("Catalog not found. Please run 'llmkb-catalog' first.")
        return

    catalog = load_json(context.catalog_path)
    documents = catalog.get("documents", [])

    # Load overrides to update them
    overrides_payload = load_json(context.overrides_path) if context.overrides_path.exists() else {}

    docs_to_process = []
    if args.doc_id:
        docs_to_process = [d for d in documents if d["doc_id"] == args.doc_id]
        if not docs_to_process:
            print(f"Error: doc_id '{args.doc_id}' not found.")
            return
    else:
        # Find documents missing Title or Year
        for doc in documents:
            if doc.get("source_class") == "duplicate" or doc.get("is_redundant"):
                continue
            if not doc.get("title") or not doc.get("year") or not doc.get("author"):
                docs_to_process.append(doc)

    if not docs_to_process:
        print("No documents found with missing metadata.")
        return

    print(f"Found {len(docs_to_process)} document(s) needing metadata recovery. Using model: {args.model}")

    for entry in docs_to_process:
        doc_id = entry["doc_id"]
        print(f"\nProcessing '{doc_id}'...")

        raw_text = extract_text_for_llm(context, doc_id)
        if not raw_text.strip():
            print("  Skipped: No extracted text available. (Run 'llmkb-extract' first).")
            continue

        print("  Querying LLM...")
        recovered_meta = query_llm_metadata(args.model, raw_text)

        if not recovered_meta:
            print("  Failed to query LLM.")
            continue

        print("  Recovered Metadata:")
        print(json.dumps(recovered_meta, indent=4))

        if args.dry_run:
            continue

        # Prepare the override payload
        override_data = overrides_payload.get(doc_id, {})
        recovered_anything = False

        for k in ["title", "author", "year"]:
            # Only apply if LLM actually found a value and it differs from what we already have
            if recovered_meta.get(k) and str(recovered_meta[k]).strip() != "null":
                override_data[k] = recovered_meta[k]
                entry[k] = recovered_meta[k] # Update memory so we can generate the filename
                recovered_anything = True

        if not recovered_anything:
            print("  LLM did not find any useful new metadata. Skipping rename.")
            continue

        
        override_data["metadata_source"] = "llm"
        entry["metadata_source"] = "llm"
        
        overrides_payload[doc_id] = override_data
        
        # Save override immediately so if rename fails we don't lose data
        write_json(context.overrides_path, overrides_payload)
        
        # Calculate new canonical name
        original_ext = Path(entry["path"]).suffix.lower()
        new_filename = generate_canonical_filename(entry, original_ext)
        new_id = Path(new_filename).stem
        
        if new_id != doc_id:
            print(f"  Renaming document to canonical id: '{new_id}'")
            success = rename_document(context, doc_id, new_id, dry_run=False, no_link_update=False)
            if success:
                print("  Rename successful.")
            else:
                print("  Rename failed.")
        else:
            print("  Filename is already canonical. No rename needed.")

    if not args.dry_run:
        print("\nRecovery complete. Please run 'llmkb-update' to refresh the catalog and generated wiki pages.")

if __name__ == "__main__":
    main()
