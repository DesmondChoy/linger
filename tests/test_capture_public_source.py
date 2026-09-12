"""The captured snapshot must match what the guarded tool returns at replay."""

from __future__ import annotations

from types import SimpleNamespace

from evals.synthetic_journals.capture_public_source import render_snapshot


def _result(**updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "title": "A study of error reporting by nurses",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10599306/",
        "published_date": "2023-08-01T00:00:00.000Z",
        "author": "Lindsay Thompson Munn",
        "text": "# A study of error reporting by nurses\n\nBackground: ...",
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_snapshot_carries_the_metadata_header_the_runtime_emits() -> None:
    """A direct client capture omits these lines and fails the replay check."""
    rendered = render_snapshot(_result())

    assert rendered.startswith(
        "Title: A study of error reporting by nurses\n"
        "URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC10599306/\n"
        "Published: 2023-08-01T00:00:00.000Z\n"
        "Author: Lindsay Thompson Munn\n"
        "\n"
    )
    assert rendered.endswith("Background: ...")


def test_optional_metadata_lines_are_omitted_not_blanked() -> None:
    rendered = render_snapshot(_result(published_date=None, author=None))

    assert "Published:" not in rendered
    assert "Author:" not in rendered
    assert rendered.startswith("Title: A study of error reporting by nurses\nURL: ")


def test_a_missing_title_still_renders_a_stable_header() -> None:
    rendered = render_snapshot(_result(title=None))

    assert rendered.startswith("Title: (untitled)\n")
