# Synthetic readers for Serendipity

The fixture at `data/synthetic_readers.json` provides repeatable,
non-sensitive demo data. It is not production user data or authentication.

| Reader | Existing history | Standardized connection tests |
| --- | --- | --- |
| Maya | Four days, eight turns, five memories about Alice | identity as a test; wonder beside fear; pressure to conform and belong |
| Theo | Four days, eight turns, five memories about Animal Farm | privilege through administration; persuasion through a shared enemy; a rule reinterpreted to favour the powerful |
| Noor | Four days, eight turns, six cross-book memories | a visual identity connection; rules and ceremony across books; a selectively framed account |

## Test in the UI

1. Open the **Synthetic reader** selector above the chat.
2. Choose Maya, Theo, or Noor. This starts a clean in-process session and
   prepopulates that reader's first test prompt.
3. Send the prompt. After the reviewed response returns, the next prompt is
   prepopulated automatically.
4. Open **Memories** to inspect one unified collection. Fixture records are
   labelled **Synthetic** and reader-created records are labelled **Reader**.
5. Open **Inspect** to verify which Librarian records Serendipity searched and
   which evidence IDs supported its proposal or decline.

The selected fixture is session-scoped. Switching readers starts a fresh chat,
and only the selected reader's authorised memories are available to Librarian.
Synthetic and persisted records share the same list, but edit and delete
controls remain unavailable for read-only fixture records.

## Responsibility boundary

- The fixture stands in for prior chat and automatic memory capture history.
- Librarian returns selected-reader memory records through the same
  `authorised_memory` source used by Serendipity.
- Serendipity remains responsible for deciding whether to search those records,
  comparing candidate connections, and returning one proposal or decline.
- Muse drafts the reader-facing reply; Provenance still reviews it.
