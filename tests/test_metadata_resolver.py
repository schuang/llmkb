import json
import pytest
from unittest.mock import patch, MagicMock
from llmkb.metadata_resolver import resolve_doi, resolve_isbn

def test_resolve_doi_book():
    """Test (1) resolving a DOI for a book (Canuto)."""
    doi = "10.1007/978-3-540-30704-4"
    mock_response = {
        "message": {
            "title": ["Spectral Methods"],
            "author": [
                {"given": "Claudio", "family": "Canuto"},
                {"given": "M. Y.", "family": "Hussaini"},
                {"given": "Alfio", "family": "Quarteroni"},
                {"given": "Thomas A.", "family": "Zang"}
            ],
            "published-print": {
                "date-parts": [[2006]]
            },
            "publisher": "Springer Berlin Heidelberg",
            "container-title": []
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_doi(doi)
        
        assert result is not None
        assert result["title"] == "Spectral Methods"
        assert "Claudio Canuto" in result["author"]
        assert "Thomas A. Zang" in result["author"]
        assert result["year"] == 2006
        assert result["publisher"] == "Springer Berlin Heidelberg"
        assert result["metadata_source"] == "crossref"

def test_resolve_isbn_book():
    """Test (2) resolving an ISBN for a book (Ferziger)."""
    isbn = "9783030435074"
    mock_response = {
        f"ISBN:{isbn}": {
            "title": "Computational Methods for Fluid Dynamics",
            "authors": [
                {"name": "Joel H. Ferziger"},
                {"name": "Milovan Peric"},
                {"name": "Robert L. Street"}
            ],
            "publish_date": "2020",
            "publishers": [{"name": "Springer Nature"}]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_isbn(isbn)
        
        assert result is not None
        assert result["title"] == "Computational Methods for Fluid Dynamics"
        assert "Joel H. Ferziger" in result["author"]
        assert "Robert L. Street" in result["author"]
        assert result["year"] == 2020
        assert result["publisher"] == "Springer Nature"
        assert result["metadata_source"] == "openlibrary"

def test_resolve_doi_paper():
    """Test (3) resolving a DOI for a research paper (Spalart)."""
    doi = "10.1017/S0022112088000345"
    mock_response = {
        "message": {
            "title": ["Direct simulation of a turbulent boundary layer up to <i>R</i><sub>θ</sub> = 1410"],
            "author": [
                {"given": "Philippe R.", "family": "Spalart"}
            ],
            "published-print": {
                "date-parts": [[1988]]
            },
            "publisher": "Cambridge University Press (CUP)",
            "container-title": ["Journal of Fluid Mechanics"]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_doi(doi)
        
        assert result is not None
        assert result["title"] == "Direct simulation of a turbulent boundary layer up to <i>R</i><sub>θ</sub> = 1410"
        assert result["author"] == "Philippe R. Spalart"
        assert result["year"] == 1988
        assert result["journal"] == "Journal of Fluid Mechanics"
        assert result["metadata_source"] == "crossref"

def test_resolve_doi_failure():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 404
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_doi("10.1007/invalid")
        assert result is None

def test_resolve_isbn_not_found():
    isbn = "0000000000000"
    mock_response = {}
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = b"{}"
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_isbn(isbn)
        assert result is None

def test_resolve_doi_paper_with_parentheses():
    """Test resolving a DOI that contains parentheses."""
    doi = "10.1016/0021-9991(85)90148-2"
    mock_response = {
        "message": {
            "title": ["Application of a fractional-step method to incompressible Navier-Stokes equations"],
            "author": [
                {"given": "J", "family": "Kim"},
                {"given": "P", "family": "Moin"}
            ],
            "published-print": {
                "date-parts": [[1985]]
            },
            "publisher": "Elsevier BV",
            "container-title": ["Journal of Computational Physics"]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_doi(doi)
        
        assert result is not None
        assert result["title"] == "Application of a fractional-step method to incompressible Navier-Stokes equations"
        assert result["author"] == "J Kim; P Moin"
        assert result["year"] == 1985
        assert result["journal"] == "Journal of Computational Physics"
        assert result["publisher"] == "Elsevier BV"
        assert result["metadata_source"] == "crossref"

def test_resolve_isbn_10_success():
    """Test resolving an older ISBN-10 format for a book (Aris)."""
    isbn = "0486661105"
    mock_response = {
        f"ISBN:{isbn}": {
            "title": "Vectors, tensors, and the basic equations of fluid mechanics",
            "authors": [
                {"name": "Rutherford Aris"}
            ],
            "publish_date": "1989",
            "publishers": [{"name": "Dover Publications"}]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_isbn(isbn)
        
        assert result is not None
        assert result["title"] == "Vectors, tensors, and the basic equations of fluid mechanics"
        assert result["author"] == "Rutherford Aris"
        assert result["year"] == 1989
        assert result["publisher"] == "Dover Publications"
        assert result["metadata_source"] == "openlibrary"

def test_resolve_doi_paper_moser():
    """Test resolving a DOI for a research paper (Moser 1999)."""
    doi = "10.1063/1.869966"
    mock_response = {
        "message": {
            "title": ["Direct numerical simulation of turbulent channel flow up to Reτ=590"],
            "author": [
                {"given": "Robert D.", "family": "Moser"},
                {"given": "John", "family": "Kim"},
                {"given": "Nagi N.", "family": "Mansour"}
            ],
            "published-print": {
                "date-parts": [[1999]]
            },
            "publisher": "AIP Publishing",
            "container-title": ["Physics of Fluids"]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_context = MagicMock()
        mock_context.status = 200
        mock_context.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_context.__enter__.return_value = mock_context
        mock_urlopen.return_value = mock_context
        
        result = resolve_doi(doi)
        
        assert result is not None
        assert result["title"] == "Direct numerical simulation of turbulent channel flow up to Reτ=590"
        assert "Robert D. Moser" in result["author"]
        assert "John Kim" in result["author"]
        assert result["year"] == 1999
        assert result["journal"] == "Physics of Fluids"
        assert result["metadata_source"] == "crossref"

def test_resolve_doi_arxiv_datacite_fallback():
    """Test resolving an arXiv DOI that uses the DataCite fallback API."""
    doi = "10.48550/arXiv.1706.03762"
    mock_datacite_response = {
        "data": {
            "attributes": {
                "titles": [{"title": "Attention Is All You Need"}],
                "creators": [
                    {"givenName": "Ashish", "familyName": "Vaswani"},
                    {"givenName": "Noam", "familyName": "Shazeer"}
                ],
                "publicationYear": 2017,
                "publisher": "arXiv"
            }
        }
    }
    
    # We need to mock a 404 for the first call (Crossref) and a 200 for the second (DataCite)
    import urllib.error
    
    def side_effect(req, timeout=10):
        url = req.full_url
        if "crossref" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        elif "datacite" in url:
            import json
            from unittest.mock import MagicMock
            mock_context = MagicMock()
            mock_context.status = 200
            mock_context.read.return_value = json.dumps(mock_datacite_response).encode("utf-8")
            mock_context.__enter__.return_value = mock_context
            return mock_context
            
    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = resolve_doi(doi)
        
        assert result is not None
        assert result["title"] == "Attention Is All You Need"
        assert result["author"] == "Ashish Vaswani; Noam Shazeer"
        assert result["year"] == 2017
        assert result["journal"] == "arXiv"
        assert result["metadata_source"] == "datacite"
