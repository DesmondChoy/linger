"""The Muse draft and revision spans record which reflection modules each run loaded."""

import json
import unittest
from unittest.mock import AsyncMock

import logfire
from logfire.testing import TestExporter

from test_reflection import reflection_reply, result, review
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection,
    reset_connection_inspection,
)
from src.linger.orchestration.turn_context import (
    ToolExposure,
    reset_active_memories,
    reset_tool_exposure,
    reset_turn_evidence,
    set_active_memories,
    set_tool_exposure,
    set_turn_evidence,
)


class ReflectionModuleTraceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._evidence_token = set_turn_evidence(())
        self._connection_token = begin_connection_inspection()
        self._memories_token = set_active_memories(())
        self.exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[logfire.testing.SimpleSpanProcessor(self.exporter)],
        )

    async def asyncTearDown(self) -> None:
        reset_active_memories(self._memories_token)
        reset_connection_inspection(self._connection_token)
        reset_turn_evidence(self._evidence_token)

    def _modules(self, span_name: str) -> list[str]:
        span = next(
            span for span in self.exporter.exported_spans_as_dict()
            if span["name"] == span_name
        )
        value = span["attributes"]["muse.reflection_modules"]
        # The test exporter serialises sequence attributes to JSON.
        return json.loads(value) if isinstance(value, str) else list(value)

    async def test_draft_and_revision_spans_name_their_modules(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Revised reply")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Qualify the claim.")),
            result(review("pass", finding_resolutions=({
                "finding_index": 0,
                "status": "resolved",
                "explanation": "The revised reply removes the draft claim.",
            },))),
        ]
        token = set_tool_exposure(ToolExposure(tools=frozenset({"serendipity_explore"})))
        try:
            release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)
        finally:
            reset_tool_exposure(token)

        self.assertEqual("Revised reply", release.reply)
        self.assertEqual(["connections"], self._modules("muse.draft"))
        self.assertEqual(["revision", "connections"], self._modules("muse.revision"))

    async def test_ungated_turn_records_every_draft_module(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Approved reply")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(["routing", "grounding", "connections"], self._modules("muse.draft"))

    async def test_failed_draft_still_names_its_modules(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = RuntimeError("output retries exhausted")
        provenance = AsyncMock()
        token = set_tool_exposure(ToolExposure(tools=frozenset({"librarian_search"})))
        try:
            await reflection_reply("Hello", [], muse=muse, provenance=provenance)
        finally:
            reset_tool_exposure(token)

        provenance.run.assert_not_called()
        self.assertEqual(["grounding"], self._modules("muse.draft"))


if __name__ == "__main__":
    unittest.main()
