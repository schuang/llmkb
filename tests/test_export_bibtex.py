import json
import sys

from llmkb.export_bibtex import (
    collect_bibtex_entries,
    escape_bibtex_value,
    format_authors_bibtex,
    generate_bibtex_entry,
    main,
    should_export_doc,
)


def test_should_export_doc_requires_identifier_by_default():
    doc = {
        "doc_id": "notes-1",
        "title": "Working notes",
        "year": 2026,
        "source_class": "notes",
    }

    assert should_export_doc(doc) is False


def test_should_export_doc_allows_explicit_zotero_override():
    doc = {
        "doc_id": "notes-1",
        "title": "Working notes",
        "year": 2026,
        "source_class": "notes",
        "zotero_include": True,
    }

    assert should_export_doc(doc) is True


def test_format_authors_bibtex_handles_mixed_name_styles():
    author_string = "John von Neumann; Moser, Robert D.; Kim, John"

    assert format_authors_bibtex(author_string) == (
        "Neumann, John von and Moser, Robert D. and Kim, John"
    )


def test_escape_bibtex_value_escapes_special_characters():
    value = r"C%_#&${}^~\path"

    assert escape_bibtex_value(value) == (
        r"C\%\_\#\&\$\{\}\textasciicircum{}\textasciitilde{}\textbackslash{}path"
    )


def test_generate_bibtex_entry_escapes_fields_and_formats_authors():
    doc = {
        "doc_id": "book1",
        "title": "C% and _underscores_ in BibTeX",
        "author": "Moser, Robert D.; Kim, John",
        "year": 1999,
        "isbn": "9783540307044",
        "publisher": "Springer & Sons",
        "path": "raw/library/book_name.pdf",
        "source_class": "book",
    }

    entry = generate_bibtex_entry(doc)

    assert entry is not None
    assert "@book{book1," in entry
    assert "title = {C\\% and \\_underscores\\_ in BibTeX}," in entry
    assert "author = {Moser, Robert D. and Kim, John}," in entry
    assert "publisher = {Springer \\& Sons}," in entry
    assert "file = {raw/library/book\\_name.pdf}," in entry
    assert "note =" not in entry


def test_collect_bibtex_entries_skips_informal_and_rejected_documents():
    documents = [
        {
            "doc_id": "paper-1",
            "title": "A paper",
            "author": "Jane Doe",
            "year": 2020,
            "doi": "10.1000/example",
            "journal": "Journal",
            "source_class": "paper",
        },
        {
            "doc_id": "notes-1",
            "title": "Working notes",
            "year": 2026,
            "source_class": "notes",
        },
        {
            "doc_id": "paper-2",
            "title": "Rejected paper",
            "year": 2021,
            "doi": "10.1000/rejected",
            "status": "rejected",
            "source_class": "paper",
        },
    ]

    entries = collect_bibtex_entries(documents)

    assert len(entries) == 1
    assert "@article{paper-1," in entries[0]


def test_main_writes_only_citeable_entries(tmp_path, capsys, monkeypatch):
    kb_root = tmp_path
    catalog_dir = kb_root / "artifacts" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "sources.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "paper-1",
                        "title": "A paper",
                        "author": "Jane Doe",
                        "year": 2020,
                        "doi": "10.1000/example",
                        "journal": "Journal",
                        "path": "raw/library/paper.pdf",
                        "source_class": "paper",
                    },
                    {
                        "doc_id": "notes-1",
                        "title": "Working notes",
                        "author": "Jane Doe",
                        "year": 2026,
                        "path": "raw/library/notes.pdf",
                        "source_class": "notes",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["llmkb-export", "--kb-root", str(kb_root)])

    main()

    output = kb_root / "artifacts" / "compile" / "library.bib"
    content = output.read_text(encoding="utf-8")
    captured = capsys.readouterr()

    assert "@article{paper-1," in content
    assert "notes-1" not in content
    assert "note =" not in content
    assert "Successfully generated 1 BibTeX entries." in captured.out
