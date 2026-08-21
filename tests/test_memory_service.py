"""Tests for deterministic automatic-capture policy and Markdown storage."""

import hashlib
import json
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path

from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryConflictError,
    MemoryPolicyError,
    MemoryPolicyService,
)


def candidate(
    text: str,
    source_event_id: str,
    *,
    review_allows_capture: bool = True,
    contains_sensitive_content: bool = False,
) -> AutomaticMemoryCandidate:
    return AutomaticMemoryCandidate(
        text=text,
        source_event_id=source_event_id,
        review_allows_capture=review_allows_capture,
        contains_sensitive_content=contains_sensitive_content,
    )


class MemoryPolicyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "memories"
        self.service = MemoryPolicyService(self.root)
        self.alice = AccountContext("alice")
        self.bob = AccountContext("bob")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_default_store_is_repository_memories_folder(self) -> None:
        with chdir(self.temporary_directory.name):
            service = MemoryPolicyService()
            service.set_capture_enabled(self.alice, True)
            saved = service.save_automatic(
                self.alice,
                candidate("Stored under memories.", "default-root"),
            ).record

        expected = (
            Path(self.temporary_directory.name)
            / "memories"
            / saved.account_key
            / f"{saved.idempotency_key}.md"
        )
        self.assertTrue(expected.is_file())

    def test_automatic_capture_uses_account_scoped_markdown(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        result = self.service.save_automatic(
            self.alice,
            candidate("A safe memory", "automatic-1"),
        )

        account_key = hashlib.sha256(b"alice").hexdigest()
        files = list((self.root / account_key).glob("*.md"))
        self.assertEqual(1, len(files))
        front_matter, body = files[0].read_text(encoding="utf-8")[4:].split(
            "\n---\n", maxsplit=1
        )
        metadata = json.loads(front_matter)
        self.assertEqual(account_key, metadata["account_key"])
        self.assertEqual("automatic", metadata["capture_type"])
        self.assertEqual(result.record.text + "\n", body)
        self.assertNotIn("alice", str(files[0]))
        self.assertEqual([], list(files[0].parent.glob("*.tmp")))

    def test_automatic_capture_requires_every_policy_rule(self) -> None:
        allowed = candidate("A safe memory", "automatic-1")
        with self.assertRaisesRegex(MemoryPolicyError, "automatic_capture_disabled"):
            self.service.save_automatic(self.alice, allowed)

        self.service.set_capture_enabled(self.alice, True)
        with self.assertRaisesRegex(MemoryPolicyError, "upstream_review_rejected"):
            self.service.save_automatic(
                self.alice,
                candidate(
                    "A rejected memory",
                    "automatic-2",
                    review_allows_capture=False,
                ),
            )
        with self.assertRaisesRegex(MemoryPolicyError, "sensitive_content"):
            self.service.save_automatic(
                self.alice,
                candidate(
                    "Sensitive inferred content",
                    "automatic-3",
                    contains_sensitive_content=True,
                ),
            )

        saved = self.service.save_automatic(self.alice, allowed)
        self.assertTrue(saved.created)
        self.assertEqual([saved.record], self.service.list_active(self.alice))

    def test_capture_policy_and_reads_are_account_scoped(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        saved = self.service.save_automatic(
            self.alice,
            candidate("Alice only", "alice-event"),
        ).record

        self.assertTrue(self.service.capture_enabled(self.alice))
        self.assertFalse(self.service.capture_enabled(self.bob))
        self.assertEqual([saved], self.service.list_active(self.alice))
        self.assertEqual([], self.service.list_active(self.bob))

    def test_repeated_source_event_is_idempotent_and_conflicts_fail(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        first = self.service.save_automatic(
            self.alice,
            candidate("Keep this once.", "same-event"),
        )
        retry = self.service.save_automatic(
            self.alice,
            candidate("Keep this once.", "same-event"),
        )

        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.record, retry.record)
        with self.assertRaises(MemoryConflictError):
            self.service.save_automatic(
                self.alice,
                candidate("Different content.", "same-event"),
            )


if __name__ == "__main__":
    unittest.main()
