"""Tests for the progress-streaming chat transport."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    from apps.backend import chat_turn, main
    from apps.backend.telemetry import run_agent_traced
    from src.linger.contracts.emotional import EmotionalBoundaryAssessment
    from src.linger.orchestration.progress_context import emit_progress
    from src.linger.orchestration.reflection import ReflectionRelease
    from src.linger.services.memory import AccountContext, MemoryPolicyService


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Decode an SSE body into (event, payload) pairs, ignoring comments."""
    frames: list[tuple[str, dict]] = []
    for frame in body.split("\n\n"):
        if not frame.strip() or frame.lstrip().startswith(":"):
            continue
        name = "message"
        data: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            frames.append((name, json.loads("\n".join(data))))
    return frames


class ChatStreamTests(unittest.TestCase):
    session_id = "stream-test"

    def setUp(self) -> None:
        self._memory_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._memory_directory.cleanup)
        main.memory_service = MemoryPolicyService(Path(self._memory_directory.name))
        main.memory_context = AccountContext("chat-stream-test")
        boundary = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            AsyncMock(
                return_value=EmotionalBoundaryAssessment(decision="continue_reflection")
            ),
        )
        boundary.start()
        self.addCleanup(boundary.stop)

    def post_stream(self, message: str, gate: AsyncMock) -> list[tuple[str, dict]]:
        with patch.object(chat_turn, "reflection_reply", gate):
            with TestClient(main.app) as client:
                response = client.post(
                    "/api/chat/stream",
                    json={
                        "session_id": self.session_id,
                        "turn_id": "stream-turn",
                        "message": message,
                    },
                )
        self.assertEqual(200, response.status_code)
        self.assertIn("text/event-stream", response.headers["content-type"])
        return parse_sse(response.text)

    def test_progress_precedes_the_same_atomic_result(self) -> None:
        async def release(*args, **kwargs):
            # Stand in for the agents that normally emit while the turn runs.
            emit_progress("Muse", "draft", "running", "drafting")
            emit_progress("Muse", "draft", "complete", "drafted")
            return ReflectionRelease(
                reply="Approved reply",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )

        frames = self.post_stream("Hello", AsyncMock(side_effect=release))
        names = [name for name, _ in frames]
        self.assertEqual(["progress", "progress", "result"], names)

        first, second = (payload for name, payload in frames if name == "progress")
        self.assertEqual("Muse", first["agent"])
        self.assertEqual("draft", first["stage"])
        self.assertEqual("running", first["status"])
        self.assertEqual(1, first["sequence"])
        self.assertEqual(2, second["sequence"])
        self.assertEqual("complete", second["status"])
        # Elapsed time is monotonic so the UI can show per-agent seconds.
        self.assertGreaterEqual(second["elapsed_ms"], first["elapsed_ms"])
        # Handoff direction drives the Inspect interaction view.
        self.assertIn("input_origin", first)
        self.assertIn("output_receiver", first)

        result = next(payload for name, payload in frames if name == "result")
        self.assertEqual("Approved reply", result["reply"])
        self.assertRegex(result["trace"]["trace_id"], r"^[0-9a-f]{32}$")

    def test_progress_never_carries_request_or_draft_content(self) -> None:
        async def release(*args, **kwargs):
            emit_progress("Muse", "draft", "running", "PRIVATE_READER_MESSAGE")
            return ReflectionRelease(
                reply="Approved reply",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )

        frames = self.post_stream(
            "PRIVATE_READER_MESSAGE", AsyncMock(side_effect=release)
        )
        progress = [payload for name, payload in frames if name == "progress"]
        self.assertTrue(progress)
        for payload in progress:
            self.assertNotIn("PRIVATE_READER_MESSAGE", json.dumps(payload))

    def test_a_traced_agent_stage_reaches_the_stream(self) -> None:
        """Cover the whole chain: endpoint → emitter → run_agent_traced → SSE."""

        class StubAgent:
            async def run(self, prompt: str, **kwargs: object) -> object:
                return SimpleNamespace(output="candidate", usage=lambda: None)

        async def release(*args, **kwargs):
            await run_agent_traced(
                StubAgent(),
                "PRIVATE_PROMPT",
                span_name="agent.muse",
                role="Muse",
                stage="draft",
                input_contract="MuseDraftInput",
                output_contract="MuseCandidate",
                prompt_template_id="muse",
                prompt_digest="digest",
                failure_code="muse_draft_failed",
            )
            return ReflectionRelease(
                reply="Approved reply",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )

        frames = self.post_stream("Hello", AsyncMock(side_effect=release))
        progress = [payload for name, payload in frames if name == "progress"]

        self.assertEqual(
            [("Muse", "draft", "running"), ("Muse", "draft", "complete")],
            [(item["agent"], item["stage"], item["status"]) for item in progress],
        )
        self.assertNotIn("PRIVATE_PROMPT", json.dumps(progress))

    def test_failure_streams_the_atomic_error_contract(self) -> None:
        gate = AsyncMock(side_effect=RuntimeError("private provider failure"))
        frames = self.post_stream("Hello", gate)

        self.assertEqual(["error"], [name for name, _ in frames])
        payload = frames[0][1]
        self.assertEqual("The model call failed. Try again.", payload["detail"])
        self.assertRegex(payload["trace"]["trace_id"], r"^[0-9a-f]{32}$")
        self.assertNotIn("private provider failure", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
