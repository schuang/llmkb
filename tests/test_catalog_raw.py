import pytest
from pathlib import Path

from llmkb.catalog_raw import (
    infer_doc_id,
    choose_canonical,
    infer_source_class,
    apply_override,
)

def test_infer_doc_id():
    slug, year = infer_doc_id(Path("2021-gelman-etal-regression.pdf"))
    assert slug == "2021-gelman-etal-regression"
    assert year == 2021

    slug, year = infer_doc_id(Path("murphy-machine-learning.pdf"))
    assert slug == "murphy-machine-learning"
    assert year is None

def test_choose_canonical():
    entries = [
        {"doc_id": "doc1", "filename": "1999-smith-copy.pdf", "year": 1999},
        {"doc_id": "doc2", "filename": "1999-smith.pdf", "year": 1999},
        {"doc_id": "doc3", "filename": "1999-smith-tmp.pdf", "year": 1999},
    ]
    # "doc2" is preferred because "copy" and "tmp" incur penalties
    assert choose_canonical(entries) == "doc2"

def test_infer_source_class():
    assert infer_source_class({"filename": "book.pdf", "page_count": 200}) == "book"
    assert infer_source_class({"filename": "paper.pdf", "page_count": 15}) == "paper"
    assert infer_source_class({"filename": "something-manual.pdf", "page_count": 50}) == "manual"
    assert infer_source_class({"filename": "some_solution.pdf", "title": "Solutions", "page_count": 200}) == "solution_manual"

def test_apply_override():
    entry = {
        "doc_id": "test-doc",
        "title": "Old Title",
        "year": 2000,
    }
    override = {
        "title": "New Title",
        "author": "Jane Doe",
    }
    apply_override(entry, override)
    
    assert entry["doc_id"] == "test-doc"  # Unchanged
    assert entry["year"] == 2000          # Unchanged
    assert entry["title"] == "New Title"  # Overridden
    assert entry["author"] == "Jane Doe"  # Added
