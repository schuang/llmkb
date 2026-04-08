import json
import sys

from llmkb.sync_zotero import (
    append_identity_extra,
    build_item_payload,
    collect_local_records,
    parse_create_response,
    plan_sync_actions,
    trim_plan,
)


class FakeZoteroClient:
    def item_template(self, itemtype: str, linkmode: str | None = None):
        if itemtype == "journalArticle":
            return {
                "itemType": "journalArticle",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "publicationTitle": "",
                "extra": "",
                "collections": [],
            }
        if itemtype == "book":
            return {
                "itemType": "book",
                "title": "",
                "creators": [],
                "date": "",
                "ISBN": "",
                "publisher": "",
                "extra": "",
                "collections": [],
            }
        if itemtype == "attachment":
            return {
                "itemType": "attachment",
                "title": "",
                "path": "",
                "filename": "",
                "contentType": "",
            }
        return {"itemType": itemtype, "title": "", "creators": [], "date": "", "extra": "", "collections": []}


def test_collect_local_records_filters_non_syncable_entries():
    docs = [
        {
            "doc_id": "paper-1",
            "title": "A paper",
            "author": "Jane Doe",
            "year": 2020,
            "doi": "10.1000/example",
            "sha256": "sha-paper-1",
            "path": "raw/library/paper-1.pdf",
            "source_class": "paper",
        },
        {
            "doc_id": "notes-1",
            "title": "Notes",
            "author": "Jane Doe",
            "year": 2026,
            "sha256": "sha-notes-1",
            "path": "raw/library/notes-1.pdf",
            "source_class": "notes",
        },
        {
            "doc_id": "notes-2",
            "title": "Notes",
            "author": "Jane Doe",
            "year": 2026,
            "sha256": "sha-notes-2",
            "path": "raw/library/notes-2.pdf",
            "source_class": "notes",
            "zotero_include": True,
        },
        {
            "doc_id": "dup-1",
            "title": "Duplicate",
            "author": "Jane Doe",
            "year": 2021,
            "doi": "10.1000/dup",
            "sha256": "sha-dup-1",
            "path": "raw/library/dup-1.pdf",
            "source_class": "duplicate",
        },
    ]

    records = collect_local_records(docs)

    assert sorted(records) == ["sha-notes-2", "sha-paper-1"]


def test_plan_sync_actions_detects_create_update_delete():
    docs = [
        {
            "doc_id": "paper-1",
            "title": "Paper v2",
            "author": "Jane Doe",
            "year": 2020,
            "doi": "10.1000/example",
            "sha256": "sha-paper-1",
            "path": "raw/library/paper-1.pdf",
            "source_class": "paper",
        },
        {
            "doc_id": "paper-2",
            "title": "Paper 2",
            "author": "Jane Doe",
            "year": 2021,
            "doi": "10.1000/example-2",
            "sha256": "sha-paper-2",
            "path": "raw/library/paper-2.pdf",
            "source_class": "paper",
        },
    ]
    records = collect_local_records(docs)

    stale_fingerprint = "old-fingerprint"
    mappings = {
        "sha-paper-1": {
            "zotero_key": "AAAA1111",
            "zotero_version": 10,
            "last_synced_fingerprint": stale_fingerprint,
            "doc_id": "paper-1",
        },
        "sha-old": {
            "zotero_key": "BBBB2222",
            "zotero_version": 7,
            "last_synced_fingerprint": "whatever",
            "doc_id": "old-paper",
        },
    }

    plan = plan_sync_actions(records, mappings)

    assert plan["create"] == ["sha-paper-2"]
    assert plan["update"] == ["sha-paper-1"]
    assert plan["delete"] == ["sha-old"]


def test_trim_plan_applies_global_limit_in_priority_order():
    plan = {
        "create": ["c1", "c2"],
        "update": ["u1", "u2"],
        "delete": ["d1"],
    }

    trimmed = trim_plan(plan, 3)
    assert trimmed == {
        "create": ["c1", "c2"],
        "update": ["u1"],
        "delete": [],
    }


def test_build_item_payload_maps_core_fields():
    doc = {
        "doc_id": "paper-1",
        "title": "A paper",
        "author": "Doe, Jane; Smith, John",
        "year": 2020,
        "doi": "10.1000/example",
        "journal": "Journal of Testing",
        "sha256": "sha-paper-1",
        "path": "raw/library/paper-1.pdf",
        "source_class": "paper",
    }
    record = collect_local_records([doc])["sha-paper-1"]
    client = FakeZoteroClient()

    payload = build_item_payload(client, record, collection_key="COLL123")

    assert payload["itemType"] == "journalArticle"
    assert payload["title"] == "A paper"
    assert payload["date"] == "2020"
    assert payload["DOI"] == "10.1000/example"
    assert payload["publicationTitle"] == "Journal of Testing"
    assert payload["collections"] == ["COLL123"]
    assert payload["creators"] == [
        {"creatorType": "author", "lastName": "Doe", "firstName": "Jane"},
        {"creatorType": "author", "lastName": "Smith", "firstName": "John"},
    ]
    assert "LLMKB SHA256: sha-paper-1" in payload["extra"]


def test_append_identity_extra_preserves_existing_extra():
    doc = {
        "doc_id": "paper-1",
        "title": "A paper",
        "author": "Jane Doe",
        "year": 2020,
        "doi": "10.1000/example",
        "sha256": "sha-paper-1",
        "path": "raw/library/paper-1.pdf",
        "source_class": "paper",
    }
    record = collect_local_records([doc])["sha-paper-1"]

    extra = append_identity_extra("Original notes", record)

    assert "Original notes" in extra
    assert "LLMKB doc_id: paper-1" in extra


def test_parse_create_response_extracts_successful_rows():
    response = {
        "successful": {
            "0": {"key": "AAAA1111", "version": 12},
            "2": {"key": "BBBB2222", "version": 13},
        }
    }

    parsed = parse_create_response(response)

    assert parsed == {
        0: {"key": "AAAA1111", "version": 12},
        2: {"key": "BBBB2222", "version": 13},
    }


def test_main_dry_run_prints_plan(tmp_path, monkeypatch, capsys):
    kb_root = tmp_path
    catalog_dir = kb_root / "artifacts" / "catalog"
    config_dir = kb_root / "config"
    catalog_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

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
                        "sha256": "sha-paper-1",
                        "path": "raw/library/paper-1.pdf",
                        "source_class": "paper",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "zotero_sync.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "library_type": "user",
                "library_id": "12345",
                "api_key_env": "ZOTERO_API_KEY",
                "sync_mode": "local_to_zotero",
                "collection_key": "",
                "include_attachments": False,
            }
        ),
        encoding="utf-8",
    )

    from llmkb import sync_zotero

    monkeypatch.setattr(
        sys,
        "argv",
        ["llmkb-zotero-sync", "--kb-root", str(kb_root), "--dry-run"],
    )

    sync_zotero.main()

    output = capsys.readouterr().out
    assert "Planned Zotero sync actions:" in output
    assert "create: 1" in output
    assert "Dry run complete" in output
