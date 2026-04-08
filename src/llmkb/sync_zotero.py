#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from llmkb.export_bibtex import should_export_doc
from llmkb.kb_common import KBContext, load_json, utc_now_iso, write_json


CONFIG_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_API_KEY_ENV = "ZOTERO_API_KEY"
DEFAULT_BATCH_SIZE = 50
CONFLICT_SKIP = "skip"
CONFLICT_LOCAL_WINS = "local_wins"
DEFAULT_MIN_REQUEST_INTERVAL_MS = 1000


@dataclass(frozen=True)
class LocalRecord:
    sha256: str
    doc_id: str
    fingerprint: str
    attachment_fingerprint: str
    document: dict[str, Any]


class RequestPacer:
    def __init__(self, min_interval_ms: int):
        self.min_interval_seconds = max(0.0, float(min_interval_ms) / 1000.0)
        self._next_allowed = 0.0

    def before_request(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed:
            time.sleep(self._next_allowed - now)

    def after_response_headers(self, headers: Any) -> None:
        now = time.monotonic()
        wait_seconds = self.min_interval_seconds
        backoff = parse_backoff_seconds(headers)
        if backoff is not None:
            wait_seconds = max(wait_seconds, backoff)
        self._next_allowed = max(self._next_allowed, now + wait_seconds)


def parse_backoff_seconds(headers: Any) -> float | None:
    if headers is None:
        return None
    for key in ("backoff", "retry-after"):
        value = headers.get(key)
        if value is None:
            continue
        try:
            parsed = float(str(value).strip())
        except ValueError:
            continue
        if parsed >= 0:
            return parsed
    return None


def client_last_response_headers(client: Any) -> Any:
    response = getattr(client, "request", None)
    if response is None:
        return None
    return getattr(response, "headers", None)


def call_create_items(client: Any, pacer: RequestPacer, payload: list[dict[str, Any]], parentid: str | None = None) -> Any:
    pacer.before_request()
    response = client.create_items(payload, parentid=parentid)
    pacer.after_response_headers(client_last_response_headers(client))
    return response


def call_update_item(client: Any, pacer: RequestPacer, payload: dict[str, Any]) -> Any:
    pacer.before_request()
    response = client.update_item(payload)
    pacer.after_response_headers(getattr(response, "headers", None))
    return response


def call_delete_item(
    client: Any,
    pacer: RequestPacer,
    payload: dict[str, Any] | list[dict[str, Any]],
    last_modified: int | None = None,
) -> Any:
    pacer.before_request()
    if last_modified is None:
        response = client.delete_item(payload)
    else:
        response = client.delete_item(payload, last_modified=last_modified)
    pacer.after_response_headers(getattr(response, "headers", None))
    return response


def call_last_modified_version(client: Any, pacer: RequestPacer) -> int:
    pacer.before_request()
    version = client.last_modified_version()
    pacer.after_response_headers(client_last_response_headers(client))
    return version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize llmkb local catalog with Zotero via pyzotero.")
    parser.add_argument(
        "--kb-root",
        default=".",
        help="Root directory of the knowledge base.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to Zotero sync config JSON. Defaults to <kb-root>/config/zotero_sync.json",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Path to Zotero sync state JSON. Defaults to <kb-root>/artifacts/zotero/sync_state.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned create/update/delete actions without calling Zotero.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit total number of actions (create/update/delete) to execute.",
    )
    parser.add_argument(
        "--min-request-interval-ms",
        type=int,
        help="Minimum delay between Zotero API requests in milliseconds.",
    )
    parser.add_argument(
        "--conflict-policy",
        choices=[CONFLICT_SKIP, CONFLICT_LOCAL_WINS],
        default=CONFLICT_SKIP,
        help="How to handle Zotero version conflicts (HTTP 412).",
    )
    parser.add_argument(
        "--include-attachments",
        action="store_true",
        default=None,
        help="Override config and create/update linked-file child attachments.",
    )
    parser.add_argument(
        "--no-include-attachments",
        action="store_false",
        dest="include_attachments",
        default=None,
        help="Override config and do not sync attachments.",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Create a template config file and exit.",
    )
    return parser.parse_args()


def default_sync_config() -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "library_type": "user",
        "library_id": "",
        "library_id_env": "ZOTERO_LIBRARY_ID",
        "api_key_env": DEFAULT_API_KEY_ENV,
        "sync_mode": "local_to_zotero",
        "collection_key": "",
        "include_attachments": False,
        "min_request_interval_ms": DEFAULT_MIN_REQUEST_INTERVAL_MS,
    }


