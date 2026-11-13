---
name: multi
description: >
  Run two or more agents in parallel on the same task and synthesise their
  results. Mention agents by @name in your message.
  Example: /multi @plan-reviewer @deep-bug-hunter assess the risk of changing
  the ADS-B preamble threshold
argument-hint: "@agent [@agent ...] <task>"
disable-model-invocation: true
---

This skill runs in the main conversation as `pm` (started with
`claude --agent pm`). If you are not running as `pm`, stop and tell Prin.

Spawn each @mentioned agent simultaneously as an independent subagent, giving
each the same task: one Agent tool call per agent in a single message,
`subagent_type` set to the agent's exact name. Only `plan-reviewer`,
`code-writer` and `deep-bug-hunter` exist. You may add a Codex view by also
running the Codex reviewer in Diagnosis mode as described in your agent
definition.

This is an analysis run. Tell every subagent, including `@code-writer` if it
is mentioned, that it must not edit, create or delete any file. Give every
subagent the LEGAL CONSTRAINTS reminder: Mimir is receive-only, and any idea
that involves transmitting is out of bounds.

If a mentioned agent cannot be invoked, report which one and why. Never
substitute a built-in agent such as `general-purpose`.

Wait until all have reported, then synthesise: where they agreed, where they
disagreed, and which recommendation to act on. Write or change nothing until
Prin has confirmed the direction.

Task and mentioned agents:

$ARGUMENTS
