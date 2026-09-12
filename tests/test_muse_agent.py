"""Tests for Muse's tool wiring, candidate schema, and citation validation."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturnPart

from apps.backend.config import Settings
from src.linger.agents.muse.models import (
    BookEvidenceUse,
    MuseCandidate,
    NoMemoryCandidate,
    SessionLineUse,
)
from src.linger.contracts.librarian import (
    EvidenceRecord,
    RetrievalResult,
    SearchedScope,
)
from src.linger.orchestration.turn_context import (
    add_turn_evidence,
    reset_turn_evidence,
    set_turn_evidence,
)


def _sample_tools(agent) -> dict[str, object]:
    tools: dict[str, object] = {}
    for toolset in agent.toolsets:
        tools.update(getattr(toolset, "tools", {}))
    return tools


def _sample_tool_names(agent) -> set[str]:
    return set(_sample_tools(agent))


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
                tools = _sample_tools(muse_agent_module.muse_chat_agent)
                self.assertIn("serendipity_explore", tools)
                tool = tools["serendipity_explore"]
                self.assertTrue(getattr(tool, "sequential"))
                schema = getattr(tool, "function_schema").json_schema
                self.assertNotIn("cue", schema["properties"])
            finally:
                importlib.reload(muse_agent_module)


class SessionLineUseTests(unittest.TestCase):
    def test_rejects_a_trivial_fragment(self) -> None:
        for fragment in ("I ", "the ", "yes it was"):
            with self.subTest(fragment=fragment):
                with self.assertRaises(ValidationError):
                    SessionLineUse(source_kind="session_line", quote=fragment)

    def test_accepts_a_substantive_quote(self) -> None:
        use = SessionLineUse(
            source_kind="session_line", quote="I lost my job last spring"
        )
        self.assertEqual("I lost my job last spring", use.quote)


class MuseOutputValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._evidence_token = set_turn_evidence(())

    def tearDown(self) -> None:
        reset_turn_evidence(self._evidence_token)

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
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        add_turn_evidence((record,))

        output = MuseCandidate(
            reply="Alice is unsure of herself.",
            memory=_no_memory(),
            evidence_uses=(
                BookEvidenceUse(
                    source_kind="book_corpus",
                    evidence_id="evidence-1",
                    source_location="Chapter 5, source lines 1-2",
                    exact_quote="A paraphrase incorrectly marked as exact",
                ),
            ),
        )

        with self.assertRaises(ModelRetry):
            validate_muse_output(self.context(record), output)

    def test_accepts_visible_exact_quote_or_null(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        add_turn_evidence((record,))

        for exact_quote in ("Who are you?", None):
            with self.subTest(exact_quote=exact_quote):
                output = MuseCandidate(
                    reply='The Caterpillar asks, "Who are you?"',
                    memory=_no_memory(),
                    evidence_uses=(
                        BookEvidenceUse(
                            source_kind="book_corpus",
                            evidence_id="evidence-1",
                            source_location="Chapter 5, source lines 1-2",
                            exact_quote=exact_quote,
                        ),
                    ),
                )
                self.assertIs(output, validate_muse_output(self.context(record), output))

    def test_quote_retry_supplies_exact_source_for_repair(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record().model_copy(update={
            "text": '“I am a sailor,” she said,\nrather _quietly_.',
        })
        add_turn_evidence((record,))
        for reply, quote in (
            (record.text.replace("\n", " "), record.text.replace("\n", " ")),
            ("She names her new role.", record.text),
            (record.text.replace("_", ""), record.text.replace("_", "")),
            ("An invented sentence.", "An invented sentence."),
        ):
            with self.subTest(reply=reply, quote=quote):
                candidate = MuseCandidate(
                    reply=reply,
                    memory=_no_memory(),
                    evidence_uses=(BookEvidenceUse(
                        source_kind="book_corpus",
                        evidence_id=record.evidence_id,
                        source_location=record.location,
                        exact_quote=quote,
                    ),),
                )
                with self.assertRaises(ModelRetry) as caught:
                    validate_muse_output(self.context(record), candidate)
                repair = json.loads(str(caught.exception))
                source = repair["canonical_book_evidence"]
                self.assertEqual(source["evidence_id"], record.evidence_id)
                self.assertEqual(source["text"], record.text)
                corrected = candidate.model_copy(update={
                    "reply": source["text"],
                    "evidence_uses": (candidate.evidence_uses[0].model_copy(update={
                        "exact_quote": source["text"],
                    }),),
                })
                self.assertIs(
                    corrected, validate_muse_output(self.context(record), corrected)
                )

    def test_live_validator_resolves_quote_location_and_evidence_id(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        add_turn_evidence((record,))
        output = MuseCandidate(
            reply='The Caterpillar asks, "Who are you?"',
            memory=_no_memory(),
            evidence_uses=(
                BookEvidenceUse(
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
        add_turn_evidence((record,))
        output = MuseCandidate(
            reply="A supported paraphrase.",
            memory=_no_memory(),
            evidence_uses=(
                BookEvidenceUse(
                    source_kind="book_corpus",
                    evidence_id="unknown-evidence",
                    source_location=record.location,
                ),
            ),
        )

        with self.assertRaises(ModelRetry):
            validate_muse_output(self.context(record), output)

    def test_message_history_tool_result_does_not_replace_the_shared_index(self) -> None:
        from src.linger.agents.muse.agent import validate_muse_output

        record = self.record()
        output = MuseCandidate(
            reply="A supported paraphrase.",
            memory=_no_memory(),
            evidence_uses=(
                BookEvidenceUse(
                    source_kind="book_corpus",
                    evidence_id=record.evidence_id,
                    source_location=record.location,
                ),
            ),
        )

        with self.assertRaises(ModelRetry):
            validate_muse_output(self.context(record), output)

if __name__ == "__main__":
    unittest.main()
