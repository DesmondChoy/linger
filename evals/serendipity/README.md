# Serendipity baseline evaluations

This directory owns seven versioned cases for Serendipity's bounded,
source-neutral slice: five book-corpus behaviors, one memory-only connection
that requires no reading context, and one book-to-web connection.

The harness grades response type, decline reason, evidence identity,
presentation policy, and scope deterministically. The usefulness and restraint
of generated connection prose remain a separate human or secondary-LLM review.
A semantic judgment can never override a failed hard gate.

Every case separates the dynamic authority-bearing input from evidence returned
by tools during the run. It declares that Serendipity must search before a
proposal, compare a shortlist, cite only run evidence, and retain no storage or
release authority. Case schema changes are versioned; accepted cases are
extended with reviewed successors rather than silently weakened.
