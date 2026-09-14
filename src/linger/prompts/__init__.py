"""Load shared agent and evaluation prompts from trusted package data."""

from functools import cache
from importlib.resources import files
from typing import Annotated, Literal

import yaml
from pydantic import StringConstraints, TypeAdapter

PromptGroup = Literal["agents", "evaluation"]
PromptText = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
_CATALOG_TYPE = TypeAdapter(dict[PromptGroup, dict[str, PromptText]])


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False,
    ) -> dict[object, object]:
        mapping = super().construct_mapping(node, deep=deep)
        if len(mapping) != len(node.value):
            raise ValueError("Duplicate keys in the prompt catalogue.")
        return mapping


@cache
def _load_catalog() -> dict[PromptGroup, dict[str, str]]:
    content = files(__package__).joinpath("prompt_catalog.yaml").read_text(encoding="utf-8")
    return _CATALOG_TYPE.validate_python(yaml.load(content, Loader=_UniqueKeyLoader))


def load_prompt(group: PromptGroup, name: str) -> str:
    """Return one prompt, failing on missing entries without a fallback."""
    return _load_catalog()[group][name]
