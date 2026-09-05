### Investigation

**You own the answer. Plan, route, write.**

Read-only requests: "how does X work?", "why was Y built this way?", "are we sure about Z?", "should we do X or Y?". They produce a cited explanation or a recommendation, not a code change.

1. Route through the **how** skill (Explain mode for narrow questions, Critique mode for "are we sure?"). For motivation questions, also route through the **why** skill.
2. Delegate independent evidence gathering when it improves speed or quality. Keep a narrow investigation direct; no throughput checkpoint report is required.
3. Produce the `how`-shaped output (Overview / Key Concepts / How It Works / Where Things Live / Gotchas), or a recommendation with a tradeoffs table if the request is a decision between alternatives.
4. Apply the **unslop** skill to the reply.

A read-only request ends with the explanation or recommendation. When investigation is part of an already authorized implementation task, continue into Bug fix or Feature without a new permission step. Use `architect` only for a consequential unresolved design choice. Git, PR, and monitoring actions require their own applicable authorization.

**Reply:** the investigation output. For "are we sure?" answers, include your real judgment with reasons. Push back if the premise is wrong (see Autonomy).
