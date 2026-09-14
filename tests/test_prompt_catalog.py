"""Prompt resource loading preserves text and rejects ambiguous catalogues."""

import pytest

from src.linger import prompts


@pytest.fixture
def catalog_file(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "files", lambda package: tmp_path)
    prompts._load_catalog.cache_clear()
    yield tmp_path / "prompt_catalog.yaml"
    prompts._load_catalog.cache_clear()


def test_literal_prompt_preserves_internal_whitespace(catalog_file):
    catalog_file.write_text(
        "agents:\n  muse: |-\n    First line.\n\n      Indented line.\n",
        encoding="utf-8",
    )
    assert prompts.load_prompt("agents", "muse") == "First line.\n\n  Indented line."


@pytest.mark.parametrize("content", [
    "agents:\n  muse: First.\n  muse: Second.\n",
    "agents:\n  muse: First.\nagents:\n  muse: Second.\n",
    "agents:\n  muse: null\n",
    "agents:\n  muse: 123\n",
    "agents:\n  muse: '   '\n",
    "unexpected:\n  muse: Instructions.\n",
])
def test_invalid_catalogue_fails_instead_of_changing_instructions(catalog_file, content):
    catalog_file.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        prompts.load_prompt("agents", "muse")


def test_missing_prompt_has_no_fallback(catalog_file):
    catalog_file.write_text("agents:\n  muse: Instructions.\n", encoding="utf-8")
    with pytest.raises(KeyError, match="missing"):
        prompts.load_prompt("agents", "missing")


def test_uncached_packaged_catalogue_loads_from_an_unrelated_directory(tmp_path, monkeypatch):
    expected = prompts.load_prompt("agents", "muse")
    prompts._load_catalog.cache_clear()
    monkeypatch.chdir(tmp_path)
    assert prompts.load_prompt("agents", "muse") == expected
    assert prompts.load_prompt("evaluation", "book_spoiler_review")