def default_sync_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "updated_at": None,
        "last_library_version": None,
        "mappings": {},
    }


def resolve_config_path(context: KBContext, explicit_path: Path | None) -> Path:
    return explicit_path or (context.config_dir / "zotero_sync.json")


def resolve_state_path(context: KBContext, explicit_path: Path | None) -> Path:
    return explicit_path or context.path("artifacts", "zotero", "sync_state.json")


def init_config(path: Path) -> None:
    if path.exists():
        print(f"Config already exists: {path}")
        return
    write_json(path, default_sync_config())
    print(f"Created config template: {path}")


def load_sync_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Config not found: {path}. Run with --init-config to generate a template.")
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid config payload in {path}: expected JSON object.")
    config = default_sync_config()
    config.update(payload)
    if config.get("sync_mode") != "local_to_zotero":
        raise ValueError("Only sync_mode='local_to_zotero' is currently supported.")
    library_type = config.get("library_type")
    if library_type not in {"user", "group"}:
        raise ValueError("config.library_type must be 'user' or 'group'.")
    return config


def load_sync_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_sync_state()
    payload = load_json(path)
    if not isinstance(payload, dict):
        return default_sync_state()
    state = default_sync_state()
    state.update(payload)
    mappings = state.get("mappings")
    if not isinstance(mappings, dict):
        state["mappings"] = {}
    return state


def is_sync_candidate(doc: dict[str, Any]) -> bool:
    if doc.get("source_class") == "duplicate" or doc.get("is_redundant") or doc.get("status") == "rejected":
        return False
    if not doc.get("sha256"):
        return False
    return should_export_doc(doc)


