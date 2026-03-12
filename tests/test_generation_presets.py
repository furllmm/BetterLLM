from pathlib import Path

import utils.generation_presets as gp


def test_save_load_delete_custom_preset(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gp, "PRESETS_FILE", tmp_path / "generation_presets.json")

    params = {
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 33,
        "repeat_penalty": 1.1,
        "max_tokens": 512,
    }
    gp.save_custom_preset("MyPreset", params)
    loaded = gp.load_custom_presets()
    assert "MyPreset" in loaded
    assert loaded["MyPreset"]["top_k"] == 33

    assert gp.delete_custom_preset("MyPreset") is True
    assert "MyPreset" not in gp.load_custom_presets()


def test_load_custom_presets_handles_corrupt_json(tmp_path: Path, monkeypatch):
    f = tmp_path / "generation_presets.json"
    f.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(gp, "PRESETS_FILE", f)
    assert gp.load_custom_presets() == {}
