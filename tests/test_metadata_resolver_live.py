import os
import pytest
from llmkb.metadata_resolver import resolve_doi, resolve_isbn

# Skip all tests in this module if LLMKB_LIVE_TESTS is not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("LLMKB_LIVE_TESTS"),
    reason="Live API tests are slow and disabled by default. Set LLMKB_LIVE_TESTS=1 to run."
)

def test_live_resolve_doi_crossref():
    """Test resolving a real DOI against the live Crossref API."""
    # Moser 1999 (Physics of Fluids)
    doi = "10.1063/1.869966"
    result = resolve_doi(doi)
    
    assert result is not None
    assert result["title"] == "Direct numerical simulation of turbulent channel flow up to Reτ=590"
    assert "Robert D. Moser" in result["author"]
    assert "John Kim" in result["author"]
    assert "Nagi N. Mansour" in result["author"]
    assert result["year"] == 1999
    assert result["journal"] == "Physics of Fluids"
    assert result["publisher"] == "AIP Publishing"
    assert result["metadata_source"] == "crossref"

def test_live_resolve_doi_datacite():
    """Test resolving a real arXiv DOI against the live DataCite API."""
    # Vaswani et al. 2017 (Attention Is All You Need)
    doi = "10.48550/arXiv.1706.03762"
    result = resolve_doi(doi)
    
    assert result is not None
    assert result["title"] == "Attention Is All You Need"
    assert "Ashish Vaswani" in result["author"]
    assert "Noam Shazeer" in result["author"]
    assert result["year"] == 2017
    assert "arXiv" in result["journal"]
    assert "arXiv" in result["publisher"]
    assert result["metadata_source"] == "datacite"

def test_live_resolve_isbn_13():
    """Test resolving a real ISBN-13 against the live Open Library API."""
    # We use a 2006 book here because OpenLibrary doesn't always have brand new textbooks indexed.
    isbn = "9783540307044"
    result = resolve_isbn(isbn)
    
    assert result is not None
    assert "seventeen provers of the world" in result["title"].lower()
    assert "Dana S. Scott" in result["author"]
    assert result["year"] == 2006
    assert result["metadata_source"] == "openlibrary"

def test_live_resolve_isbn_10():
    """Test resolving a real ISBN-10 against the live Open Library API."""
    # Aris (Vectors, tensors, and the basic equations of fluid mechanics)
    isbn = "0486661105"
    result = resolve_isbn(isbn)
    
    assert result is not None
    assert "Vectors, tensors, and the basic equations of fluid mechanics" in result["title"]
    assert "Rutherford Aris" in result["author"]
    assert result["year"] == 1989
    assert "Dover" in result["publisher"]
    assert result["metadata_source"] == "openlibrary"
