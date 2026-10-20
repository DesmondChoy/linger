"""Sign-in: login tokens decide the account, and accounts cannot reach each other's data."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import auth, chat_turn, main, sessions
    from apps.backend.accounts import AccountStore
    from src.linger.contracts.emotional import EmotionalBoundaryAssessment
    from src.linger.orchestration.progress_context import emit_progress
    from src.linger.orchestration.reflection import ReflectionRelease
    from src.linger.services.memory import (
        AccountContext,
        AutomaticMemoryCandidate,
        MemoryPolicyService,
    )


class AccountStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "accounts.sqlite3"
        self.store = AccountStore(self.path)

    def test_passwords_are_not_stored_in_plain_text(self) -> None:
        self.store.create_account("alice", "correct horse")
        self.assertNotIn(b"correct horse", self.path.read_bytes())

    def test_login_and_logout(self) -> None:
        self.store.create_account("alice", "correct horse")
        self.assertIsNone(self.store.login("alice", "wrong horse"))
        self.assertIsNone(self.store.login("nobody", "correct horse"))

        token = self.store.login("alice", "correct horse")
        assert token is not None
        self.assertEqual("alice", self.store.username_for(token))
        self.store.logout(token)
        self.assertIsNone(self.store.username_for(token))

    def test_tokens_survive_a_new_store_on_the_same_file(self) -> None:
        token = self.store.create_account("alice", "correct horse")
        self.assertEqual("alice", AccountStore(self.path).username_for(token))


class SignInTests(unittest.TestCase):
    def setUp(self) -> None:
        # Exercise real tokens instead of the suite's signed-in test reader.
        main.app.dependency_overrides.pop(auth.current_username, None)

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        memory_service = patch.object(
            main, "memory_service", MemoryPolicyService(Path(directory.name))
        )
        memory_service.start()
        self.addCleanup(memory_service.stop)
        for target, replacement in (
            (
                "assess_emotional_boundary",
                AsyncMock(
                    return_value=EmotionalBoundaryAssessment(
                        decision="continue_reflection"
                    )
                ),
            ),
            (
                "reflection_reply",
                AsyncMock(
                    return_value=ReflectionRelease(
                        reply="Approved reply",
                        release_source="muse_candidate",
                        provenance_verdicts=("pass",),
                    )
                ),
            ),
        ):
            patcher = patch.object(chat_turn, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.session_id = "alice-private-session"
        self.addCleanup(sessions.clear, self.session_id)
        self.client = TestClient(main.app)
        self.alice = self.sign_up("alice")
        self.bob = self.sign_up("bob")

    def sign_up(self, username: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/signup", json={"username": username, "password": "password1"}
        )
        self.assertEqual(201, response.status_code)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def chat(self, headers: dict[str, str], turn_id: str = "turn-1"):
        return self.client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": self.session_id, "turn_id": turn_id, "message": "Hello"},
        )

    def test_sign_up_and_log_in(self) -> None:
        taken = self.client.post(
            "/api/auth/signup", json={"username": "ALICE", "password": "password1"}
        )
        self.assertEqual(409, taken.status_code)

        wrong = self.client.post(
            "/api/auth/login", json={"username": "alice", "password": "password2"}
        )
        self.assertEqual(401, wrong.status_code)

        # Usernames are case-insensitive.
        right = self.client.post(
            "/api/auth/login", json={"username": "Alice", "password": "password1"}
        )
        self.assertEqual("alice", right.json()["username"])
        headers = {"Authorization": f"Bearer {right.json()['token']}"}
        self.assertEqual(
            {"username": "alice"}, self.client.get("/api/auth/me", headers=headers).json()
        )

        self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(401, self.client.get("/api/auth/me", headers=headers).status_code)

    def test_requests_without_a_valid_token_are_refused(self) -> None:
        for headers in ({}, {"Authorization": "Bearer not-a-real-token"}):
            with self.subTest(headers=headers):
                self.assertEqual(401, self.chat(headers).status_code)
                self.assertEqual(401, self.client.get("/api/history", headers=headers).status_code)
                self.assertEqual(
                    401,
                    self.client.delete(
                        f"/api/sessions/{self.session_id}", headers=headers
                    ).status_code,
                )
        self.assertEqual([], sessions.history(self.session_id))

    def test_the_token_decides_the_memory_account(self) -> None:
        def account_for(headers: dict[str, str]) -> AccountContext:
            token = headers["Authorization"].removeprefix("Bearer ")
            return auth.current_account(auth.current_username(
                auth.HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            ))

        self.assertEqual("user:alice", account_for(self.alice).account_id)
        self.assertEqual("user:bob", account_for(self.bob).account_id)

    def test_another_account_cannot_continue_or_delete_a_session(self) -> None:
        self.assertEqual(200, self.chat(self.alice).status_code)
        history = list(sessions.history(self.session_id))

        self.assertEqual(404, self.chat(self.bob, turn_id="turn-2").status_code)
        self.assertEqual(
            404,
            self.client.delete(
                f"/api/sessions/{self.session_id}", headers=self.bob
            ).status_code,
        )
        self.assertEqual(history, sessions.history(self.session_id))
        self.assertEqual(200, self.chat(self.alice, turn_id="turn-2").status_code)

    def test_only_the_owner_can_list_and_forget_a_memory(self) -> None:
        main.memory_service.set_capture_enabled(AccountContext("user:alice"), True)
        saved = main.memory_service.save_automatic(
            AccountContext("user:alice"),
            AutomaticMemoryCandidate(
                text="I reread letters when I feel far from home.",
                source_event_id="turn-letters",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record

        listed = self.client.get("/api/memories", headers=self.alice).json()
        self.assertEqual(
            [(saved.memory_id, "original", "turn-letters", True)],
            [(row["memory_id"], row["kind"], row["source_turn_id"], row["searchable"]) for row in listed],
        )
        self.assertEqual([], self.client.get("/api/memories", headers=self.bob).json())
        url = f"/api/memories/{saved.memory_id}"
        self.assertEqual(404, self.client.delete(url, headers=self.bob).status_code)
        self.assertEqual(401, self.client.delete(url).status_code)
        self.assertEqual(204, self.client.delete(url, headers=self.alice).status_code)
        self.assertEqual([], self.client.get("/api/memories", headers=self.alice).json())
        self.assertEqual(404, self.client.delete(url, headers=self.alice).status_code)

    def test_memory_table_and_history_show_every_curation_link(self) -> None:
        from src.linger.agents.provenance.curation_models import CurationProvenanceReview
        from src.linger.agents.sculptor.models import (
            CurationProposal,
            DerivedSummary,
            DuplicateLink,
            RetrievalTombstone,
        )
        from src.linger.contracts.curation import ApprovedCuration
        from src.linger.orchestration.curation import prepare_curation_plan

        account = AccountContext("user:alice")
        service = main.memory_service
        service.set_capture_enabled(account, True)
        kept, copy, earlier, later = (
            service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=text,
                    source_event_id=f"turn-{index}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            ).record
            for index, text in enumerate((
                "I read outdoors.", "I read outdoors.",
                "Book club meets on Mondays.", "Book club moved to Fridays.",
            ))
        )
        actions = (
            DuplicateLink(action="link_duplicates", source_memory_ids=(kept.memory_id, copy.memory_id)),
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(copy.memory_id, kept.memory_id),
                memory_id=copy.memory_id,
                canonical_memory_id=kept.memory_id,
            ),
            DerivedSummary(
                action="update_derived_summary",
                source_memory_ids=(earlier.memory_id, later.memory_id),
                summary="Book club moved from Mondays to Fridays.",
            ),
        )
        for action in actions:
            plan = prepare_curation_plan(
                service.select_for_curation(account, action.source_memory_ids),
                CurationProposal(kind="curation_proposal", action=action),
                base_state_sha256=service.curation_state_sha256(account),
            )
            service.apply_curation(account, ApprovedCuration(
                plan=plan,
                review=CurationProvenanceReview(proposal_digest=plan.digest, decision="allow"),
            ))

        rows = {row["memory_id"]: row for row in self.client.get("/api/memories", headers=self.alice).json()}
        self.assertEqual([copy.memory_id], rows[kept.memory_id]["duplicate_memory_ids"])
        self.assertEqual([kept.memory_id], rows[copy.memory_id]["duplicate_memory_ids"])
        self.assertEqual(kept.memory_id, rows[copy.memory_id]["retired_for"])
        self.assertFalse(rows[copy.memory_id]["searchable"])
        self.assertIsNone(rows[kept.memory_id]["retired_for"])

        history = self.client.get("/api/memories/curation", headers=self.alice).json()
        self.assertEqual(
            ["link_duplicates", "tombstone_for_retrieval", "update_derived_summary"],
            [entry["action"] for entry in history],
        )
        self.assertEqual((copy.memory_id, kept.memory_id), (history[1]["memory_id"], history[1]["canonical_memory_id"]))
        self.assertIn(history[2]["result_memory_id"], rows)
        self.assertEqual("derived_summary", rows[history[2]["result_memory_id"]]["kind"])
        self.assertEqual([], self.client.get("/api/memories/curation", headers=self.bob).json())
        self.assertEqual(401, self.client.get("/api/memories/curation").status_code)

    def test_a_reader_loads_a_recorded_scenarios_props_into_their_own_account(self) -> None:
        url = "/api/scenarios/pottery-memory-curation--sculptor--2026-08-29/props"
        self.assertEqual(401, self.client.post(url).status_code)

        first = self.client.post(url, headers=self.alice)
        again = self.client.post(url, headers=self.alice)

        self.assertEqual({"loaded": 15, "already_saved": 0}, first.json())
        self.assertEqual({"loaded": 0, "already_saved": 15}, again.json())
        listed = self.client.get("/api/memories", headers=self.alice).json()
        self.assertEqual(15, len(listed))
        self.assertIn("prop-summary-date-moved", {row["source_prop_id"] for row in listed})
        self.assertTrue(all(row["source_turn_id"] is None for row in listed))
        self.assertEqual([], self.client.get("/api/memories", headers=self.bob).json())
        for unknown in ("index", "no-such-scenario", "..%2Fsecrets"):
            with self.subTest(unknown=unknown):
                self.assertEqual(404, self.client.post(f"/api/scenarios/{unknown}/props", headers=self.alice).status_code)

    def history(self, headers: dict[str, str]) -> list[dict]:
        response = self.client.get("/api/history", headers=headers)
        self.assertEqual(200, response.status_code)
        return response.json()

    def test_history_holds_only_the_readers_own_conversations(self) -> None:
        self.assertEqual(200, self.chat(self.alice).status_code)
        self.session_id = "alice-second-session"
        self.addCleanup(sessions.clear, self.session_id)
        self.assertEqual(200, self.chat(self.alice).status_code)

        history = self.history(self.alice)
        self.assertEqual(
            ["alice-private-session", "alice-second-session"],
            [conversation["session_id"] for conversation in history],
        )
        self.assertEqual(
            [("Hello", "Approved reply")],
            [(t["user_message"], t["assistant_message"]) for t in history[0]["turns"]],
        )
        self.assertEqual([], self.history(self.bob))

    def test_history_keeps_what_inspect_showed_for_each_turn(self) -> None:
        async def release(*args, **kwargs):
            emit_progress("Muse", "draft", "running", "drafting")
            return ReflectionRelease(
                reply="Approved reply",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )

        with patch.object(chat_turn, "reflection_reply", AsyncMock(side_effect=release)):
            streamed = self.client.post(
                "/api/chat/stream",
                headers=self.alice,
                json={"session_id": self.session_id, "turn_id": "t", "message": "Hello"},
            )
        self.assertEqual(200, streamed.status_code)

        details = self.history(self.alice)[0]["turns"][0]["details"]
        self.assertEqual("Approved reply", details["response"]["reply"])
        self.assertIn("inspection", details["response"])
        self.assertIn("Muse", [event["agent"] for event in details["progress"]])

    def test_history_names_a_memory_saved_before_inspect_recorded_it(self) -> None:
        account = AccountContext(auth.account_id_for("alice"))
        main.transcript_store.append_turn(
            account.account_id, self.session_id, "turn-before-handles", "I fill silence.", "Reply.",
            details={"response": {"inspection": {"release": {"capture": {"storage": "committed"}}}}},
        )
        main.memory_service.set_capture_enabled(account, True)
        saved = main.memory_service.save_automatic(account, AutomaticMemoryCandidate(
            text="I fill silence.", source_event_id="turn-before-handles",
            review_allows_capture=True, contains_sensitive_content=False,
        )).record

        memory = self.history(self.alice)[0]["turns"][0]["details"]["response"]["inspection"]["memory"]
        self.assertEqual(saved.memory_id, memory["captured_memory_id"])
        self.assertNotIn("texts", memory)

        with patch.object(main.settings, "linger_dev_inspect", True):
            memory = self.history(self.alice)[0]["turns"][0]["details"]["response"]["inspection"]["memory"]
        self.assertEqual({saved.memory_id: "I fill silence."}, memory["texts"])

    def test_a_saved_conversation_survives_a_restart_for_its_owner_only(self) -> None:
        self.assertEqual(200, self.chat(self.alice).status_code)
        sessions.clear(self.session_id)  # what a server restart does to live state

        self.assertEqual(404, self.chat(self.bob, turn_id="turn-2").status_code)
        self.assertEqual(200, self.chat(self.alice, turn_id="turn-2").status_code)
        self.assertEqual(2, len(self.history(self.alice)[0]["turns"]))
        # Muse sees the restored earlier turn as history, not a blank slate.
        self.assertEqual(4, len(sessions.history(self.session_id)))

    def test_deleting_a_conversation_removes_the_saved_transcript(self) -> None:
        self.assertEqual(200, self.chat(self.alice).status_code)
        self.assertEqual(
            204,
            self.client.delete(
                f"/api/sessions/{self.session_id}", headers=self.alice
            ).status_code,
        )
        self.assertEqual([], self.history(self.alice))


if __name__ == "__main__":
    unittest.main()
