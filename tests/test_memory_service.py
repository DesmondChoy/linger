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

    def test_automatic_capture_vetoes_shaped_personal_data_or_secrets(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        for index, text in enumerate((
            "Reach me at jane.doe@example.com if you want to talk.",
            "My SSN is 123-45-6789 just so you know.",
            "Here's my key: sk-ant-abcdefghijklmnopqrstuvwx1234",
            "Ring me on +44 20 7946 0958 once you finish it.",
            "My number is 415-555-0132 if you want to talk it over.",
            "She left a card reading (415) 555-0132 inside the cover.",
            "Text +1-800-273-8255 when the ending lands badly.",
        )):
            with self.subTest(text=text):
                with self.assertRaises(MemoryPolicyError) as caught:
                    self.service.save_automatic(
                        self.alice,
                        candidate(text, f"private-{index}"),
                    )
                self.assertEqual(
                    "personal_data_or_secret_not_allowed", caught.exception.reason
                )
        self.assertEqual([], self.service.list_active(self.alice))

    def test_automatic_capture_allows_ordinary_numeric_reflective_text(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        for index, text in enumerate((
            "I loved the scene on p. 214 where she finally speaks her mind.",
            "This reminded me of 1984 and how bleak that ending felt.",
            "Chapter 12 was where everything changed for me.",
            "We talked at 10:30 about the ending.",
            "The war ran from 1914-1918 and the whole book sits inside it.",
            "I own ISBN 0-306-40615-2, the edition with the blue spine.",
            "The reprint is ISBN 978-0-306-40615-7 and ISBN 9780306406157.",
            "I finished it on 2024-05-17 after a very long week.",
            "I finished it on 17/05/2024 after a very long week.",
            "John 3:16 gets quoted twice, and section 12.4.2 explains why.",
            "Pages 214-238 are the strongest, and pp. 100-1000 drag.",
            "Volume 3, pages 301-4500 in the collected edition.",
            "Smith (1997) 100-200 is the citation I keep returning to.",
            "The 1999 edition and the 2014 reprint end differently.",
            "The hardback cost 12.99 and still felt worth it.",
        )):
            with self.subTest(text=text):
                saved = self.service.save_automatic(
                    self.alice,
                    candidate(text, f"ordinary-{index}"),
                )
                self.assertEqual(text, saved.record.text)

    def test_upstream_refusals_take_precedence_over_the_pattern_screen(self) -> None:
        self.service.set_capture_enabled(self.alice, True)
        private = "Reach me at jane.doe@example.com about the ending."
        cases = (
            ("upstream_review_rejected_capture", {"review_allows_capture": False}),
            ("sensitive_content_not_allowed", {"contains_sensitive_content": True}),
        )
        for expected, flags in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(MemoryPolicyError) as caught:
                    self.service.save_automatic(
                        self.alice,
                        candidate(private, f"precedence-{expected}", **flags),
                    )
                self.assertEqual(expected, caught.exception.reason)

        self.service.set_capture_enabled(self.alice, False)
        with self.assertRaises(MemoryPolicyError) as caught:
            self.service.save_automatic(
                self.alice,
                candidate(private, "precedence-disabled"),
            )
        self.assertEqual("automatic_capture_disabled", caught.exception.reason)
        self.assertEqual([], self.service.list_active(self.alice))

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