def document_fingerprint(doc: dict[str, Any]) -> str:
    material = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "author": doc.get("author"),
        "year": doc.get("year"),
        "doi": doc.get("doi"),
        "isbn": doc.get("isbn"),
        "journal": doc.get("journal"),
        "publisher": doc.get("publisher"),
        "path": doc.get("path"),
        "source_class": doc.get("source_class"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attachment_fingerprint(doc: dict[str, Any]) -> str:
    material = {
        "path": doc.get("path"),
        "filename": doc.get("filename"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def collect_local_records(documents: list[dict[str, Any]]) -> dict[str, LocalRecord]:
    records: dict[str, LocalRecord] = {}
    for doc in sorted(documents, key=lambda item: item.get("doc_id", "")):
        if not is_sync_candidate(doc):
            continue
        sha256 = str(doc["sha256"])
        records[sha256] = LocalRecord(
            sha256=sha256,
            doc_id=str(doc.get("doc_id") or ""),
            fingerprint=document_fingerprint(doc),
            attachment_fingerprint=attachment_fingerprint(doc),
            document=doc,
        )
    return records


def plan_sync_actions(
    local_records: dict[str, LocalRecord],
    mappings: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    plan = {"create": [], "update": [], "delete": []}

    for sha256, record in local_records.items():
        mapping = mappings.get(sha256)
        if not mapping or not mapping.get("zotero_key"):
            plan["create"].append(sha256)
            continue
        if mapping.get("last_synced_fingerprint") != record.fingerprint:
            plan["update"].append(sha256)

    for sha256 in mappings:
        if sha256 not in local_records:
            plan["delete"].append(sha256)

    return plan


def trim_plan(plan: dict[str, list[str]], limit: int | None) -> dict[str, list[str]]:
    if limit is None or limit < 0:
        return plan
    if limit == 0:
        return {"create": [], "update": [], "delete": []}

    ordered = [("create", key) for key in plan["create"]]
    ordered += [("update", key) for key in plan["update"]]
    ordered += [("delete", key) for key in plan["delete"]]
    kept = ordered[:limit]

    trimmed = {"create": [], "update": [], "delete": []}
    for action, key in kept:
        trimmed[action].append(key)
    return trimmed


def split_authors(author_string: str | None) -> list[dict[str, str]]:
    if not author_string:
        return []

    creators: list[dict[str, str]] = []
    for author in [a.strip() for a in author_string.split(";") if a.strip()]:
        compact = " ".join(author.split())
        if "," in compact:
            parts = [p.strip() for p in compact.split(",") if p.strip()]
            if len(parts) >= 2:
                creators.append(
                    {
                        "creatorType": "author",
                        "lastName": parts[0],
                        "firstName": " ".join(parts[1:]),
                    }
                )
                continue
        name_parts = compact.split(" ")
        if len(name_parts) >= 2:
            creators.append(
                {
                    "creatorType": "author",
                    "lastName": name_parts[-1],
                    "firstName": " ".join(name_parts[:-1]),
                }
            )
        else:
            creators.append({"creatorType": "author", "name": compact})
    return creators


def choose_item_type(doc: dict[str, Any]) -> str:
    if doc.get("doi") and doc.get("journal"):
        return "journalArticle"
    if doc.get("isbn") or doc.get("source_class") == "book":
        return "book"
    if doc.get("doi"):
        return "journalArticle"
    return "document"


def set_if_present(payload: dict[str, Any], field: str, value: Any) -> None:
    if field in payload and value not in (None, ""):
        payload[field] = value


def append_identity_extra(existing: str | None, record: LocalRecord) -> str:
    lines = []
    if existing:
        lines.append(existing.strip())
    lines.extend(
        [
            f"LLMKB SHA256: {record.sha256}",
            f"LLMKB doc_id: {record.doc_id}",
            f"LLMKB path: {record.document.get('path', '')}",
        ]
    )
    return "\n".join(line for line in lines if line)


def build_item_payload(client: Any, record: LocalRecord, collection_key: str | None) -> dict[str, Any]:
    doc = record.document
    item_type = choose_item_type(doc)
    payload = dict(client.item_template(item_type))

    set_if_present(payload, "itemType", item_type)
    set_if_present(payload, "title", doc.get("title"))
    if payload.get("creators") is not None:
        payload["creators"] = split_authors(doc.get("author"))
    if doc.get("year"):
        set_if_present(payload, "date", str(doc["year"]))
    set_if_present(payload, "DOI", doc.get("doi"))
    set_if_present(payload, "ISBN", doc.get("isbn"))
    set_if_present(payload, "publicationTitle", doc.get("journal"))
    set_if_present(payload, "publisher", doc.get("publisher") or doc.get("producer"))
    set_if_present(payload, "extra", append_identity_extra(payload.get("extra"), record))

    if collection_key and "collections" in payload:
        payload["collections"] = [collection_key]

    return payload


def detect_content_type(path: str | None) -> str:
    if not path:
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def build_attachment_payload(client: Any, record: LocalRecord) -> dict[str, Any]:
    doc = record.document
    payload = dict(client.item_template("attachment", linkmode="linked_file"))
    rel_path = str(doc.get("path") or "")
    filename = str(doc.get("filename") or Path(rel_path).name)
    set_if_present(payload, "title", filename or record.doc_id)
    set_if_present(payload, "path", rel_path)
    set_if_present(payload, "filename", filename)
    set_if_present(payload, "contentType", detect_content_type(rel_path))
    return payload


def read_api_key(config: dict[str, Any]) -> str:
    env_name = str(config.get("api_key_env") or DEFAULT_API_KEY_ENV)
    api_key = os.environ.get(env_name)
    if not api_key:
        raise ValueError(f"Environment variable '{env_name}' is required for Zotero sync.")
    return api_key


def resolve_library_id(config: dict[str, Any]) -> str:
    literal = str(config.get("library_id") or "").strip()
    if literal:
        return literal

    env_candidates = []
    configured_name = str(config.get("library_id_env") or "").strip()
    if configured_name:
        env_candidates.append(configured_name)
    env_candidates.extend(["ZOTERO_LIBRARY_ID", "ZOTERO_USER_ID"])

    for env_name in env_candidates:
        value = os.environ.get(env_name)
        if value and value.strip():
            return value.strip()
    raise ValueError(
        "Zotero library_id is missing. Set config.library_id or define one of: "
        + ", ".join(env_candidates)
    )


def build_client(config: dict[str, Any]) -> Any:
    from pyzotero import Zotero  # Imported lazily for testability.

    api_key = read_api_key(config)
    library_id = resolve_library_id(config)
    return Zotero(library_id, config["library_type"], api_key)


def parse_create_response(response: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(response, dict):
        return {}
    successful = response.get("successful")
    if not isinstance(successful, dict):
        return {}

    parsed: dict[int, dict[str, Any]] = {}
    for index, payload in successful.items():
        try:
            numeric = int(index)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            parsed[numeric] = payload
    return parsed


def item_versions_for(client: Any, item_keys: list[str], pacer: RequestPacer | None = None) -> dict[str, int]:
    if not item_keys:
        return {}
    keys = [key for key in item_keys if key]
    if not keys:
        return {}
    if pacer is not None:
        pacer.before_request()
    payload = client.item_versions(itemKey=",".join(keys))
    if pacer is not None:
        pacer.after_response_headers(client_last_response_headers(client))
    if not isinstance(payload, dict):
        return {}
    versions: dict[str, int] = {}
    for key, value in payload.items():
        try:
            versions[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return versions


def chunk(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def update_mapping_from_record(
    mapping: dict[str, Any],
    record: LocalRecord,
    zotero_key: str,
    zotero_version: int | None,
) -> None:
    mapping["sha256"] = record.sha256
    mapping["doc_id"] = record.doc_id
    mapping["zotero_key"] = zotero_key
    mapping["zotero_version"] = zotero_version
    mapping["last_synced_fingerprint"] = record.fingerprint
    mapping["last_synced_path"] = record.document.get("path")


def print_plan(plan: dict[str, list[str]], local_records: dict[str, LocalRecord], mappings: dict[str, dict[str, Any]]) -> None:
    print("Planned Zotero sync actions:")
    print(f"  create: {len(plan['create'])}")
    print(f"  update: {len(plan['update'])}")
    print(f"  delete: {len(plan['delete'])}")

    for sha256 in plan["create"]:
        doc_id = local_records[sha256].doc_id
        print(f"    + create: {doc_id} ({sha256[:10]})")
    for sha256 in plan["update"]:
        doc_id = local_records[sha256].doc_id
        print(f"    ~ update: {doc_id} ({sha256[:10]})")
    for sha256 in plan["delete"]:
        mapping = mappings.get(sha256, {})
        doc_id = mapping.get("doc_id", "<unknown>")
        print(f"    - delete: {doc_id} ({sha256[:10]})")


def refresh_versions(client: Any, mappings: dict[str, dict[str, Any]], shas: list[str], pacer: RequestPacer) -> None:
    keys = [str(mappings[sha].get("zotero_key") or "") for sha in shas if sha in mappings]
    versions = item_versions_for(client, keys, pacer=pacer)
    for sha in shas:
        mapping = mappings.get(sha)
        if not mapping:
            continue
        key = str(mapping.get("zotero_key") or "")
        if key in versions:
            mapping["zotero_version"] = versions[key]


def apply_creates(
    client: Any,
    pacer: RequestPacer,
    shas_to_create: list[str],
    local_records: dict[str, LocalRecord],
    mappings: dict[str, dict[str, Any]],
    collection_key: str | None,
    include_attachments: bool,
) -> tuple[int, int]:
    created = 0
    attachment_created = 0

    for sha_chunk in chunk(shas_to_create, DEFAULT_BATCH_SIZE):
        records = [local_records[sha] for sha in sha_chunk]
        payloads = [build_item_payload(client, record, collection_key) for record in records]
        response = call_create_items(client, pacer, payloads)
        successful = parse_create_response(response)

        for index, record in enumerate(records):
            result = successful.get(index)
            if not result:
                print(f"Warning: create failed for doc_id={record.doc_id}")
                continue

            zotero_key = result.get("key")
            if not zotero_key:
                print(f"Warning: create response missing key for doc_id={record.doc_id}")
                continue
            zotero_version = result.get("version")
            try:
                zotero_version = int(zotero_version) if zotero_version is not None else None
            except (TypeError, ValueError):
                zotero_version = None

            mapping = mappings.setdefault(record.sha256, {})
            update_mapping_from_record(mapping, record, str(zotero_key), zotero_version)
            created += 1

            if include_attachments:
                att_payload = build_attachment_payload(client, record)
                att_response = call_create_items(client, pacer, [att_payload], parentid=str(zotero_key))
                att_successful = parse_create_response(att_response).get(0, {})
                att_key = att_successful.get("key")
                if att_key:
                    mapping["attachment_key"] = str(att_key)
                    mapping["attachment_version"] = att_successful.get("version")
                    mapping["attachment_fingerprint"] = record.attachment_fingerprint
                    attachment_created += 1

    refresh_versions(client, mappings, shas_to_create, pacer)
    return created, attachment_created


def _retry_version_from_mapping_or_remote(
    client: Any,
    mapping: dict[str, Any],
    pacer: RequestPacer,
) -> int | None:
    key = mapping.get("zotero_key")
    if not key:
        return None
    versions = item_versions_for(client, [str(key)], pacer=pacer)
    if key in versions:
        return versions[key]
    return None


def apply_updates(
    client: Any,
    pacer: RequestPacer,
    shas_to_update: list[str],
    local_records: dict[str, LocalRecord],
    mappings: dict[str, dict[str, Any]],
    collection_key: str | None,
    include_attachments: bool,
    conflict_policy: str,
) -> tuple[int, int, int]:
    updated = 0
    attachment_updated = 0
    conflicts = 0

    for sha256 in shas_to_update:
        record = local_records[sha256]
        mapping = mappings.get(sha256, {})
        zotero_key = mapping.get("zotero_key")
        if not zotero_key:
            continue

        payload = build_item_payload(client, record, collection_key)
        payload["key"] = str(zotero_key)
        payload["version"] = int(mapping.get("zotero_version") or 0)

        response = call_update_item(client, pacer, payload)
        if response.status_code == 412:
            conflicts += 1
            if conflict_policy == CONFLICT_LOCAL_WINS:
                latest = _retry_version_from_mapping_or_remote(client, mapping, pacer)
                if latest is not None:
                    payload["version"] = latest
                    response = call_update_item(client, pacer, payload)
            if response.status_code == 412:
                print(f"Warning: conflict on update doc_id={record.doc_id}; skipped.")
                continue
        if response.status_code < 200 or response.status_code >= 300:
            print(f"Warning: update failed for doc_id={record.doc_id} (status={response.status_code})")
            continue

        update_mapping_from_record(mapping, record, str(zotero_key), int(mapping.get("zotero_version") or 0))
        updated += 1

        if include_attachments and mapping.get("attachment_key"):
            if mapping.get("attachment_fingerprint") != record.attachment_fingerprint:
                att_payload = build_attachment_payload(client, record)
                att_payload["key"] = str(mapping["attachment_key"])
                att_payload["version"] = int(mapping.get("attachment_version") or 0)
                att_response = call_update_item(client, pacer, att_payload)
                if att_response.status_code == 412 and conflict_policy == CONFLICT_LOCAL_WINS:
                    latest_att = item_versions_for(
                        client,
                        [str(mapping["attachment_key"])],
                        pacer=pacer,
                    ).get(str(mapping["attachment_key"]))
                    if latest_att is not None:
                        att_payload["version"] = latest_att
                        att_response = call_update_item(client, pacer, att_payload)
                if 200 <= att_response.status_code < 300:
                    mapping["attachment_fingerprint"] = record.attachment_fingerprint
                    attachment_updated += 1

    refresh_versions(client, mappings, shas_to_update, pacer)
    return updated, attachment_updated, conflicts


def apply_deletes(
    client: Any,
    pacer: RequestPacer,
    shas_to_delete: list[str],
    mappings: dict[str, dict[str, Any]],
    conflict_policy: str,
) -> tuple[int, int]:
    deleted = 0
    conflicts = 0
    for sha256 in shas_to_delete:
        mapping = mappings.get(sha256, {})
        zotero_key = mapping.get("zotero_key")
        if not zotero_key:
            mappings.pop(sha256, None)
            continue

        payload = {
            "key": str(zotero_key),
            "version": int(mapping.get("zotero_version") or 0),
        }
        response = call_delete_item(client, pacer, payload)
        if response.status_code == 412:
            conflicts += 1
            if conflict_policy == CONFLICT_LOCAL_WINS:
                last_modified = call_last_modified_version(client, pacer)
                response = call_delete_item(client, pacer, payload, last_modified=last_modified)
            if response.status_code == 412:
                print(f"Warning: conflict on delete doc_id={mapping.get('doc_id', '<unknown>')}; skipped.")
                continue
        if response.status_code < 200 or response.status_code >= 300:
            print(f"Warning: delete failed for doc_id={mapping.get('doc_id', '<unknown>')} (status={response.status_code})")
            continue

        deleted += 1
        mappings.pop(sha256, None)

    return deleted, conflicts


def perform_sync(
    config: dict[str, Any],
    state: dict[str, Any],
    local_records: dict[str, LocalRecord],
    plan: dict[str, list[str]],
    include_attachments: bool,
    conflict_policy: str,
    min_request_interval_ms: int,
) -> dict[str, int]:
    client = build_client(config)
    pacer = RequestPacer(min_interval_ms=min_request_interval_ms)
    mappings: dict[str, dict[str, Any]] = state.setdefault("mappings", {})
    collection_key = str(config.get("collection_key") or "").strip() or None

    created, attachment_created = apply_creates(
        client=client,
        pacer=pacer,
        shas_to_create=plan["create"],
        local_records=local_records,
        mappings=mappings,
        collection_key=collection_key,
        include_attachments=include_attachments,
    )
    updated, attachment_updated, update_conflicts = apply_updates(
        client=client,
        pacer=pacer,
        shas_to_update=plan["update"],
        local_records=local_records,
        mappings=mappings,
        collection_key=collection_key,
        include_attachments=include_attachments,
        conflict_policy=conflict_policy,
    )
    deleted, delete_conflicts = apply_deletes(
        client=client,
        pacer=pacer,
        shas_to_delete=plan["delete"],
        mappings=mappings,
        conflict_policy=conflict_policy,
    )

    state["updated_at"] = utc_now_iso()
    state["last_library_version"] = call_last_modified_version(client, pacer)
    state["schema_version"] = STATE_SCHEMA_VERSION

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "attachment_created": attachment_created,
        "attachment_updated": attachment_updated,
        "conflicts": update_conflicts + delete_conflicts,
    }


def main() -> None:
    load_dotenv()
    load_dotenv(Path.home() / ".env")

    args = parse_args()
    context = KBContext(args.kb_root)
    config_path = resolve_config_path(context, args.config)
    state_path = resolve_state_path(context, args.state)

    if args.init_config:
        init_config(config_path)
        return

    if not context.catalog_path.exists():
        print(f"Error: Catalog not found at {context.catalog_path}. Run llmkb-add first.")
        return

    try:
        config = load_sync_config(config_path)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    include_attachments = (
        bool(config.get("include_attachments", False))
        if args.include_attachments is None
        else bool(args.include_attachments)
    )
    min_request_interval_ms = (
        int(config.get("min_request_interval_ms", DEFAULT_MIN_REQUEST_INTERVAL_MS))
        if args.min_request_interval_ms is None
        else int(args.min_request_interval_ms)
    )
    if min_request_interval_ms < 0:
        print("Error: --min-request-interval-ms must be >= 0.")
        return

    catalog = load_json(context.catalog_path)
    local_records = collect_local_records(catalog.get("documents", []))
    state = load_sync_state(state_path)
    mappings: dict[str, dict[str, Any]] = state.setdefault("mappings", {})

    plan = plan_sync_actions(local_records, mappings)
    plan = trim_plan(plan, args.limit)
    print_plan(plan, local_records, mappings)

    if args.dry_run:
        print("Dry run complete. No Zotero API calls were made.")
        return

    print(f"Using minimum request interval: {min_request_interval_ms} ms")

    try:
        stats = perform_sync(
            config=config,
            state=state,
            local_records=local_records,
            plan=plan,
            include_attachments=include_attachments,
            conflict_policy=args.conflict_policy,
            min_request_interval_ms=min_request_interval_ms,
        )
    except Exception as exc:
        print(f"Error during Zotero sync: {exc}")
        return

    write_json(state_path, state)
    print("Zotero sync complete.")
    print(
        "  created={created} updated={updated} deleted={deleted} "
        "attachment_created={attachment_created} attachment_updated={attachment_updated} conflicts={conflicts}".format(
            **stats
        )
    )
    print(f"State saved to: {state_path}")


if __name__ == "__main__":
    main()
