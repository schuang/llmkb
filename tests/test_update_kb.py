from argparse import Namespace

from llmkb import update_kb


def test_main_runs_bibtex_export_as_part_of_update_pipeline(monkeypatch, tmp_path):
    calls: list[tuple[str, list[str]]] = []
    reports: list[tuple[object, dict[str, str]]] = []

    monkeypatch.setattr(update_kb, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        update_kb,
        "parse_args",
        lambda: Namespace(
            kb_root=str(tmp_path),
            recursive=True,
            force=False,
            summarize_books=False,
            doc_id=[],
            no_report=False,
        ),
    )

    def fake_run_step(script: str, args: list[str]) -> str:
        calls.append((script, args))
        return f"ran {script}"

    def fake_generate_report(context, results: dict[str, str]):
        reports.append((context, results))
        return None

    monkeypatch.setattr(update_kb, "run_step", fake_run_step)
    monkeypatch.setattr(update_kb, "generate_report", fake_generate_report)

    update_kb.main()

    assert calls == [
        ("add_source.py", ["--kb-root", str(tmp_path), "--recursive"]),
        ("clean_kb.py", ["--kb-root", str(tmp_path)]),
        ("extract_pages.py", ["--kb-root", str(tmp_path)]),
        ("resolve_near_duplicates.py", ["--kb-root", str(tmp_path)]),
        ("build_source_pages.py", ["--kb-root", str(tmp_path)]),
        ("build_concept_pages.py", ["--kb-root", str(tmp_path)]),
        ("export_bibtex.py", ["--kb-root", str(tmp_path)]),
    ]
    assert len(reports) == 1
    assert "export_bibtex" in reports[0][1]
