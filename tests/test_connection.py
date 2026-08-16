"""Tests for the additive Layer 3 connection orchestration module."""

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from apps.backend.config import get_settings
from apps.backend.contracts import ConnectionDecline, ConnectionProposal, EvidenceBundle
from apps.backend.serendipity import discover
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration import connection
from src.linger.orchestration.connection import build_brief, connection_proposal, web_reach_permitted
from src.linger.orchestration.turn_context import reset_confirmed_reading, set_confirmed_reading
from src.linger.services.memory import AccountContext, MemoryPolicyService

WORK_ID = "pg11"


class ConnectionBriefTests(unittest.TestCase):
    def test_no_confirmed_reading_leaves_scope_unset(self) -> None:
        brief = build_brief("a cue")
        self.assertIsNone(brief.book_id)
        self.assertIsNone(brief.chapter_max)
        self.assertEqual({"book_corpus"}, brief.allowed_sources)

    def test_confirmed_reading_fills_scope(self) -> None:
        token = set_confirmed_reading(ConfirmedReading(work_id=WORK_ID, chapter_max=4))
        try:
            brief = build_brief("identity and change")
        finally:
            reset_confirmed_reading(token)

        self.assertEqual(WORK_ID, brief.book_id)
        self.assertEqual(4, brief.chapter_max)
        self.assertEqual({"book_corpus"}, brief.allowed_sources)


class ConnectionProposalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._token = None

    def tearDown(self) -> None:
        if self._token is not None:
            reset_confirmed_reading(self._token)
            self._token = None

    def _confirm(self, work_id: str = WORK_ID, chapter_max: int = 5) -> None:
        self._token = set_confirmed_reading(ConfirmedReading(work_id=work_id, chapter_max=chapter_max))

    async def test_no_confirmed_reading_declines_without_calling_explorer(self) -> None:
        explorer = MagicMock()
        brief = build_brief("identity")

        result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("insufficient_evidence", result.reason)
        explorer.assert_not_called()

    async def test_brief_cannot_widen_chapter_max_past_confirmed_ceiling(self) -> None:
        self._confirm(chapter_max=3)
        explorer = MagicMock()
        explorer.return_value = ConnectionDecline(reason="unsupported_cue", safe_next_step="n/a")
        brief = build_brief("identity").model_copy(update={"chapter_max": 99})

        await connection_proposal(brief, explorer=explorer)

        called_brief, called_evidence = explorer.call_args.args
        self.assertEqual(3, called_brief.chapter_max)

    async def test_book_id_is_forced_to_confirmed_slug(self) -> None:
        self._confirm(work_id=WORK_ID, chapter_max=5)
        explorer = MagicMock()
        explorer.return_value = ConnectionDecline(reason="unsupported_cue", safe_next_step="n/a")
        brief = build_brief("identity").model_copy(update={"book_id": "animal-farm"})

        await connection_proposal(brief, explorer=explorer)

        called_brief, _ = explorer.call_args.args
        self.assertEqual(WORK_ID, called_brief.book_id)

    async def test_evidence_handed_to_explorer_is_bounded_by_ceiling(self) -> None:
        self._confirm(chapter_max=2)
        explorer = MagicMock()
        explorer.return_value = ConnectionDecline(reason="unsupported_cue", safe_next_step="n/a")
        brief = build_brief("identity change growing caterpillar rules")

        await connection_proposal(brief, explorer=explorer)

        _, evidence = explorer.call_args.args
        self.assertIsInstance(evidence, EvidenceBundle)
        for item in evidence.items:
            self.assertLessEqual(item.chapter, 2)

    async def test_raising_retriever_declines_instead_of_raising(self) -> None:
        self._confirm()
        explorer = MagicMock()
        brief = build_brief("identity")

        with patch(
            "src.linger.orchestration.connection.librarian_service.retrieve",
            side_effect=RuntimeError("boom"),
        ):
            result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("insufficient_evidence", result.reason)
        explorer.assert_not_called()

    async def test_raising_explorer_declines_instead_of_raising(self) -> None:
        self._confirm()
        explorer = MagicMock(side_effect=RuntimeError("boom"))
        brief = build_brief("identity")

        result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("insufficient_evidence", result.reason)

    async def test_real_discover_pass_through_returns_proposal_for_in_corpus_cue(self) -> None:
        self._confirm(chapter_max=5)
        brief = build_brief("growing caterpillar")

        result = await connection_proposal(brief, explorer=discover)

        self.assertIsInstance(result, ConnectionProposal)

