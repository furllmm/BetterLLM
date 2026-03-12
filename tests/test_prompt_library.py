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
        feature_name="Auth API",
        tags=["backend", "api"],
    )

    items = pl.get_all_prompts()
    assert len(items) == 1
    p = items[0]
    assert p["app_name"] == "BetterLLM"
    assert p["framework"] == "Flask"
    assert p["prompt_version"] == "v2"
    assert p["feature_name"] == "Auth API"

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



def test_get_app_prompt_timeline_orders_by_created_at(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("New", "text", app_name="MyApp")
    # Force custom created_at order by patching stored file
    entries = pl.get_all_prompts()
    entries[0]["created_at"] = "2024-02-01T10:00:00"
    entries.append({
        "id": "p_old",
        "name": "Old",
        "text": "text",
        "category": "General",
        "description": "",
        "app_name": "MyApp",
        "project_name": "",
        "programming_language": "",
        "framework": "",
        "prompt_version": "v1",
        "tags": [],
        "created_at": "2024-01-01T10:00:00",
        "use_count": 0,
    })
    pl._save(entries)

    timeline = pl.get_app_prompt_timeline("MyApp")
    assert len(timeline) == 2
    assert timeline[0]["name"] == "Old"
    assert timeline[1]["name"] == "New"



def test_prompt_import_skips_duplicates_by_default(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("Same", "Text", app_name="App", project_name="Proj", prompt_version="v1")
    export_path = tmp_path / "export.json"
    pl.export_prompts(export_path, "json")

    # Importing same file should not duplicate when merge_duplicates=True
    n = pl.import_prompts(export_path)
    assert n == 0
    assert len(pl.get_all_prompts()) == 1


def test_prompt_import_can_allow_duplicates(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("Same", "Text", app_name="App", project_name="Proj", prompt_version="v1")
    export_path = tmp_path / "export.json"
    pl.export_prompts(export_path, "json")

    n = pl.import_prompts(export_path, merge_duplicates=False)
    assert n == 1
    assert len(pl.get_all_prompts()) == 2



def test_get_prompt_feature_map_groups_entries(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="App1", feature_name="Login")
    pl.add_prompt("B", "x", app_name="App1", feature_name="Login")
    pl.add_prompt("C", "x", app_name="App1", feature_name="Dashboard")

    mp = pl.get_prompt_feature_map("App1")
    assert "Login" in mp and "Dashboard" in mp
    assert len(mp["Login"]) == 2
    assert len(mp["Dashboard"]) == 1


def test_get_replay_sequence_sorts_versions_naturally(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p_v10",
            "name": "Later",
            "text": "text",
            "category": "General",
            "description": "",
            "app_name": "AppX",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v10",
            "feature_name": "Auth",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
        {
            "id": "p_v2",
            "name": "Earlier",
            "text": "text",
            "category": "General",
            "description": "",
            "app_name": "AppX",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v2",
            "feature_name": "Auth",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
    ])

    seq = pl.get_replay_sequence("AppX", "Auth")
    assert [p["prompt_version"] for p in seq] == ["v2", "v10"]


def test_build_replay_script_includes_steps_and_description(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p_1",
            "name": "Setup",
            "text": "create project",
            "category": "General",
            "description": "first step",
            "app_name": "AppY",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "Core",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        }
    ])

    script = pl.build_replay_script("AppY", "Core")
    assert "# Prompt Replay: AppY / Core" in script
    assert "## Step 1 · Setup · v1" in script
    assert "Desc: first step" in script
    assert "```\ncreate project\n```" in script


def test_build_replay_script_uses_safe_fence_for_embedded_backticks(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p_bt",
            "name": "Fence",
            "text": "before\n```python\nprint('x')\n```\nafter",
            "category": "General",
            "description": "",
            "app_name": "AppFence",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "Core",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        }
    ])

    script = pl.build_replay_script("AppFence", "Core")
    assert "````" in script
    assert "```python" in script


def test_get_replay_sequence_feature_filter_trims_input(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="AppTrim", feature_name="Login")
    pl.add_prompt("B", "x", app_name="AppTrim", feature_name="Billing")

    seq = pl.get_replay_sequence("AppTrim", "  Login  ")
    assert len(seq) == 1
    assert seq[0]["name"] == "A"


def test_get_replay_sequence_trims_app_name(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="TrimApp", feature_name="Login")

    seq = pl.get_replay_sequence("  TrimApp  ", "Login")
    assert len(seq) == 1
    assert seq[0]["name"] == "A"


def test_build_replay_script_trims_title_parts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("Step", "do work", app_name="TrimTitle", feature_name="Core")

    script = pl.build_replay_script("  TrimTitle  ", "  Core  ")
    assert script.startswith("# Prompt Replay: TrimTitle / Core")


def test_filter_prompts_trims_inputs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="AppTrim", programming_language="Python", framework="Qt")

    results = pl.filter_prompts(app_name="  AppTrim  ", programming_language="  Python ", framework=" Qt ")
    assert len(results) == 1
    assert results[0]["name"] == "A"


