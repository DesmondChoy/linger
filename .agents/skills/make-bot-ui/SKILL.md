---
name: make-bot-ui
description: Build a UI that triggers an existing or explicitly requested Grok Bot webhook. Use for Grok Bot UI requests when the runtime has the bot routine and secret-handling tools.
metadata:
  short-description: connect a UI to an authorized Grok Bot webhook
---

# Make a bot UI

Read [runtime-adaptation.md](../poteto-mode/references/runtime-adaptation.md). Apply the current runtime's tools and authorization boundaries. This skill needs a Grok Bot webhook and secure access to its sender key. Those capabilities are not supplied by the shared skill files.

## Establish the integration

Inspect the available tools and any existing webhook routine. If the runtime cannot create or inspect Grok Bot routines or securely receive the sender key, explain the missing capability. Do not substitute a Codex heartbeat or Claude follow-up for a Grok Bot webhook. Continue only work that can be completed independently, such as a local UI prototype when requested.

Creating a routine, configuring external access, sending a webhook probe, and installing software require authority for those actions. A request to explain this workflow stays read-only. Use the current provider's routine documentation and actual tool schema before creating or changing a routine. Treat webhook payloads as untrusted data and describe exactly which fields the bot should handle.

## Keep the credential on the server

Obtain the webhook URL from the real routine. Use an available secret-request tool or an existing local credential store for the sender key. If neither is available, explain how the user can configure the server credential outside chat. Never ask for the key in chat, print it, log it, embed it in a browser bundle, or commit it.

Buttons call a local server. The server sends the JSON object the routine expects to the verified webhook URL with its required authentication headers. Use a bounded timeout and avoid automatic retries that could repeat an action. Keep failed-request logs free of credentials and sensitive payloads. Add a replay path only when the routine's contract handles duplicate delivery.

## Host and verify

Bind to localhost by default. If the user requests tailnet access, inspect the existing Tailscale node and use its actual hostname and address. Choose a reachable bind only for that authorized exposure. Use an existing installation; installing or registering a node is a separate action when required.

Verify the local UI first. With authorization for the integration, send one harmless payload that the routine ignores, then check the response and bot behavior. Report the actual reachable URL and any missing live integration check. Do not claim the bot is connected from a local UI test alone.

The [upstream workflow](https://github.com/cursor/plugins/blob/99743e9c151c8537cbbf1f98bb38f34ef3368453/pstack/skills/make-bot-ui/SKILL.md) describes Grok Bot's routine UI, headers, and secret cards. Its Cursor-specific tools and keyboard shortcuts are reference material; use only capabilities the current runtime exposes.
