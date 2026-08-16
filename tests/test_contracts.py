"""Tests for typed agent hand-off contracts under src/linger/contracts/."""

import unittest

from pydantic import ValidationError

from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    AccessScope,
    ClarificationRequest,
    EvidenceRecord,
    ExpectedAnswer,
    LibrarianRequest,
    RetrievalFailure,
    RetrievalOptions,
    RetrievalResult,
    SearchedScope,
)
from src.linger.contracts.reading import ReadingBoundary


class ReadingBoundaryTests(unittest.TestCase):
    def test_rejects_unknown_field(self) -> None:
        with self.assertRaises(ValidationError):
            ReadingBoundary(
                chapter_number=5,
                chapter_state="completed",
                extra_field="nope",
            )

    def test_rejects_missing_chapter_state(self) -> None:
        with self.assertRaises(ValidationError):
            ReadingBoundary(chapter_number=5)

    def test_rejects_missing_chapter_number(self) -> None:
        with self.assertRaises(ValidationError):
            ReadingBoundary(chapter_state="completed")

    def test_rejects_non_positive_chapter_number(self) -> None:
        for chapter_number in (0, -1, -100):
            with self.subTest(chapter_number=chapter_number):
                with self.assertRaises(ValidationError):
                    ReadingBoundary(
                        chapter_number=chapter_number,
                        chapter_state="completed",
                    )

    def test_rejects_unsupported_chapter_state(self) -> None:
        with self.assertRaises(ValidationError):
            ReadingBoundary(chapter_number=5, chapter_state="finished")

    def test_valid_boundary_is_frozen(self) -> None:
        boundary = ReadingBoundary(chapter_number=5, chapter_state="completed")
        with self.assertRaises(ValidationError):
            boundary.chapter_number = 6

    def test_both_valid_chapter_states_construct(self) -> None:
        for chapter_state in ("started", "completed"):
            with self.subTest(chapter_state=chapter_state):
                boundary = ReadingBoundary(
                    chapter_number=1,
                    chapter_state=chapter_state,
                )
                self.assertEqual(chapter_state, boundary.chapter_state)


def _access_scope() -> AccessScope:
    return AccessScope(allowed_book_version_ids=("pg11-v01b38ea4",))


def _valid_request() -> LibrarianRequest:
    return LibrarianRequest(
        request_id="libreq_01",
        query="Why does Alice struggle to explain who she is?",
        work_id="pg11",
        book_version_id="pg11-v01b38ea4",
        reading_boundary=ReadingBoundary(chapter_number=5, chapter_state="completed"),
        access_scope=_access_scope(),
        options=RetrievalOptions(),
    )


def _evidence_record() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="pg11-v01b38ea4-ch05-ln0964-0964",
        work_id="pg11",
        book_version_id="pg11-v01b38ea4",
        chapter_id="pg11-v01b38ea4-ch05",
        chapter_number=5,
        location="Chapter 5 — Advice from a Caterpillar",
        source_sha256="01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
        source_lines=(964, 964),
        text="“Who are _you?_” said the Caterpillar.",
    )


def _clarification_request() -> ClarificationRequest:
    return ClarificationRequest(
        kind="clarification",
        request_id="libreq_01",
        clarification_id="clar_01",
        reason_code="current_chapter_state_ambiguous",
        question="Have you finished Chapter 5, or have you only started it?",
        expected_answer=ExpectedAnswer(type="one_of", values=("completed", "started")),
    )


def _retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        kind="result",
        request_id="libreq_01",
        outcome="evidence_found",
        evidence_strength="sufficient",
        strength_reason="The eligible passage directly answers the query.",
        searched_scope=SearchedScope(
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            max_chapter_inclusive=5,
        ),
        evidence=(_evidence_record(),),
    )


def _retrieval_failure() -> RetrievalFailure:
    return RetrievalFailure(
        kind="failure",
        request_id="libreq_01",
        error_code="catalogue_unavailable",
        retryable=True,
    )


