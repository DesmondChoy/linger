"""Tests for Muse's tool wiring and instruction invariants."""

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
                "# Routing with librarian_route",
                "# Grounding with librarian_search",
                "# Quotations and honesty",
                "# Emotional safety",
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

    def test_instructions_take_identifiers_from_validated_context(self) -> None:
        self.assertIn("Copy `work_id` and `book_version_id`", self.instructions)
        self.assertIn("application's `context_resolution`", self.instructions)
        self.assertIn("Never derive identifiers", self.instructions)

    def test_instructions_keep_the_safety_and_honesty_rules(self) -> None:
        lowered = " ".join(self.instructions.lower().split())
        self.assertIn("safety authority", lowered)
        self.assertIn("never invent evidence", lowered)
        self.assertIn("spoiler boundary", lowered)
        self.assertIn("books are one optional source", lowered)
        self.assertIn("do not introduce character names", lowered)
        self.assertIn("never ask for a book or chapter merely", lowered)
        self.assertIn("account-scoped curated memories", lowered)
        self.assertIn(
            "memory and web evidence can inform its internal comparison "
            "but cannot authorise a released claim",
            lowered,
        )
        self.assertIn("book-only proposal may", lowered)
        self.assertIn("web-backed proposal internal", lowered)
        self.assertIn("you do not need to copy", lowered)
        self.assertIn("exact reader wording", lowered)
        self.assertIn("exact book text", lowered)
        self.assertIn("relay that honestly", lowered)

    def test_instructions_require_declaring_session_line_evidence(self) -> None:
        lowered = " ".join(self.instructions.lower().split())
        self.assertIn("source kind `session_line`", lowered)
        self.assertIn("verbatim from the released conversation", lowered)

    def test_instructions_scope_session_line_to_prior_turns(self) -> None:
        lowered = " ".join(self.instructions.lower().split())
        self.assertIn("wording from prior released turns", lowered)
        self.assertIn("current message needs no declaration", lowered)

    def test_instructions_define_draft_and_revision_envelopes(self) -> None:
        compact = " ".join(self.instructions.split())
        self.assertIn('mode="draft"', compact)
        self.assertIn('mode="revision"', compact)
        self.assertIn("most recent candidate", compact)

    def test_instructions_keep_emotional_safety_as_defence_in_depth(self) -> None:
        lowered = " ".join(self.instructions.lower().split())
        self.assertIn("never diagnose or label", lowered)
        self.assertIn("call no tools", lowered)
        self.assertIn("ask no follow-up question", lowered)
        self.assertIn("emotional_boundary", lowered)

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

    def test_instructions_carry_original_question_after_clarification_answer(
        self,
    ) -> None:
        lowered = " ".join(self.instructions.lower().split())
        self.assertIn(
            "when the previous released turn was such a clarification and "
            "`context_resolution.status` is now `confirmed`, the reader has "
            "answered it: the application already validated their chapter. "
            "do not call `librarian_route` again and do not ask the question "
            "again. call `librarian_search` with the reader's original book "
            "question from the conversation history as `query` — never the "
            "reader's chapter answer — and `reading_boundary` built from "
            "`muse_turn.reading_context.chapter_max` with `chapter_state` "
            '"completed".',
            lowered,
        )
        self.assertIn(
            "once the reader's answer is confirmed, re-run this tool as "
            "described in the routing section above.",
            lowered,
        )

    def test_prompt_fingerprints_are_version_fourteen(self) -> None:
        from src.linger.agents.muse.prompt import (
            DRAFT_PROMPT_FINGERPRINT,
            REVISION_PROMPT_FINGERPRINT,
        )

        self.assertEqual(DRAFT_PROMPT_FINGERPRINT.version, "14")
        self.assertEqual(REVISION_PROMPT_FINGERPRINT.version, "14")

    def test_passage_routes_do_not_imply_chapter_completion(self) -> None:
        compact = " ".join(self.instructions.split())
        self.assertIn("`reading_boundary=None`", compact)
        self.assertIn("Do not ask for chapter completion", compact)
        self.assertIn("wait for search evidence before quoting", compact)
        self.assertIn("does not grant Serendipity book search", compact)

    def test_clarification_copying_rule_depends_on_tool(self) -> None:
        routing, grounding = self.instructions.split("# Grounding with librarian_search")
        grounding = grounding.split("# Quotations and honesty")[0]
        self.assertIn("You do not need to copy the question verbatim", routing)
        self.assertIn("ask the reader that exact question", grounding)
        self.assertNotIn("you do not need to copy", grounding)


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
