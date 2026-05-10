from pathlib import Path

from src.services.prompts import DEFAULT_PROMPT, PromptStore


def test_load_creates_default(tmp_path):
    store = PromptStore(path=tmp_path / "prompt.json")
    prompt = store.load()
    assert prompt.text == DEFAULT_PROMPT
    assert prompt.version == 1
    assert (tmp_path / "prompt.json").exists()


def test_update_increments_version(tmp_path):
    path = tmp_path / "prompt.json"
    store = PromptStore(path=path)
    store.load()
    updated = store.update("Keep baby away from stairs", updated_by="tester")
    assert updated.version == 2
    persisted = store.load()
    assert persisted.text == "Keep baby away from stairs"
    assert "tester" in (persisted.updated_by or "")