def test_get_prompt_feature_map_trims_app_name(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="AppMap", feature_name="Login")
    pl.add_prompt("B", "x", app_name="Other", feature_name="Login")

    mp = pl.get_prompt_feature_map("  AppMap  ")
    assert "Login" in mp
    assert len(mp["Login"]) == 1
    assert mp["Login"][0]["app_name"] == "AppMap"


def test_filter_prompts_is_case_insensitive(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="BetterLLM", programming_language="Python", framework="PyQt")

    results = pl.filter_prompts(app_name="betterllm", programming_language="python", framework="pyqt")
    assert len(results) == 1
    assert results[0]["name"] == "A"


def test_replay_sequence_is_case_insensitive_for_app_and_feature(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="CaseApp", feature_name="Auth")

    seq = pl.get_replay_sequence("caseapp", "auth")
    assert len(seq) == 1
    assert seq[0]["name"] == "A"


def test_feature_map_filter_is_case_insensitive(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="MapApp", feature_name="Login")

    mp = pl.get_prompt_feature_map("mapapp")
    assert "Login" in mp
    assert len(mp["Login"]) == 1


def test_get_prompt_feature_map_merges_feature_name_variants(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="AppVar", feature_name="Login")
    pl.add_prompt("B", "x", app_name="AppVar", feature_name=" login ")

    mp = pl.get_prompt_feature_map("AppVar")
    assert len(mp) == 1
    only_key = next(iter(mp.keys()))
    assert only_key == "Login"
    assert len(mp[only_key]) == 2


def test_get_prompt_feature_map_returns_sorted_feature_keys(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("B", "x", app_name="AppSort", feature_name="Zeta")
    pl.add_prompt("A", "x", app_name="AppSort", feature_name="alpha")

    mp = pl.get_prompt_feature_map("AppSort")
    assert list(mp.keys()) == ["alpha", "Zeta"]


def test_get_unique_values_dedupes_case_and_whitespace(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", programming_language="Python")
    pl.add_prompt("B", "x", programming_language=" python ")
    pl.add_prompt("C", "x", programming_language="PYTHON")

    langs = pl.get_unique_values("programming_language")
    assert langs == ["Python"]


def test_get_prompt_feature_map_uses_deterministic_label_choice(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", app_name="AppLabel", feature_name=" login ")
    pl.add_prompt("B", "x", app_name="AppLabel", feature_name="Login")

    mp = pl.get_prompt_feature_map("AppLabel")
    assert list(mp.keys()) == ["Login"]


def test_get_prompt_feature_map_sorts_entries_deterministically(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p2",
            "name": "Zeta step",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppDet",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v10",
            "feature_name": "Login",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
        {
            "id": "p1",
            "name": "Alpha step",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppDet",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v2",
            "feature_name": "Login",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
    ])

    mp = pl.get_prompt_feature_map("AppDet")
    names = [x["name"] for x in mp["Login"]]
    assert names == ["Alpha step", "Zeta step"]


def test_get_unique_values_uses_deterministic_canonical_label(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", programming_language=" python ")
    pl.add_prompt("B", "x", programming_language="Python")

    langs = pl.get_unique_values("programming_language")
    assert langs == ["Python"]


def test_get_app_prompt_timeline_uses_name_tiebreak(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p2",
            "name": "Zulu",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppTie",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
        {
            "id": "p1",
            "name": "Alpha",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppTie",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
    ])

    timeline = pl.get_app_prompt_timeline("AppTie")
    assert [x["name"] for x in timeline] == ["Alpha", "Zulu"]


def test_get_replay_sequence_uses_name_tiebreak(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl._save([
        {
            "id": "p2",
            "name": "Zulu",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppTieReplay",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "Core",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
        {
            "id": "p1",
            "name": "Alpha",
            "text": "x",
            "category": "General",
            "description": "",
            "app_name": "AppTieReplay",
            "project_name": "",
            "programming_language": "",
            "framework": "",
            "prompt_version": "v1",
            "feature_name": "Core",
            "tags": [],
            "created_at": "2024-01-01T10:00:00",
            "use_count": 0,
        },
    ])

    seq = pl.get_replay_sequence("AppTieReplay", "Core")
    assert [x["name"] for x in seq] == ["Alpha", "Zulu"]


def test_is_favorite_prompt_by_tag_and_category(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("A", "x", category="General", tags=["favorite"])
    pl.add_prompt("B", "x", category="Favorites", tags=[])
    pl.add_prompt("C", "x", category="General", tags=[])

    items = pl.get_all_prompts()
    flags = {p["name"]: pl.is_favorite_prompt(p) for p in items}
    assert flags["A"] is True
    assert flags["B"] is True
    assert flags["C"] is False


def test_get_favorite_prompts_returns_only_favorites(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pl, "LIBRARY_FILE", tmp_path / "library.json")

    pl.add_prompt("Fav", "x", tags=["starred"])
    pl.add_prompt("NotFav", "x")

    favs = pl.get_favorite_prompts()
    assert [p["name"] for p in favs] == ["Fav"]
