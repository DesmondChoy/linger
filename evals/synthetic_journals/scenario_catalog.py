"""Discover saved scenarios without importing agents or calling providers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .adoption import validate_ground_truth_adoption_files
from .replay_support import replay_support_for
from .validate_scenario import validate_scenario_files

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FILES = ("backstory.json", "ground-truth.json", "ground-truth-adoption.json")
PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
SECRET_KEYS = (*PROVIDER_KEYS.values(), "EXA_API_KEY", "LOGFIRE_TOKEN")


def scenario_root(repository_root: Path) -> Path:
    return repository_root / "synthetic-journal-evaluation" / "scenarios"


def scenario_hashes(scenario: Path) -> dict[str, str | None]:
    return {
        name: hashlib.sha256((scenario / name).read_bytes()).hexdigest()
        if (scenario / name).is_file() else None
        for name in SCENARIO_FILES
    }


def environment_values(repository_root: Path) -> dict[str, str]:
    names = (*SECRET_KEYS, "LINGER_MODEL", "LOGFIRE_CREDENTIALS_DIR")
    dotenv = dotenv_values(repository_root / ".env")
    return {name: os.environ.get(name, dotenv.get(name) or "") for name in names}


def local_logfire_credentials(repository_root: Path) -> dict[str, Any]:
    directory = os.environ.get("LOGFIRE_CREDENTIALS_DIR", ".logfire")
    path = Path(directory)
    if not path.is_absolute():
        path = repository_root / path
    try:
        value = json.loads((path / "logfire_credentials.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def configuration(repository_root: Path, model: str | None = None) -> dict[str, Any]:
    values = environment_values(repository_root)
    selected = (model if model is not None else values["LINGER_MODEL"]).strip()
    provider, _, model_name = selected.partition(":")
    problems = []
    if provider not in PROVIDER_KEYS or not re.fullmatch(r"[A-Za-z0-9._/-]+", model_name):
        problems.append("Choose an explicit openai:, google:, or anthropic: model.")
    elif not values[PROVIDER_KEYS[provider]].strip():
        problems.append(f"Missing {PROVIDER_KEYS[provider]}; add it to the repository .env and recheck.")
    credentials = local_logfire_credentials(repository_root)
    has_logfire = bool(values["LOGFIRE_TOKEN"].strip() or credentials.get("token"))
    if not has_logfire:
        problems.append("Missing Logfire credentials; configure the project or set LOGFIRE_TOKEN.")
    return {
        "model": selected,
        "provider": provider,
        "required_api_key": PROVIDER_KEYS.get(provider),
        "provider_key_present": bool(provider in PROVIDER_KEYS and values[PROVIDER_KEYS[provider]].strip()),
        "web_key_present": bool(values["EXA_API_KEY"].strip()),
        "logfire_credentials_present": has_logfire,
        "problems": problems,
    }


def redact(text: str, repository_root: Path) -> str:
    values = environment_values(repository_root)
    secrets = [values[name].strip() for name in SECRET_KEYS if values[name].strip()]
    token = local_logfire_credentials(repository_root).get("token")
    if isinstance(token, str) and token:
        secrets.append(token)
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1[REDACTED]", text)


def descriptions(repository_root: Path) -> dict[Path, tuple[str, str]]:
    source = repository_root / "synthetic-journal-evaluation" / "scenario_descriptions.md"
    if not source.is_file():
        return {}
    result = {}
    for section in re.split(r"(?m)^## ", source.read_text(encoding="utf-8"))[1:]:
        title, _, body = section.partition("\n")
        link = re.search(r"\[Backstory\]\(([^)]+)\)", body)
        objective = re.search(r"(?ms)^Objective:\s*(.*?)(?=\n\s*\n|\Z)", body)
        if link and objective:
            path = (source.parent / link.group(1)).resolve()
            result[path] = (title.strip(), " ".join(objective.group(1).split()))
    return result


def objective_titles(repository_root: Path) -> dict[str, str]:
    source = repository_root / "synthetic-journal-evaluation" / "evaluation-objectives.yaml"
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        return {entry["id"]: entry["menu"]["title"] for entry in document["evaluation_objectives"]}
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
        return {}


def inspect_scenario(scenario: Path, repository_root: Path, model: str | None = None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    raw: dict[str, Any] = {}
    try:
        loaded = json.loads((scenario / "backstory.json").read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    except (OSError, ValueError):
        pass
    objectives = raw.get("objective_ids", [])
    if not isinstance(objectives, list) or not all(isinstance(item, str) for item in objectives):
        objectives = []
    support = replay_support_for(objectives)
    try:
        validate_scenario_files(scenario / "backstory.json", scenario / "ground-truth.json")
        if (scenario / "ground-truth-adoption.json").is_file():
            try:
                validate_ground_truth_adoption_files(*(scenario / name for name in SCENARIO_FILES))
            except (OSError, ValueError) as exc:
                issues.append({"category": "adoption", "detail": str(exc)})
        else:
            issues.append({"category": "adoption", "detail": "Independent Ground truth adoption is missing."})
    except (OSError, ValueError) as exc:
        issues.append({"category": "scenario", "detail": str(exc)})
    if support is None:
        issues.append({"category": "runner", "detail": "No supported replay for this exact Objective selection."})
    config = configuration(repository_root, model)
    issues.extend({"category": "configuration", "detail": text} for text in config["problems"])
    setups = raw.get("source_setups", [])
    public_sources = isinstance(setups, list) and any(
        isinstance(item, dict) and item.get("public_sources") for item in setups
    )
    if public_sources and not config["web_key_present"]:
        issues.append({"category": "configuration", "detail": "Missing EXA_API_KEY for this scenario's public sources."})
    return {
        "scenario": scenario.name,
        "objective_ids": objectives,
        "scene_count": len(raw.get("scenes", [])) if isinstance(raw.get("scenes"), list) else 0,
        "scene_ids": [
            scene["scene_id"] for scene in raw.get("scenes", [])
            if isinstance(scene, dict) and isinstance(scene.get("scene_id"), str)
        ] if isinstance(raw.get("scenes"), list) else [],
        "runner": support.module if support else None,
        "requires_web": bool(public_sources),
        "hashes": scenario_hashes(scenario),
        "configuration": config,
        "issues": [{**item, "detail": redact(item["detail"], repository_root)} for item in issues],
    }


def discover(repository_root: Path = REPOSITORY_ROOT) -> list[dict[str, Any]]:
    labels = descriptions(repository_root)
    titles = objective_titles(repository_root)
    entries = []
    for scenario in sorted(scenario_root(repository_root).iterdir()):
        if not scenario.is_dir() or scenario.is_symlink():
            continue
        item = inspect_scenario(scenario, repository_root)
        fallback = "; ".join(titles.get(key, key) for key in item["objective_ids"])
        title, description = labels.get(
            (scenario / "backstory.json").resolve(),
            (scenario.name.split("--")[0].replace("-", " ").capitalize(), fallback or "No generated Backstory or description is available."),
        )
        entries.append({**item, "title": title, "description": description})
    entries.sort(key=lambda item: (item["title"].casefold(), item["scenario"]))
    return [{"number": index, **item} for index, item in enumerate(entries, 1)]


def selected_scenario(menu: dict[str, Any], number: int, repository_root: Path) -> tuple[Path, dict[str, Any]]:
    entries = menu.get("entries", [])
    matches = [entry for entry in entries if entry.get("number") == number]
    if len(matches) != 1:
        raise ValueError("Choose a number from the displayed menu.")
    entry = matches[0]
    scenario = (scenario_root(repository_root) / entry["scenario"]).resolve()
    if scenario.parent != scenario_root(repository_root).resolve() or not scenario.is_dir():
        raise ValueError("The selected scenario is no longer in the scenario directory; refresh the menu.")
    return scenario, entry
