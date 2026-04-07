#!/usr/bin/env python3

"""Backward-compatible imports for the legacy catalog_raw module.

The cataloging implementation now lives in ``llmkb.add_source``. This shim
keeps older imports working for tests and secondary commands that still import
``llmkb.catalog_raw``.
"""

from llmkb.add_source import (
    apply_override,
    choose_canonical,
    generate_canonical_filename,
    infer_doc_id,
    infer_source_class,
    main,
    parse_args,
)

