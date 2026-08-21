"""Tests for Muse's tool wiring and instruction invariants."""

import json
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
                "# Optional book grounding and spoilers",
                "# Probe when context is insufficient",
                "# Grounding with librarian_search",
                "# Quotations and honesty",
                "# Connections with serendipity_explore",
            },
            headings,
        )

    def test_instructions_require_probing_when_context_is_insufficient(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("missing information blocks", lowered)
        self.assertIn("follow-up question", lowered)
        self.assertIn("guessing", lowered)
        self.assertIn("do not probe for book context", lowered)

    def test_instructions_keep_the_in_scope_identifiers(self) -> None:
        self.assertIn('"pg11"', self.instructions)
        self.assertIn('"pg11-v01b38ea4"', self.instructions)

    def test_instructions_keep_the_safety_and_honesty_rules(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("safety authority", lowered)
        self.assertIn("never invent evidence", lowered)
        self.assertIn("spoiler boundary", lowered)
        self.assertIn("books are one optional source", lowered)
        self.assertIn("do not introduce character names", lowered)
        self.assertIn("never ask for a book or chapter merely", lowered)
        self.assertIn("without a book", lowered)
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

    @staticmethod
    def outside_request_context(*parts: object) -> SimpleNamespace:
        payload = json.dumps(
            {
                "muse_turn": {
                    "user_message": (
                        "Does this connect to an essay or philosophical idea "
                        "outside the book?"
                    ),
                    "policy": {"allow_connection": True},
                }
            }
        )
        return SimpleNamespace(
            messages=[
                SimpleNamespace(
                    parts=[SimpleNamespace(content=payload), *parts],
                )
            ]
        )

    def test_explicit_outside_request_requires_serendipity_return(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        output = MuseCandidate(
            reply="I could not safely search for an outside connection.",
            memory=_no_memory(),
        )

        with self.assertRaisesRegex(ModelRetry, "explicitly requested"):
            validate_muse_output(self.outside_request_context(), output)

    def test_explicit_outside_request_accepts_serendipity_decline(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output
        from src.linger.agents.serendipity.models import (
            ConnectionDecline,
            ConnectionExplorationResult,
        )

        exploration = ConnectionExplorationResult(
            decision=ConnectionDecline(
                reason="insufficient_evidence",
                safe_next_step="Name a source you would like to compare.",
            )
        )
        tool_return = ToolReturnPart("serendipity_explore", exploration)
        output = MuseCandidate(
            reply="I could not support a strong outside connection from this search.",
            memory=_no_memory(),
        )

        self.assertIs(
            output,
            validate_muse_output(
                self.outside_request_context(tool_return),
                output,
            ),
        )

    def test_live_validator_requires_selected_web_url(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output
        from src.linger.agents.serendipity.models import ConnectionExplorationResult

        url = "https://example.com/socratic-questioning"
        rubric = {
            "cue_fit": "direct",
            "reflective_value": "high",
            "safety": "clear",
            "disqualifiers": [],
        }
        exploration = ConnectionExplorationResult.model_validate({
            "decision": {
                "status": "proposal",
                "shortlist": [
                    {
                        "candidate_id": "candidate-socratic-first",
                        "rank": 1,
                        "tentative_claim": "The questions may resemble Socratic inquiry.",
                        "evidence_ids": [url],
                        "shared_structure": "Questions expose uncertain knowledge.",
                        "meaningful_difference": "The fictional exchange is less collaborative.",
                        "interpretation": "Confusion may begin inquiry.",
                        "rubric": rubric,
                        "comparison_note": "This is the most direct bridge.",
                    },
                    {
                        "candidate_id": "candidate-socratic-second",
                        "rank": 2,
                        "tentative_claim": "The scene may also resemble an examination.",
                        "evidence_ids": [url],
                        "shared_structure": "Both exchanges test an answer.",
                        "meaningful_difference": "One is literary and one philosophical.",
                        "interpretation": "Calmness may intensify pressure.",
                        "rubric": rubric,
                        "comparison_note": "This is useful but less transformative.",
                    },
                ],
                "selected_candidate_id": "candidate-socratic-first",
                "uncertainty": "medium",
                "presentation": "ask_before_showing",
                "suggested_follow_up": "Would you like the connection?",
                "policy_flags": ["contains_web_claim", "reader_consent_required"],
            },
            "evidence": [{
                "source_kind": "web",
                "evidence_id": url,
                "title": "Socratic questioning",
                "url": url,
                "excerpt": "Socratic questions can expose uncertain knowledge.",
            }],
        })
        context = SimpleNamespace(messages=[SimpleNamespace(parts=[
            ToolReturnPart("serendipity_explore", exploration)
        ])])
        without_url = MuseCandidate(
            reply="This may connect to Socratic inquiry.",
            memory=_no_memory(),
        )

        with self.assertRaisesRegex(ModelRetry, "exact URL"):
            validate_muse_output(context, without_url)

        with_url = without_url.model_copy(
            update={"reply": f"This may connect to Socratic inquiry: {url}"}
        )
        self.assertIs(with_url, validate_muse_output(context, with_url))


if __name__ == "__main__":
    unittest.main()
