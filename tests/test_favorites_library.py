from pathlib import Path

import utils.favorites_library as fav
def test_update_and_load_profile_normalizes_lists(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")

    fav.update_profile(
        favorite_software=["VS Code", " vs code ", "PyCharm"],
        installed_tools=["Docker", "docker", "Poetry"],
        favorite_languages=["Python", " python ", "PYTHON"],
    )

    loaded = fav.load_profile()
    assert loaded["favorite_software"] == ["VS Code", "PyCharm"]
    assert loaded["installed_tools"] == ["Docker", "Poetry"]
    assert loaded["favorite_languages"] == ["Python"]


def test_build_personalization_context_contains_expected_sections(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")

    fav.save_profile(
        {
            "preferences": ["concise responses"],
            "favorite_software": ["VS Code"],
            "installed_tools": ["Docker", "Poetry"],
            "environments": ["Ubuntu 24.04", "WSL2"],
            "favorite_languages": ["Python"],
            "interests_hobbies": ["game dev"],
            "notes": "Use local-first suggestions",
        }
    )

    text = fav.build_personalization_context()
    assert "User Workflow Profile:" in text
    assert "Favorite software: VS Code" in text
    assert "Installed tools: Docker, Poetry" in text
    assert "Environment: Ubuntu 24.04, WSL2" in text
    assert "Personalization rule:" in text




def test_chat_session_prompt_template_has_personalization_section():
    src = Path("core/chat_session.py").read_text(encoding="utf-8")
    assert "- User personalization profile:" in src


def test_personalize_suggestions_prioritizes_environment_matches(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile(
        {
            "installed_tools": ["Docker", "Poetry"],
            "favorite_languages": ["Python"],
            "environments": ["WSL2"],
        }
    )

    suggestions = [
        "How to improve productivity?",
        "Create a Docker Compose setup for local dev",
        "Set up Poetry project structure",
        "Write a Python CLI scaffold",
    ]
    ranked = fav.personalize_suggestions(suggestions, limit=4)

    assert ranked[0] in {
        "Create a Docker Compose setup for local dev",
        "Set up Poetry project structure",
        "Write a Python CLI scaffold",
    }
    assert "How to improve productivity?" in ranked


def test_personalize_suggestions_dedupes_and_limits(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile({"installed_tools": ["Docker"]})

    ranked = fav.personalize_suggestions([
        "Use Docker for local stack",
        "use docker for local stack",
        "General tip",
    ], limit=2)

    assert len(ranked) == 2
    assert ranked[0] == "Use Docker for local stack"


def test_personalize_suggestions_prioritizes_installed_tools_over_interests(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile({
        "installed_tools": ["Docker"],
        "interests_hobbies": ["music"],
    })

    suggestions = [
        "music production ideas",
        "dockerize this service with Docker Compose",
    ]
    ranked = fav.personalize_suggestions(suggestions, limit=2)
    assert ranked[0] == "dockerize this service with Docker Compose"


def test_personalize_suggestions_prefers_token_matches(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile({"installed_tools": ["go"]})

    suggestions = [
        "How to get going faster",      # substring only
        "Build and test a Go module",   # token match
    ]
    ranked = fav.personalize_suggestions(suggestions, limit=2)
    assert ranked[0] == "Build and test a Go module"


def test_personalize_suggestions_uses_preferences_as_strong_signal(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile({"preferences": ["concise"]})

    suggestions = [
        "Give me a long and exhaustive walkthrough",
        "Give me a concise summary of next steps",
    ]
    ranked = fav.personalize_suggestions(suggestions, limit=2)
    assert ranked[0] == "Give me a concise summary of next steps"


def test_personalize_suggestions_keeps_input_order_when_no_profile_terms(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fav, "FAVORITES_FILE", tmp_path / "favorites.json")
    fav.save_profile({})

    suggestions = ["First option", "Second option", "Third option"]
    ranked = fav.personalize_suggestions(suggestions, limit=3)
    assert ranked == suggestions
