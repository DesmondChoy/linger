"""The developer trace keeps Serendipity's searches and decision readable."""

import json
import unittest

from apps.backend.dev_trace import DevTraceSink
from src.linger.evaluation_transcript import ConnectionEvaluationEvent


class DevTraceSinkTests(unittest.TestCase):
    def test_connection_events_keep_query_results_and_ranked_decision(self) -> None:
        sink = DevTraceSink()
        sink.record_connection_event(ConnectionEvaluationEvent(
            kind="query", status="sent", source="web", operation="web_search", query="homesickness letters",
        ))
        sink.record_connection_event(ConnectionEvaluationEvent(
            kind="search", status="ok", source="memory", operation="search_memories",
            evidence_json=(json.dumps({"evidence_id": "mem_1", "text": "I reread letters."}),),
        ))
        sink.record_connection_event(ConnectionEvaluationEvent(
            kind="discovery", status="proposal",
            decision_json=json.dumps({"status": "proposal", "shortlist": ["mem_1"]}),
        ))

        events = sink.payload()["connection_events"]

        self.assertEqual("homesickness letters", events[0]["query"])
        self.assertEqual([{"evidence_id": "mem_1", "text": "I reread letters."}], events[1]["evidence"])
        self.assertEqual(["mem_1"], events[2]["decision"]["shortlist"])
        self.assertNotIn("evidence_json", events[1])

    def test_agent_exchange_records_prompt_steps_and_output(self) -> None:
        sink = DevTraceSink()
        handle = sink.begin_agent_exchange(role="Serendipity", stage="exploration", input_prompt="{}")
        sink.complete_agent_exchange(handle, result=None, status="failure", failure_code="timeout")

        exchange = sink.payload()["agent_exchanges"][0]

        self.assertEqual(("Serendipity", "exploration", "failure"), (exchange["role"], exchange["stage"], exchange["status"]))
        self.assertEqual([], exchange["steps"])
        self.assertIsNone(exchange["output"])


if __name__ == "__main__":
    unittest.main()
