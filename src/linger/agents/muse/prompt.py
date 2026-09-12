"""Effective runtime instructions and contract-aware Muse fingerprints."""

from apps.backend.contracts import MuseDraftInput, MuseRevisionInput
from src.linger.agents.muse.skills import REFLECTION

INSTRUCTIONS = REFLECTION.effective_instructions

DRAFT_PROMPT_FINGERPRINT = REFLECTION.fingerprint(
    template_id="muse.reflection", input_type=MuseDraftInput, version="19"
)
REVISION_PROMPT_FINGERPRINT = REFLECTION.fingerprint(
    template_id="muse.revision", input_type=MuseRevisionInput, version="19"
)
