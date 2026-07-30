# Linger

An academic prototype of a provenance-first reflection and memory companion.

## Proposed repository layout

Each agent owns its prompts and reasoning logic, while orchestration, typed hand-offs, and deterministic services remain shared.

```text
linger/
├── apps/
│   ├── api/                    # Backend entry point
│   └── web/                    # User interface
├── src/linger/
│   ├── agents/
│   │   ├── muse/
│   │   ├── librarian/
│   │   ├── sculptor/
│   │   ├── serendipity/
│   │   └── provenance/
│   │       # Each agent: agent.py, prompts/, tests/, README.md
│   ├── orchestration/
│   │   ├── workflow.py         # Reflection, capture, and connection flows
│   │   └── state.py            # Shared workflow state
│   ├── contracts/
│   │   └── models.py           # Typed agent hand-offs
│   └── services/
│       ├── memory_policy/      # Scoped reads, writes, and deletion
│       ├── retrieval/          # Corpus and memory retrieval
│       └── citation/           # Deterministic quotation checks
├── data/                       # Corpus, manifests, and fixtures
├── evals/                      # Fixed evaluation cases and scorers
├── tests/                      # Integration, security, and end-to-end tests
├── docs/                       # Architecture, reports, and risk register
└── deploy/                     # Containers and deployment configuration
```