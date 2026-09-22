"""Integration and replay tests for the reviewed curation application loop."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic_ai.models.test import TestModel

from src.linger.agents.provenance.curation_models import (
    CurationFinding,
    CurationProvenanceReview,
)
from src.linger.agents.sculptor.models import (
    CurationProposal,
    DerivedSummary,
    DuplicateLink,
    NoCurationProposal,
    RetrievalRestore,
    RetrievalTombstone,
    TopicGroup,
)
from src.linger.contracts.curation import ApprovedCuration
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    CurationPolicyError,
    MemoryPolicyService,
    MemoryRecord,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.orchestration.curation import (
        CurationSourceMutation,
        InvalidCurationReview,
        run_curation_loop,
    )


class CurationApplicationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = MemoryPolicyService(
            Path(self.directory.name) / "memories"
        )
        self.account = AccountContext("curation-account")
        self.service.set_capture_enabled(self.account, True)

    def seed(self, *texts: str) -> tuple[MemoryRecord, ...]:
        return tuple(
            self.service.save_automatic(
                self.account,
                AutomaticMemoryCandidate(
                    text=text,
                    source_event_id=f"scene-source-{index}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            ).record
            for index, text in enumerate(texts, start=1)
        )

    @staticmethod
    def sculptor_for(action) -> AsyncMock:
        agent = AsyncMock()
        agent.run.return_value = SimpleNamespace(
            output=CurationProposal(
                kind="curation_proposal",
                action=action,
            )
        )
        return agent

    @staticmethod
    def approved_plan(service, account, records, action, review=None):
        from src.linger.orchestration.curation import prepare_curation_plan

        plan = prepare_curation_plan(
            records,
            CurationProposal(kind="curation_proposal", action=action),
            base_state_sha256=service.curation_state_sha256(account),
        )
        return ApprovedCuration(
            plan=plan,
            review=review
            or CurationProvenanceReview(
                proposal_digest=plan.digest,
                decision="allow",
            ),
        )

    @staticmethod
    def allowing_provenance() -> AsyncMock:
        agent = AsyncMock()

        async def run(prompt: str, **_kwargs):
            payload = json.loads(prompt)
            return SimpleNamespace(
                output=CurationProvenanceReview(
                    proposal_digest=payload["proposal_digest"],
                    decision="allow",
                )
            )

        agent.run.side_effect = run
        return agent

    async def test_propose_review_apply_audit_and_curated_read(self) -> None:
        first, second = self.seed(
            "My emergency contact is Maya at 555-0148.",
            "My emergency contact is Maya at 555-0148.",
        )
        sculptor = self.sculptor_for(
            DuplicateLink(
                action="link_duplicates",
                source_memory_ids=(first.memory_id, second.memory_id),
            )
        )
        provenance = self.allowing_provenance()

        result = await run_curation_loop(
            self.account,
            (first.memory_id, second.memory_id),
            service=self.service,
            sculptor=sculptor,
            provenance=provenance,
        )

        self.assertEqual("applied", result.status)
        self.assertTrue(result.source_immutable)
        self.assertIsNotNone(result.application)
        assert result.application is not None
        self.assertTrue(result.application.verification.verified)
        self.assertEqual(1, len(self.service.list_curation_audit(self.account)))
        view = self.service.list_for_retrieval(self.account)
        by_id = {item.memory_id: item for item in view}
        self.assertEqual(
            (second.memory_id,),
            by_id[first.memory_id].duplicate_memory_ids,
        )

        sculptor_payload = json.loads(sculptor.run.await_args.args[0])
        self.assertEqual({"memories"}, set(sculptor_payload))
        provenance_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual(
            {"proposal_digest", "proposal", "sources"},
            set(provenance_payload),
        )
        self.assertNotIn(first.account_key, provenance.run.await_args.args[0])

    async def test_rejected_or_unbound_review_never_reaches_storage(self) -> None:
        first, second = self.seed("A short walk helps.", "The walk was quiet.")
        action = DerivedSummary(
            action="update_derived_summary",
            source_memory_ids=(first.memory_id, second.memory_id),
            summary="A walk always cures anxiety.",
        )
        rejected = AsyncMock()

        async def reject(prompt: str, **_kwargs):
            payload = json.loads(prompt)
            return SimpleNamespace(
                output=CurationProvenanceReview(
                    proposal_digest=payload["proposal_digest"],
                    decision="reject",
                    findings=(
                        CurationFinding(
                            code="unsupported_derivation",
                            source_memory_ids=(first.memory_id, second.memory_id),
                            explanation="The summary overstates the sources.",
                        ),
                    ),
                )
            )

        rejected.run.side_effect = reject
        result = await run_curation_loop(
            self.account,
            (first.memory_id, second.memory_id),
            service=self.service,
            sculptor=self.sculptor_for(action),
            provenance=rejected,
        )
        self.assertEqual("provenance_reject", result.status)
        self.assertEqual((), self.service.list_curation_audit(self.account))

        revise = AsyncMock()

        async def request_revision(prompt: str, **_kwargs):
            payload = json.loads(prompt)
            return SimpleNamespace(
                output=CurationProvenanceReview(
                    proposal_digest=payload["proposal_digest"],
                    decision="revise",
                    findings=(
                        CurationFinding(
                            code="unsupported_derivation",
                            source_memory_ids=(first.memory_id, second.memory_id),
                            explanation="Use qualified language.",
                        ),
                    ),
                )
            )

        revise.run.side_effect = request_revision
        revision_result = await run_curation_loop(
            self.account,
            (first.memory_id, second.memory_id),
            service=self.service,
            sculptor=self.sculptor_for(action),
            provenance=revise,
        )
        self.assertEqual("provenance_revise", revision_result.status)
        self.assertEqual((), self.service.list_curation_audit(self.account))

        unbound = AsyncMock()
        unbound.run.return_value = SimpleNamespace(
            output=CurationProvenanceReview(
                proposal_digest="f" * 64,
                decision="allow",
            )
        )
        with self.assertRaises(InvalidCurationReview) as raised:
            await run_curation_loop(
                self.account,
                (first.memory_id, second.memory_id),
                service=self.service,
                sculptor=self.sculptor_for(action),
                provenance=unbound,
            )
        self.assertEqual("curation_review_unbound", raised.exception.code)
        self.assertEqual((), self.service.list_curation_audit(self.account))

    async def test_source_mutation_fails_closed_with_named_error(self) -> None:
        class MutatingService(MemoryPolicyService):
            selections = 0

            def select_for_curation(self, context, memory_ids):
                records = super().select_for_curation(context, memory_ids)
                self.selections += 1
                if self.selections == 2:
                    return (records[0], replace(records[1], text="Changed after proposal."))
                return records

        service = MutatingService(self.directory.name + "/mutating")
        service.set_capture_enabled(self.account, True)
        first = service.save_automatic(
            self.account,
            AutomaticMemoryCandidate(
                text="A repeated preference.",
                source_event_id="mutating-source-1",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        second = service.save_automatic(
            self.account,
            AutomaticMemoryCandidate(
                text="A repeated preference.",
                source_event_id="mutating-source-2",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=(first.memory_id, second.memory_id),
        )

        with self.assertRaises(CurationSourceMutation) as raised:
            await run_curation_loop(
                self.account,
                (first.memory_id, second.memory_id),
                service=service,
                sculptor=self.sculptor_for(action),
                provenance=self.allowing_provenance(),
            )
        self.assertEqual("curation_source_mutated", raised.exception.code)
        self.assertEqual((), service.list_curation_audit(self.account))

    def test_stale_state_is_named_and_does_not_apply(self) -> None:
        first, second = self.seed("Same preference.", "Same preference.")
        action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=(first.memory_id, second.memory_id),
        )
        approved = self.approved_plan(
            self.service, self.account, (first, second), action
        )
        stale_action = TopicGroup(
            action="assign_topic_group",
            source_memory_ids=(first.memory_id, second.memory_id),
            topic_label="A shared preference",
        )
        stale = self.approved_plan(
            self.service, self.account, (first, second), stale_action
        )
        self.service.apply_curation(self.account, approved)

        with self.assertRaises(CurationPolicyError) as raised:
            self.service.apply_curation(self.account, stale)
        self.assertEqual("curation_state_stale", raised.exception.reason)

    def test_cross_account_plan_is_named_and_does_not_apply(self) -> None:
        first, second = self.seed("Same preference.", "Same preference.")
        action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=(first.memory_id, second.memory_id),
        )
        approved = self.approved_plan(
            self.service, self.account, (first, second), action
        )

        with self.assertRaises(CurationPolicyError) as raised:
            self.service.apply_curation(AccountContext("other-account"), approved)
        self.assertEqual("curation_account_scope_mismatch", raised.exception.reason)

    async def test_no_proposal_skips_provenance_and_storage(self) -> None:
        first, second = self.seed("Unrelated one", "Unrelated two")
        sculptor = AsyncMock()
        sculptor.run.return_value = SimpleNamespace(
            output=NoCurationProposal(
                kind="no_curation_proposal",
                reason="The memories are unrelated.",
            )
        )
        provenance = AsyncMock()

        result = await run_curation_loop(
            self.account,
            (first.memory_id, second.memory_id),
            service=self.service,
            sculptor=sculptor,
            provenance=provenance,
        )

        self.assertEqual("no_change", result.status)
        provenance.run.assert_not_awaited()
        self.assertEqual((), self.service.list_curation_audit(self.account))

    async def test_replays_all_actions_into_one_curated_view(self) -> None:
        first, second, third = self.seed(
            "I plan to grow rosemary on the balcony.",
            "I plan to grow rosemary on the balcony.",
            "I decided to add thyme in a self-watering pot.",
        )

        async def apply(
            action,
            selected: tuple[str, ...],
            expected_states: dict[str, str],
        ):
            provenance = self.allowing_provenance()
            result = await run_curation_loop(
                self.account,
                selected,
                service=self.service,
                sculptor=self.sculptor_for(action),
                provenance=provenance,
            )
            self.assertEqual("applied", result.status)
            payload = json.loads(provenance.run.await_args.args[0])
            self.assertEqual(
                expected_states,
                {
                    source["memory_id"]: source["retrieval_state"]
                    for source in payload["sources"]
                },
            )

        await apply(
            DuplicateLink(
                action="link_duplicates",
                source_memory_ids=(first.memory_id, second.memory_id),
            ),
            (first.memory_id, second.memory_id),
            {first.memory_id: "active", second.memory_id: "active"},
        )
        await apply(
            RetrievalTombstone(
                action="tombstone_for_retrieval",
                source_memory_ids=(second.memory_id, first.memory_id),
                memory_id=second.memory_id,
                canonical_memory_id=first.memory_id,
            ),
            (first.memory_id, second.memory_id),
            {first.memory_id: "active", second.memory_id: "active"},
        )
        await apply(
            DerivedSummary(
                action="update_derived_summary",
                source_memory_ids=(first.memory_id, third.memory_id),
                summary="The balcony garden will begin with rosemary and thyme.",
            ),
            (first.memory_id, third.memory_id),
            {first.memory_id: "active", third.memory_id: "active"},
        )
        await apply(
            TopicGroup(
                action="assign_topic_group",
                source_memory_ids=(first.memory_id, third.memory_id),
                topic_label="Balcony herb garden planning",
            ),
            (first.memory_id, third.memory_id),
            {first.memory_id: "active", third.memory_id: "active"},
        )
        await apply(
            RetrievalRestore(
                action="restore_to_retrieval",
                source_memory_ids=(second.memory_id,),
                memory_id=second.memory_id,
            ),
            (first.memory_id, second.memory_id),
            {second.memory_id: "tombstoned"},
        )

        view = self.service.list_for_retrieval(self.account)
        self.assertEqual(3, sum(item.kind == "original" for item in view))
        self.assertEqual(1, sum(item.kind == "derived_summary" for item in view))
        self.assertEqual(1, sum(item.kind == "topic_group" for item in view))
        self.assertEqual(5, len(self.service.list_curation_audit(self.account)))


if __name__ == "__main__":
    unittest.main()