class WebReachPermittedTests(unittest.TestCase):
    def test_denies_when_unset_default_settings(self) -> None:
        get_settings.cache_clear()
        try:
            self.assertFalse(web_reach_permitted())
        finally:
            get_settings.cache_clear()

    def test_denies_when_attribute_absent_entirely(self) -> None:
        class NoFieldSettings:
            pass

        with patch(
            "src.linger.orchestration.connection.get_settings",
            return_value=NoFieldSettings(),
        ):
            self.assertFalse(web_reach_permitted())

    def test_permits_when_explicitly_true(self) -> None:
        class TrueSettings:
            linger_web_search_enabled = True

        with patch(
            "src.linger.orchestration.connection.get_settings",
            return_value=TrueSettings(),
        ):
            self.assertTrue(web_reach_permitted())


class EgressGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._token = set_confirmed_reading(ConfirmedReading(work_id=WORK_ID, chapter_max=5))
        self._tempdir = tempfile.TemporaryDirectory()
        self._service = MemoryPolicyService(self._tempdir.name)
        self._account = AccountContext(account_id="local-prototype-user")
        self._service.save_explicit(
            self._account,
            text="I was devastated when my grandmother passed away last spring",
            source_event_id="evt-1",
        )
        self._patcher = patch("src.linger.orchestration.connection.memory_service", self._service)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        self._tempdir.cleanup()
        reset_confirmed_reading(self._token)

    async def test_cue_quoting_seeded_memory_verbatim_declines_without_explorer(self) -> None:
        explorer = MagicMock()
        brief = build_brief("I was devastated when my grandmother passed away last spring")

        result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("unsupported_cue", result.reason)
        explorer.assert_not_called()

    async def test_short_memory_is_still_blocked_verbatim(self) -> None:
        self._service.save_explicit(self._account, text="sexual abuse", source_event_id="evt-2")
        explorer = MagicMock()
        brief = build_brief("does the story say anything about sexual abuse")

        result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("unsupported_cue", result.reason)
        explorer.assert_not_called()

    async def test_memory_without_word_characters_blocks_nothing(self) -> None:
        self._service.save_explicit(self._account, text="...", source_event_id="evt-3")
        explorer = MagicMock()
        explorer.return_value = ConnectionDecline(reason="unsupported_cue", safe_next_step="n/a")
        brief = build_brief("growing caterpillar")

        await connection_proposal(brief, explorer=explorer)

        explorer.assert_called_once()

    async def test_cue_about_same_topic_in_different_words_reaches_explorer(self) -> None:
        explorer = MagicMock()
        explorer.return_value = ConnectionDecline(reason="unsupported_cue", safe_next_step="n/a")
        brief = build_brief("losing a close family member is hard")

        await connection_proposal(brief, explorer=explorer)

        explorer.assert_called_once()

    async def test_unreadable_memory_store_fails_closed(self) -> None:
        explorer = MagicMock()
        brief = build_brief("some unrelated cue about the story")

        with patch.object(self._service, "list_active", side_effect=RuntimeError("boom")):
            result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("unsupported_cue", result.reason)
        explorer.assert_not_called()

    async def test_web_reach_permitted_declines_without_explorer(self) -> None:
        explorer = MagicMock()
        brief = build_brief("growing caterpillar")

        with patch(
            "src.linger.orchestration.connection.web_reach_permitted",
            return_value=True,
        ):
            result = await connection_proposal(brief, explorer=explorer)

        self.assertIsInstance(result, ConnectionDecline)
        self.assertEqual("unsupported_cue", result.reason)
        explorer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
