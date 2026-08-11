"""Tests for deterministic policy and Markdown memory storage."""

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
    MemoryNotFoundError,
    MemoryPolicyError,
    MemoryPolicyService,
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
            saved = service.save_explicit(
                self.alice,
                text="Stored directly under memories.",
                source_event_id="default-root",
            ).record

        expected = (
            Path(self.temporary_directory.name)
            / "memories"
            / saved.account_key
            / f"{saved.idempotency_key}.md"
        )
        self.assertTrue(expected.is_file())

    def test_explicit_save_ignores_automatic_policy_and_uses_markdown(self) -> None:
        result = self.service.save_explicit(
            self.alice,
            text="My medical history is mine to save explicitly.",
            source_event_id="explicit-1",
            evidence_ids=("turn-1",),
        )

        self.assertTrue(result.created)
        self.assertFalse(self.service.capture_enabled(self.alice))
        self.assertEqual([result.record], self.service.list_active(self.alice))

        account_key = hashlib.sha256(b"alice").hexdigest()
        account_dir = self.root / account_key
        files = list(account_dir.glob("*.md"))
        self.assertEqual(1, len(files))
        raw = files[0].read_text(encoding="utf-8")
        front_matter, body = raw[4:].split("\n---\n", maxsplit=1)
        metadata = json.loads(front_matter)
        self.assertEqual(account_key, metadata["account_key"])
        self.assertEqual("explicit", metadata["capture_type"])
        self.assertEqual(result.record.idempotency_key, files[0].stem)
        self.assertEqual(result.record.text + "\n", body)
        self.assertNotIn("alice", str(files[0]))
        self.assertEqual([], list(account_dir.glob("*.tmp")))

    def test_automatic_capture_requires_every_policy_rule(self) -> None:
        candidate = AutomaticMemoryCandidate(
            text="A safe memory",
            source_event_id="automatic-1",
            review_allows_capture=True,
            contains_sensitive_content=False,
        )
        with self.assertRaisesRegex(MemoryPolicyError, "automatic_capture_disabled"):
            self.service.save_automatic(self.alice, candidate)

        self.service.set_capture_enabled(self.alice, True)
        rejected = AutomaticMemoryCandidate(
            text="A rejected memory",
            source_event_id="automatic-2",
            review_allows_capture=False,
            contains_sensitive_content=False,
        )
        with self.assertRaisesRegex(MemoryPolicyError, "upstream_review_rejected"):
            self.service.save_automatic(self.alice, rejected)

        sensitive = AutomaticMemoryCandidate(
            text="Sensitive inferred content",
            source_event_id="automatic-3",
            review_allows_capture=True,
            contains_sensitive_content=True,
        )
        with self.assertRaisesRegex(MemoryPolicyError, "sensitive_content"):
            self.service.save_automatic(self.alice, sensitive)

        saved = self.service.save_automatic(self.alice, candidate)
        self.assertTrue(saved.created)
        self.assertEqual("automatic", saved.record.capture_type)
        self.assertEqual(1, len(self.service.list_active(self.alice)))

    def test_capture_preference_is_account_scoped(self) -> None:
        self.service.set_capture_enabled(self.alice, True)

        self.assertTrue(self.service.capture_enabled(self.alice))
        self.assertFalse(self.service.capture_enabled(self.bob))

    def test_repeated_source_event_is_idempotent_but_conflicts_are_rejected(
        self,
    ) -> None:
        first = self.service.save_explicit(
            self.alice,
            text="Keep this once.",
            source_event_id="same-event",
        )
        retry = self.service.save_explicit(
            self.alice,
            text="Keep this once.",
            source_event_id="same-event",
        )

        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.record, retry.record)
        self.assertEqual(1, len(self.service.list_active(self.alice)))

        with self.assertRaises(MemoryConflictError):
            self.service.save_explicit(
                self.alice,
                text="Different content for the same event.",
                source_event_id="same-event",
            )

    def test_correction_preserves_original_and_exposes_only_new_version(self) -> None:
        original = self.service.save_explicit(
            self.alice,
            text="The original words.",
            source_event_id="original-event",
        ).record
        account_dir = self.root / original.account_key
        original_path = account_dir / f"{original.idempotency_key}.md"
        original_bytes = original_path.read_bytes()

        correction = self.service.correct(
            self.alice,
            original.memory_id,
            text="The corrected words.",
            source_event_id="correction-event",
        )

        self.assertTrue(correction.created)
        self.assertEqual(original.memory_id, correction.record.root_memory_id)
        self.assertEqual(original.memory_id, correction.record.supersedes_memory_id)
        self.assertEqual(original_bytes, original_path.read_bytes())
        self.assertEqual([correction.record], self.service.list_active(self.alice))
        with self.assertRaises(MemoryNotFoundError):
            self.service.get_active(self.alice, original.memory_id)

        retry = self.service.correct(
            self.alice,
            original.memory_id,
            text="The corrected words.",
            source_event_id="correction-event",
        )
        self.assertFalse(retry.created)
        self.assertEqual(correction.record, retry.record)

    def test_delete_removes_complete_version_family(self) -> None:
        original = self.service.save_explicit(
            self.alice,
            text="First version",
            source_event_id="delete-original",
        ).record
        correction = self.service.correct(
            self.alice,
            original.memory_id,
            text="Second version",
            source_event_id="delete-correction",
        ).record

        deleted = self.service.delete(self.alice, correction.memory_id)

        self.assertEqual(2, deleted)
        self.assertEqual([], self.service.list_active(self.alice))
        self.assertEqual([], list((self.root / original.account_key).glob("*.md")))

    def test_cross_account_reads_and_mutations_do_not_reveal_memory(self) -> None:
        memory = self.service.save_explicit(
            self.alice,
            text="Alice only",
            source_event_id="alice-event",
        ).record

        self.assertEqual([], self.service.list_active(self.bob))
        with self.assertRaises(MemoryNotFoundError):
            self.service.get_active(self.bob, memory.memory_id)
        with self.assertRaises(MemoryNotFoundError):
            self.service.correct(
                self.bob,
                memory.memory_id,
                text="Bob cannot edit this",
                source_event_id="bob-correction",
            )
        with self.assertRaises(MemoryNotFoundError):
            self.service.delete(self.bob, memory.memory_id)

        self.assertEqual(memory, self.service.get_active(self.alice, memory.memory_id))


if __name__ == "__main__":
    unittest.main()