class LibrarianContractUnknownFieldTests(unittest.TestCase):
    def test_rejects_unknown_field(self) -> None:
        cases = {
            "AccessScope": (AccessScope, {"allowed_book_version_ids": ("a",)}),
            "RetrievalOptions": (RetrievalOptions, {}),
            "LibrarianRequest": (
                LibrarianRequest,
                {
                    "request_id": "libreq_01",
                    "query": "why?",
                    "work_id": "pg11",
                    "book_version_id": "pg11-v01b38ea4",
                    "reading_boundary": None,
                    "access_scope": _access_scope(),
                    "options": RetrievalOptions(),
                },
            ),
            "ExpectedAnswer": (ExpectedAnswer, {"type": "one_of", "values": ("a",)}),
            "ClarificationRequest": (
                ClarificationRequest,
                {
                    "kind": "clarification",
                    "request_id": "libreq_01",
                    "clarification_id": "clar_01",
                    "reason_code": "current_chapter_state_ambiguous",
                    "question": "Have you finished Chapter 5?",
                    "expected_answer": ExpectedAnswer(
                        type="one_of", values=("completed", "started")
                    ),
                },
            ),
            "SearchedScope": (
                SearchedScope,
                {
                    "work_id": "pg11",
                    "book_version_id": "pg11-v01b38ea4",
                    "max_chapter_inclusive": 5,
                },
            ),
            "RetrievalResult": (
                RetrievalResult,
                {
                    "kind": "result",
                    "request_id": "libreq_01",
                    "outcome": "evidence_found",
                    "evidence_strength": "sufficient",
                    "strength_reason": "Directly answers the query.",
                    "searched_scope": SearchedScope(
                        work_id="pg11",
                        book_version_id="pg11-v01b38ea4",
                        max_chapter_inclusive=5,
                    ),
                },
            ),
            "RetrievalFailure": (
                RetrievalFailure,
                {
                    "kind": "failure",
                    "request_id": "libreq_01",
                    "error_code": "catalogue_unavailable",
                    "retryable": True,
                },
            ),
            "EvidenceRecord": (
                EvidenceRecord,
                {
                    "evidence_id": "alice-ch5-identity",
                    "work_id": "pg11",
                    "book_version_id": "pg11-v01b38ea4",
                    "chapter_number": 5,
                    "location": "Chapter 5",
                    "text": "Who are YOU?",
                },
            ),
        }
        for name, (model_cls, valid_kwargs) in cases.items():
            with self.subTest(model=name):
                with self.assertRaises(ValidationError):
                    model_cls(**valid_kwargs, unexpected_field="nope")


class ExpectedAnswerTests(unittest.TestCase):
    def test_one_of_with_empty_values_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ExpectedAnswer(type="one_of", values=())

    def test_free_text_with_values_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ExpectedAnswer(type="free_text", values=("a",))

    def test_one_of_with_values_constructs(self) -> None:
        answer = ExpectedAnswer(type="one_of", values=("completed", "started"))
        self.assertEqual(("completed", "started"), answer.values)

    def test_free_text_without_values_constructs(self) -> None:
        answer = ExpectedAnswer(type="free_text")
        self.assertEqual((), answer.values)


class LibrarianRequestTests(unittest.TestCase):
    def test_accepts_none_reading_boundary(self) -> None:
        request = LibrarianRequest(
            request_id="libreq_01",
            query="Why does Alice struggle to explain who she is?",
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            reading_boundary=None,
            access_scope=_access_scope(),
            options=RetrievalOptions(),
        )
        self.assertIsNone(request.reading_boundary)

    def test_accepts_valid_reading_boundary(self) -> None:
        request = _valid_request()
        self.assertEqual(5, request.reading_boundary.chapter_number)

    def test_access_scope_rejects_empty_book_version_ids(self) -> None:
        with self.assertRaises(ValidationError):
            AccessScope(allowed_book_version_ids=())

    def test_retrieval_options_rejects_out_of_range_max_final_evidence(self) -> None:
        for max_final_evidence in (0, 50):
            with self.subTest(max_final_evidence=max_final_evidence):
                with self.assertRaises(ValidationError):
                    RetrievalOptions(max_final_evidence=max_final_evidence)

    def test_retrieval_options_rejects_out_of_range_threshold(self) -> None:
        for threshold in (-0.1, 1.1):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValidationError):
                    RetrievalOptions(retrieval_score_threshold=threshold)


class LibrarianResponseAdapterTests(unittest.TestCase):
    def test_round_trips_all_members_by_kind(self) -> None:
        cases = {
            "clarification": (_clarification_request(), ClarificationRequest),
            "result": (_retrieval_result(), RetrievalResult),
            "failure": (_retrieval_failure(), RetrievalFailure),
        }
        for kind, (instance, expected_cls) in cases.items():
            with self.subTest(kind=kind):
                payload = instance.model_dump(mode="json")
                parsed = LIBRARIAN_RESPONSE_ADAPTER.validate_python(payload)
                self.assertIsInstance(parsed, expected_cls)
                self.assertEqual(instance, parsed)

    def test_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ValidationError):
            LIBRARIAN_RESPONSE_ADAPTER.validate_python(
                {"kind": "unknown", "request_id": "libreq_01"}
            )

    def test_result_with_no_evidence_and_no_limitations_constructs(self) -> None:
        result = RetrievalResult(
            kind="result",
            request_id="libreq_01",
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="No eligible passage addresses the query.",
            searched_scope=SearchedScope(
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                max_chapter_inclusive=5,
            ),
        )
        self.assertEqual((), result.evidence)
        self.assertEqual((), result.limitations)


if __name__ == "__main__":
    unittest.main()
