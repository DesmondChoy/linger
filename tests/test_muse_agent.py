"""Tests for Muse's tool wiring and instruction invariants."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturnPart

from apps.backend.config import Settings
from src.linger.agents.muse.models import (
    EvidenceUse,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.contracts.librarian import (
    EvidenceRecord,
    RetrievalResult,
    SearchedScope,
)


def _sample_tool_names(agent) -> set[str]:
    names: set[str] = set()
    for toolset in agent.toolsets:
        names.update(getattr(toolset, "tools", {}).keys())
    return names


def _no_memory() -> NoMemoryCandidate:
    return NoMemoryCandidate(
        kind="no_memory_candidate",
        reason_code="transient_or_low_signal",
    )


class MuseAgentToolWiringTests(unittest.TestCase):
    def test_muse_chat_agent_registers_librarian_search(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            import importlib

            from src.linger.agents.muse import agent as muse_agent_module

            importlib.reload(muse_agent_module)
            try:
                names = _sample_tool_names(muse_agent_module.muse_chat_agent)
                self.assertIn("librarian_search", names)
            finally:
                importlib.reload(muse_agent_module)

    def test_muse_chat_agent_registers_serendipity_explore(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            import importlib

            from src.linger.agents.muse import agent as muse_agent_module

            importlib.reload(muse_agent_module)
            try:
                names = _sample_tool_names(muse_agent_module.muse_chat_agent)
                self.assertIn("serendipity_explore", names)
            finally:
                importlib.reload(muse_agent_module)


class MuseInstructionTests(unittest.TestCase):
    """Guard the load-bearing rules in Muse's Gemini-facing instructions."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.linger.agents.muse.agent import INSTRUCTIONS

        cls.instructions = INSTRUCTIONS

    def test_instructions_are_sectioned_for_structured_prompting(self) -> None:
        headings = {
            line for line in self.instructions.splitlines() if line.startswith("# ")
        }
        self.assertEqual(
            {
                "# Typed candidate",
                "# Context authority",
                "# Book confirmation and spoilers",
                "# Probe when context is insufficient",
                "# Grounding with librarian_search",
                "# Quotations and honesty",
                "# Connections with serendipity_explore",
            },
            headings,
        )

    def test_instructions_require_probing_when_context_is_insufficient(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("insufficient context", lowered)
        self.assertIn("follow-up question", lowered)
        self.assertIn("guessing", lowered)

    def test_instructions_keep_the_in_scope_identifiers(self) -> None:
        self.assertIn('"pg11"', self.instructions)
        self.assertIn('"pg11-v01b38ea4"', self.instructions)

    def test_instructions_keep_the_safety_and_honesty_rules(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("safety authority", lowered)
        self.assertIn("never invent evidence", lowered)
        self.assertIn("spoiler boundary", lowered)
        self.assertIn("until the reader confirms the book", lowered)
        self.assertIn("character names, plot details", lowered)
        self.assertIn("ask the reader that exact question", lowered)
        self.assertIn(
            "never present retrieved text as an exact quotation", lowered
        )
        self.assertIn("relay that honestly", lowered)

    def test_instructions_distinguish_every_librarian_response_branch(self) -> None:
        lowered = " ".join(self.instructions.lower().split())
        for phrase in (
            "clarification means retrieval did not run",
            "result` with `sufficient",
            "result` with `weak",
            "result` with `none",
            "for a `failure",
            "inspect `kind` before drafting",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, lowered)

        self.assertIn("state its `strength_reason` and `limitations`", lowered)
        self.assertIn("do not imply that later chapters were searched", lowered)
        self.assertIn("produce no evidence-based book answer", lowered)
        self.assertIn("without paraphrasing or broadening", lowered)
        self.assertIn("smallest evidence set", lowered)
        self.assertIn("directly supported by the cited records", lowered)


class MuseOutputValidationTests(unittest.TestCase):
    @staticmethod
    def context(record: EvidenceRecord) -> SimpleNamespace:
        result = RetrievalResult(
            kind="result",
            request_id="libreq-test",
            outcome="evidence_found",
            evidence_strength="sufficient",
            strength_reason="The evidence answers the question.",
            searched_scope=SearchedScope(
                work_id=record.work_id,
                book_version_id=record.book_version_id,
                max_chapter_inclusive=record.chapter_number,
            ),
            evidence=(record,),
        )
        return SimpleNamespace(
            messages=[
                SimpleNamespace(
                    parts=[ToolReturnPart("librarian_search", result)]
                )
            ]
        )

    @staticmethod
    def record() -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id="evidence-1",
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            chapter_id="pg11-v01b38ea4-ch05",
            chapter_number=5,
            location="Chapter 5, source lines 1-2",
            source_sha256="a" * 64,
            source_lines=(1, 2),
            text='The Caterpillar asks, "Who are you?"',
        )

    def test_retries_non_visible_exact_quote_metadata(self) -> None:
        from src.linger.agents.muse.agent import validate_exact_quote_declarations

        output = MuseCandidate(
            reply="Alice is unsure of herself.",
            memory=_no_memory(),
            evidence_uses=(
                EvidenceUse(
                    source_kind="book_corpus",
                    evidence_id="evidence-1",
                    source_location="Chapter 5, source lines 1-2",
                    exact_quote="A paraphrase incorrectly marked as exact",
                ),
            ),
        )

        with self.assertRaises(ModelRetry):
            validate_exact_quote_declarations(output)

    def test_accepts_visible_exact_quote_or_null(self) -> None:
        from src.linger.agents.muse.agent import validate_exact_quote_declarations

        for exact_quote in ("Who are you?", None):
            with self.subTest(exact_quote=exact_quote):
                output = MuseCandidate(
                    reply='The Caterpillar asks, "Who are you?"',
                    memory=_no_memory(),
                    evidence_uses=(
                        EvidenceUse(
                            source_kind="book_corpus",
                            evidence_id="evidence-1",
                            source_location="Chapter 5, source lines 1-2",
                            exact_quote=exact_quote,
                        ),
                    ),
                )
                self.assertIs(output, validate_exact_quote_declarations(output))

    def test_live_validator_resolves_quote_location_and_evidence_id(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        output = MuseCandidate(
            reply='The Caterpillar asks, "Who are you?"',
            memory=_no_memory(),
            evidence_uses=(
                EvidenceUse(
                    source_kind="book_corpus",
                    evidence_id=record.evidence_id,
                    source_location=record.location,
                    exact_quote="Who are you?",
                ),
            ),
        )

        self.assertIs(output, validate_muse_output(self.context(record), output))

    def test_live_validator_retries_unknown_evidence(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        output = MuseCandidate(
            reply="A supported paraphrase.",
            memory=_no_memory(),
            evidence_uses=(
                EvidenceUse(
                    source_kind="book_corpus",
                    evidence_id="unknown-evidence",
                    source_location=record.location,
                ),
            ),
        )

        with self.assertRaises(ModelRetry):
            validate_muse_output(self.context(record), output)


if __name__ == "__main__":
    unittest.main()
