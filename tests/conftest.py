"""Offline regressions must not make accidental provider requests."""

import pytest
from pydantic_ai.models import override_allow_model_requests


@pytest.fixture(autouse=True)
def offline_model_requests():
    with override_allow_model_requests(False):
        yield
