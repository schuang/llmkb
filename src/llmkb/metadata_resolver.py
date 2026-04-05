"""Metadata resolution engine for resolving identifiers to bibliographic data.

This module provides functions to query external academic APIs (Crossref, Open Library)
to retrieve canonical metadata for research papers and books based on unique
identifiers like DOIs and ISBNs.
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Any


def resolve_doi(doi: str) -> dict[str, Any] | None:
    """Resolve a Digital Object Identifier (DOI) to metadata using the Crossref or DataCite API.

    Args:
        doi: The DOI string to resolve (e.g., '10.1016/0021-9991(85)90148-2').

    Returns:
        dict | None: A dictionary containing 'title', 'author', 'year', 'publisher',
            'journal', 'metadata_source', and 'doi' if successful; otherwise None.
    """
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "llmkb/0.1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                msg = data.get("message", {})

                titles = msg.get("title", [])
                title = titles[0] if titles else None
                
                authors = []
                for author in msg.get("author", []):
                    given = author.get("given", "")
                    family = author.get("family", "")
                    if given or family:
                        authors.append(f"{given} {family}".strip())

                year = None
                published = msg.get("published-print", {}) or msg.get("published-online", {})
                date_parts = published.get("date-parts", [])
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]

                journals = msg.get("container-title", [])
                journal = journals[0] if journals else None

                return {
                    "title": title,
                    "author": "; ".join(authors) if authors else None,
                    "year": year,
                    "publisher": msg.get("publisher"),
                    "journal": journal,
                    "metadata_source": "crossref",
                    "doi": doi,
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # If Crossref fails with 404, try DataCite (often used for arXiv preprints)
            datacite_url = f"https://api.datacite.org/dois/{urllib.parse.quote(doi)}"
            dc_req = urllib.request.Request(datacite_url, headers={"User-Agent": "llmkb/0.1.0"})
            try:
                with urllib.request.urlopen(dc_req, timeout=10) as dc_response:
                    if dc_response.status == 200:
                        data = json.loads(dc_response.read().decode("utf-8"))
                        attrs = data.get("data", {}).get("attributes", {})
                        
                        titles = attrs.get("titles", [])
                        title = titles[0].get("title") if titles else None
                        
                        authors = []
                        for creator in attrs.get("creators", []):
                            given = creator.get("givenName", "")
                            family = creator.get("familyName", "")
                            if given or family:
                                authors.append(f"{given} {family}".strip())
                            elif creator.get("name"):
                                authors.append(creator.get("name"))
                                
                        return {
                            "title": title,
                            "author": "; ".join(authors) if authors else None,
                            "year": attrs.get("publicationYear"),
                            "publisher": attrs.get("publisher"),
                            "journal": attrs.get("publisher"),  # DataCite puts the repository here
                            "metadata_source": "datacite",
                            "doi": doi,
                        }
            except Exception as dc_e:
                print(f"Warning: Error resolving DOI {doi} with DataCite: {dc_e}")
                return None
        else:
            print(f"Warning: Error resolving DOI {doi} with Crossref: {e}")
            return None
    except Exception as e:
        print(f"Warning: Error resolving DOI {doi}: {e}")
        return None
    return None


def resolve_isbn(isbn: str) -> dict[str, Any] | None:
    """Resolve an International Standard Book Number (ISBN) to metadata using Open Library.

    Args:
        isbn: The 10 or 13-digit ISBN string (e.g., '9783030435074').

    Returns:
        dict | None: A dictionary containing 'title', 'author', 'year', 'publisher',
            'metadata_source', and 'isbn' if successful; otherwise None.
    """
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    req = urllib.request.Request(url, headers={"User-Agent": "llmkb/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                key = f"ISBN:{isbn}"
                if key in data:
                    book_data = data[key]
                    authors = [a.get("name") for a in book_data.get("authors", []) if a.get("name")]

                    year = None
                    publish_date = book_data.get("publish_date", "")
                    if publish_date:
                        match = re.search(r"\b(19|20)\d{2}\b", publish_date)
                        if match:
                            year = int(match.group(0))

                    publishers = [p.get("name") for p in book_data.get("publishers", []) if p.get("name")]

                    return {
                        "title": book_data.get("title"),
                        "author": "; ".join(authors) if authors else None,
                        "year": year,
                        "publisher": publishers[0] if publishers else None,
                        "metadata_source": "openlibrary",
                        "isbn": isbn,
                    }
    except Exception as e:
        print(f"Warning: Error resolving ISBN {isbn}: {e}")
        return None
    return None
