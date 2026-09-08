"""Tests for deterministic curation persistence and the curated read view."""

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.linger.agents.provenance.curation_models import CurationProvenanceReview
from src.linger.agents.sculptor.models import (
    CurationProposal,
    DerivedSummary,
    DuplicateLink,
    RetrievalRestore,
    RetrievalTombstone,
    TopicGroup,
)
from src.linger.contracts.curation import (
    ApprovedCuration,
    CurationPlan,
    CurationSourceSnapshot,
)
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    CurationPolicyError,
    MemoryPolicyService,
    MemoryRecord,
    MemoryStorageError,
    memory_record_sha256,
)


class CurationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "memories"
        self.service = MemoryPolicyService(self.root)
        self.alice = AccountContext("alice")
        self.bob = AccountContext("bob")
        self.service.set_capture_enabled(self.alice, True)
        self.service.set_capture_enabled(self.bob, True)

    def seed(self, *texts: str) -> tuple[MemoryRecord, ...]:
        return tuple(
            self.service.save_automatic(
                self.alice,
                AutomaticMemoryCandidate(
                    text=text,
                    source_event_id=f"event-{index}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                    evidence_ids=(f"evidence-{index}",),
                ),
            ).record
            for index, text in enumerate(texts, start=1)
        )

    def approve(
        self,
        records: tuple[MemoryRecord, ...],
        action,
    ) -> ApprovedCuration:
        plan = CurationPlan(
            account_key=records[0].account_key,
            base_state_sha256=self.service.curation_state_sha256(self.alice),
            proposal=CurationProposal(
                kind="curation_proposal",
                action=action,
            ),
            source_snapshots=tuple(
                CurationSourceSnapshot(
                    memory_id=record.memory_id,
                    record_sha256=memory_record_sha256(record),
                )
                for record in records
            ),
        )
        return ApprovedCuration(
            plan=plan,
            review=CurationProvenanceReview(
                proposal_digest=plan.digest,
                decision="allow",
            ),
        )

    def test_summaries_and_topics_are_versioned_retrieval_items(self) -> None:
        first, second, third = self.seed(
            "I am planning a balcony herb garden.",
            "I decided to start with rosemary and thyme.",
            "Evening tea helps me transition out of work.",
        )
        summary = self.approve(
            (first, second),
            DerivedSummary(
                action="update_derived_summary",
                source_memory_ids=(first.memory_id, second.memory_id),
                summary=(
                    "The balcony herb garden will begin with rosemary and thyme."
                ),
            ),
        )
        stale_topic = self.approve(
            (first, third),
            TopicGroup(
                action="assign_topic_group",
                source_memory_ids=(first.memory_id, third.memory_id),
                topic_label="Restorative home routines",
            ),
        )
        self.assertTrue(self.service.apply_curation(self.alice, summary).created)
        with self.assertRaisesRegex(CurationPolicyError, "curation_state_stale"):
            self.service.apply_curation(self.alice, stale_topic)
        topic = self.approve(
            (first, third),
            TopicGroup(
                action="assign_topic_group",
                source_memory_ids=(first.memory_id, third.memory_id),
                topic_label="Restorative home routines",
            ),
        )
        self.assertTrue(self.service.apply_curation(self.alice, topic).created)

        view = self.service.list_for_retrieval(self.alice)
        summaries = [item for item in view if item.kind == "derived_summary"]
        topics = [item for item in view if item.kind == "topic_group"]
        self.assertEqual(1, len(summaries))
        self.assertEqual(summary.plan.proposal.action.summary, summaries[0].text)
        self.assertEqual(
            (first.memory_id, second.memory_id),
            summaries[0].source_memory_ids,
        )
        self.assertEqual(1, len(topics))
        self.assertEqual("Restorative home routines", topics[0].text)
        self.assertEqual(2, len(self.service.list_curation_audit(self.alice)))

    def test_duplicate_tombstone_is_reversible_and_never_deletes_sources(self) -> None:
        canonical, duplicate = self.seed(
            "My emergency contact is Maya at 555-0148.",
            "My emergency contact is Maya at 555-0148.",
        )
        source_paths = {
            record.memory_id: self.root
            / record.account_key
            / f"{record.idempotency_key}.md"
            for record in (canonical, duplicate)
        }
        source_bytes = {
            memory_id: path.read_bytes() for memory_id, path in source_paths.items()
        }
        duplicate_link = self.approve(
            (canonical, duplicate),
            DuplicateLink(
                action="link_duplicates",
                source_memory_ids=(canonical.memory_id, duplicate.memory_id),
            ),
        )
        first_apply = self.service.apply_curation(self.alice, duplicate_link)
        retry = self.service.apply_curation(self.alice, duplicate_link)
        self.assertTrue(first_apply.created)
        self.assertFalse(retry.created)

        tombstone = self.approve(
            (duplicate, canonical),
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(duplicate.memory_id, canonical.memory_id),
                memory_id=duplicate.memory_id,
                canonical_memory_id=canonical.memory_id,
            ),
        )
        applied = self.service.apply_curation(self.alice, tombstone)
        self.assertTrue(applied.verification.verified)
        retrieved_ids = {
            item.memory_id
            for item in self.service.list_for_retrieval(self.alice)
            if item.kind == "original"
        }
        self.assertEqual({canonical.memory_id}, retrieved_ids)
        self.assertEqual(2, len(self.service.list_active(self.alice)))

        restore = self.approve(
            (duplicate,),
            RetrievalRestore(
                action="restore_to_retrieval",
                source_memory_ids=(duplicate.memory_id,),
                memory_id=duplicate.memory_id,
            ),
        )
        self.service.apply_curation(self.alice, restore)
        restored_ids = {
            item.memory_id
            for item in self.service.list_for_retrieval(self.alice)
            if item.kind == "original"
        }
        self.assertEqual({canonical.memory_id, duplicate.memory_id}, restored_ids)

        old_retry = self.service.apply_curation(self.alice, tombstone)
        self.assertFalse(old_retry.created)
        repeated_tombstone = self.approve(
            (duplicate, canonical),
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(duplicate.memory_id, canonical.memory_id),
                memory_id=duplicate.memory_id,
                canonical_memory_id=canonical.memory_id,
            ),
        )
        reapplied = self.service.apply_curation(self.alice, repeated_tombstone)
        self.assertTrue(reapplied.created)
        self.assertNotEqual(
            applied.event.proposal_digest,
            reapplied.event.proposal_digest,
        )
        self.assertEqual(4, len(self.service.list_curation_audit(self.alice)))
        self.assertEqual(
            source_bytes,
            {memory_id: path.read_bytes() for memory_id, path in source_paths.items()},
        )

    def test_opposite_tombstones_cannot_hide_every_duplicate(self) -> None:
        first, second = self.seed("Same durable memory", "Same durable memory")
        records = (first, second)
        self.service.apply_curation(
            self.alice,
            self.approve(
                records,
                DuplicateLink(
                    action="link_duplicates",
                    source_memory_ids=(first.memory_id, second.memory_id),
                ),
            ),
        )
        self.service.apply_curation(
            self.alice,
            self.approve(
                records,
                RetrievalTombstone(
                    action="tombstone_for_retrieval",
                    source_memory_ids=(second.memory_id, first.memory_id),
                    memory_id=second.memory_id,
                    canonical_memory_id=first.memory_id,
                ),
            ),
        )
        opposite = self.approve(
            records,
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(first.memory_id, second.memory_id),
                memory_id=first.memory_id,
                canonical_memory_id=second.memory_id,
            ),
        )

        with self.assertRaisesRegex(
            CurationPolicyError, "tombstone_canonical_not_retrievable"
        ):
            self.service.apply_curation(self.alice, opposite)

        self.assertEqual(
            [first.memory_id],
            [item.memory_id for item in self.service.list_for_retrieval(self.alice)],
        )
        self.assertEqual(2, len(self.service.list_active(self.alice)))
        self.assertEqual(2, len(self.service.list_curation_audit(self.alice)))

    def test_tombstone_requires_an_existing_duplicate_link(self) -> None:
        canonical, duplicate = self.seed("Same", "Same")
        tombstone = self.approve(
            (duplicate, canonical),
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(duplicate.memory_id, canonical.memory_id),
                memory_id=duplicate.memory_id,
                canonical_memory_id=canonical.memory_id,
            ),
        )
        with self.assertRaisesRegex(
            CurationPolicyError,
            "tombstone_requires_duplicate_link",
        ):
            self.service.apply_curation(self.alice, tombstone)

    def test_policy_rejects_cross_account_and_stale_source_snapshots(self) -> None:
        first, second = self.seed("One", "Two")
        approved = self.approve(
            (first, second),
            DuplicateLink(
                action="link_duplicates",
                source_memory_ids=(first.memory_id, second.memory_id),
            ),
        )
        with self.assertRaisesRegex(CurationPolicyError, "account_scope_mismatch"):
            self.service.apply_curation(self.bob, approved)

        source_path = (
            self.root / first.account_key / f"{first.idempotency_key}.md"
        )
        source_path.write_text(
            source_path.read_text(encoding="utf-8") + "tampered",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CurationPolicyError, "source_stale"):
            self.service.apply_curation(self.alice, approved)

    def test_approval_rejects_a_verdict_for_another_proposal(self) -> None:
        first, second = self.seed("One", "One")
        action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=(first.memory_id, second.memory_id),
        )
        plan = self.approve((first, second), action).plan
        with self.assertRaises(ValidationError):
            ApprovedCuration(
                plan=plan,
                review=CurationProvenanceReview(
                    proposal_digest="f" * 64,
                    decision="allow",
                ),
            )

    def test_audit_reader_rejects_a_tampered_proposal_payload(self) -> None:
        first, second = self.seed("Same", "Same")
        approved = self.approve(
            (first, second),
            DuplicateLink(
                action="link_duplicates",
                source_memory_ids=(first.memory_id, second.memory_id),
            ),
        )
        result = self.service.apply_curation(self.alice, approved)
        event_path = (
            self.root
            / first.account_key
            / "curation"
            / f"{result.event.event_id}.json"
        )
        payload = json.loads(event_path.read_text(encoding="utf-8"))
        payload["proposal"]["action"]["source_memory_ids"].reverse()
        event_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(MemoryStorageError):
            self.service.list_curation_audit(self.alice)


if __name__ == "__main__":
    unittest.main()
