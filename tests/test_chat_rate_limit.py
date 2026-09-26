"""Tests for the deterministic per-account chat request rate limit."""

import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import logfire
from fastapi.testclient import TestClient
from logfire.testing import TestExporter

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import auth, chat_turn, main, rate_limit
    from src.linger.contracts.emotional import EmotionalBoundaryAssessment
    from src.linger.orchestration.reflection import ReflectionRelease


class FakeClock:
    """A monotonic-shaped clock the test controls without ever sleeping."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class ChatRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        clock_patcher = patch.object(rate_limit, "monotonic", self.clock)
        clock_patcher.start()
        self.addCleanup(clock_patcher.stop)
        self.preflight = AsyncMock(
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection")
        )
        boundary_patcher = patch.object(
            chat_turn, "assess_emotional_boundary", self.preflight
        )
        boundary_patcher.start()
        self.addCleanup(boundary_patcher.stop)
        self.gate = AsyncMock(
            return_value=ReflectionRelease(
                reply="Approved reply",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )
        )
        gate_patcher = patch.object(chat_turn, "reflection_reply", self.gate)
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

    def post_chat(
        self,
        client: TestClient,
        session_id: str,
        turn_id: str,
        headers: dict[str, str] | None = None,
    ):
        return client.post(
            "/api/chat",
            json={"session_id": session_id, "turn_id": turn_id, "message": "Hello"},
            headers=headers,
        )

    def post_stream(self, client: TestClient, session_id: str, turn_id: str):
        return client.post(
            "/api/chat/stream",
            json={"session_id": session_id, "turn_id": turn_id, "message": "Hello"},
        )

    def test_tenth_request_is_served_and_eleventh_is_refused(self) -> None:
        with TestClient(main.app) as client:
            responses = [
                self.post_chat(client, "budget-test", f"turn-{index}")
                for index in range(10)
            ]
            eleventh = self.post_chat(client, "budget-test", "turn-10")

        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(429, eleventh.status_code)
        self.assertIn("Retry-After", eleventh.headers)
        self.assertEqual(60, int(eleventh.headers["Retry-After"]))
        self.assertEqual(
            "Too many requests. Please wait a moment and try again.",
            eleventh.json()["detail"],
        )

    def test_refused_request_triggers_no_pipeline_work(self) -> None:
        with TestClient(main.app) as client:
            for index in range(10):
                self.post_chat(client, "no-pipeline-test", f"turn-{index}")
            preflights_before_refusal = self.preflight.await_count
            releases_before_refusal = self.gate.await_count
            refused = self.post_chat(client, "no-pipeline-test", "turn-10")

        self.assertEqual(429, refused.status_code)
        self.assertEqual(preflights_before_refusal, self.preflight.await_count)
        self.assertEqual(releases_before_refusal, self.gate.await_count)

    def test_window_slides_once_the_oldest_request_turns_sixty_seconds_old(self) -> None:
        with TestClient(main.app) as client:
            for index in range(10):
                self.post_chat(client, "sliding-test", f"turn-{index}")
            refused = self.post_chat(client, "sliding-test", "turn-10")
            self.assertEqual(429, refused.status_code)

            # The oldest request has not yet left the window, and waiting the
            # advertised whole second is enough to be served.
            self.clock.now = 59.9
            still_refused = self.post_chat(client, "sliding-test", "turn-11")
            self.assertEqual(429, still_refused.status_code)
            self.assertEqual(1, int(still_refused.headers["Retry-After"]))

            # The oldest request (t=0) is exactly sixty seconds old and leaves.
            self.clock.now = 60.0
            served = self.post_chat(client, "sliding-test", "turn-12")

        self.assertEqual(200, served.status_code)

    def test_hammering_while_refused_does_not_extend_the_lockout(self) -> None:
        with TestClient(main.app, client=("10.0.0.3", 3)) as client:
            for index in range(10):
                self.post_chat(client, "hammer-test", f"turn-{index}")

            self.clock.now = 30.0
            refusals = [
                self.post_chat(client, "hammer-test", f"retry-{index}")
                for index in range(10)
            ]

            # The window still ends sixty seconds after the served requests.
            self.clock.now = 60.0
            served = self.post_chat(client, "hammer-test", "turn-10")

        self.assertTrue(all(r.status_code == 429 for r in refusals))
        self.assertEqual({30}, {int(r.headers["Retry-After"]) for r in refusals})
        self.assertEqual(200, served.status_code)

    def sign_in_as(self, username: str) -> None:
        main.app.dependency_overrides[auth.current_username] = lambda: username

    def test_separate_accounts_have_separate_budgets(self) -> None:
        with TestClient(main.app) as client:
            self.sign_in_as("reader-a")
            responses_a = [
                self.post_chat(client, "session-a", f"turn-{index}")
                for index in range(10)
            ]
            eleventh_a = self.post_chat(client, "session-a", "turn-10")
            self.sign_in_as("reader-b")
            responses_b = [
                self.post_chat(client, "session-b", f"turn-{index}")
                for index in range(10)
            ]

        self.assertTrue(all(r.status_code == 200 for r in responses_a))
        self.assertEqual(429, eleventh_a.status_code)
        self.assertTrue(all(r.status_code == 200 for r in responses_b))

    def test_streaming_endpoint_shares_the_same_budget(self) -> None:
        with TestClient(main.app, client=("10.0.0.9", 9)) as client:
            for index in range(10):
                self.post_chat(client, "shared-budget-test", f"turn-{index}")
            refused = self.post_stream(client, "shared-budget-test", "turn-10")

        self.assertEqual(429, refused.status_code)
        self.assertNotIn("text/event-stream", refused.headers.get("content-type", ""))
        self.assertIn("Retry-After", refused.headers)

    def test_changing_client_address_does_not_split_one_account_budget(self) -> None:
        for index in range(10):
            with TestClient(main.app, client=(f"10.0.0.{index}", index)) as client:
                self.post_chat(
                    client,
                    "moving-test",
                    f"turn-{index}",
                    headers={"X-Forwarded-For": f"203.0.113.{index}"},
                )
        with TestClient(main.app, client=("10.0.0.99", 99)) as client:
            refused = self.post_chat(client, "moving-test", "turn-10")

        self.assertEqual(429, refused.status_code)

    def test_invalid_requests_spend_the_same_budget(self) -> None:
        with TestClient(main.app, client=("10.0.0.5", 5)) as client:
            rejected = [
                client.post("/api/chat", json={"session_id": "invalid-body-test"})
                for _ in range(10)
            ]
            refused = self.post_chat(client, "invalid-body-test", "turn-10")

        self.assertTrue(all(r.status_code == 422 for r in rejected))
        self.assertEqual(429, refused.status_code)

    def test_refusal_telemetry_is_fixed_and_excludes_the_client_address(self) -> None:
        exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
        )
        address_marker = "198.51.100.7"
        session_marker = "qwzxc-private-session-qwzxc"

        with TestClient(main.app, client=(address_marker, 7)) as client:
            for index in range(10):
                self.post_chat(client, session_marker, f"turn-{index}")
            refused = self.post_chat(client, session_marker, "turn-10")

        self.assertEqual(429, refused.status_code)
        payload = json.dumps(exporter.exported_spans_as_dict(), default=str)
        self.assertIn("chat.rate_limit", payload)
        self.assertIn('"failure.code": "rate_limited"', payload)
        self.assertNotIn(address_marker, payload)
        self.assertNotIn("test-reader", payload)
        self.assertNotIn(session_marker, payload)
        self.assertNotIn("HTTPException", payload)


if __name__ == "__main__":
    unittest.main()
