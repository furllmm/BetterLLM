from pathlib import Path

import utils.prompt_library as pl


def test_add_prompt_with_extended_metadata_and_search(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt(
        name="Build API",
        text="Create endpoint",
        category="Coding",
        description="API scaffold",
        app_name="BetterLLM",
        project_name="Core",
        programming_language="Python",
        framework="Flask",
        prompt_version="v2",
        tags=["backend", "api"],
    )

    items = pl.get_all_prompts()
    assert len(items) == 1
    p = items[0]
    assert p["app_name"] == "BetterLLM"
    assert p["framework"] == "Flask"
    assert p["prompt_version"] == "v2"

    assert pl.search_prompts("flask")
    assert pl.search_prompts("backend")


def test_filter_prompts_and_unique_values(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", programming_language="Python", framework="Qt")
    pl.add_prompt("B", "x", programming_language="TypeScript", framework="React")

    py = pl.filter_prompts(programming_language="Python")
    assert len(py) == 1
    assert py[0]["name"] == "A"

    langs = pl.get_unique_values("programming_language")
    assert "Python" in langs and "TypeScript" in langs



def test_prompt_library_export_and_import(monkeypatch, tmp_path: Path):
    lib_file = tmp_path / "library.json"
    monkeypatch.setattr(pl, "LIBRARY_FILE", lib_file)

    pl.add_prompt("Prompt1", "Text1", app_name="AppA", programming_language="Python")
    out_json = tmp_path / "export.json"
    out_md = tmp_path / "export.md"

    pl.export_prompts(out_json, "json")
    pl.export_prompts(out_md, "markdown")
    assert out_json.exists() and out_md.exists()
    assert "Prompt1" in out_md.read_text(encoding="utf-8")

    # Reset library and import
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "imported.json")
    n = pl.import_prompts(out_json)
    assert n == 1
    items = pl.get_all_prompts()
    assert len(items) == 1
    assert items[0]["name"] == "Prompt1"
