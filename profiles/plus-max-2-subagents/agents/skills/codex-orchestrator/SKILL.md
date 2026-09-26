---
name: codex-orchestrator
description: Coordinate Codex work that benefits from bounded delegation, independent research or review, or parallel workstreams. Use for cross-component changes and explicit subagent requests; keep small localized tasks in the root.
---

# Codex Orchestrator

<!-- Modified for this distribution: GPT-6 routing and bounded delegation. -->

The root owns scope, architecture, delegation, integration, and final verification.
User instructions take precedence over this skill.

## Resolve the active profile

Read the relevant model, effort, concurrency, and role settings in the installed
`.codex/config.toml` and `.codex/agents/*.toml`, or their user-level equivalents
for a global installation. Inspect only needed settings; do not expose secrets.
Explicit session overrides and the active tool's role definitions take precedence
over files edited after the session started.

The profiles intentionally use different models for different work. Plus keeps a
Luna root and Luna execution roles. Pro uses an Astra root, Sol worker/tester, and
Luna explorer/researcher. Both keep an independent Astra reviewer. Exact model IDs
and reasoning efforts belong in the TOML files, not in duplicated spawn rules here.

Use the configured named roles when they match the task. A model name written in a
task message does not select that model. Do not switch the root model or rewrite
installed configuration merely to perform a delegated task.

## Choose the lightest useful routing

- **Tier 1 — Root-only:** small, localized work without a useful independent
  subtask. Implement and verify directly.
- **Tier 2 — Bounded delegation:** a focused implementation, research question,
  or review benefits from separation. One capable specialist can be enough;
  the root does useful independent work and verifies the result.
- **Tier 3 — Coordinated work:** multiple independent workstreams or a risky
  cross-component change needs investigation, implementation, and verification.
  Add specialists only where they improve correctness or throughput.

File count alone does not determine the tier. A test file plus its implementation
does not automatically require a full team. Review depth follows risk.

For Tier 2 or 3, actually call the available spawn tool before doing the delegated
work yourself. If delegation is unavailable or rejected, report the limitation
and choose a supported retry or explicit root fallback. Never claim simulated
delegation. Honor a user's explicit request for independent review when deciding
whether a root fallback can satisfy the task.

## Select a role

- `explorer`: read-only repository mapping, call paths, tests, and dependencies.
- `researcher`: read-only current external facts and version-specific APIs;
  require primary sources and distinguish verified facts from inference.
- `worker`: bounded implementation with file ownership and focused checks.
- `tester`: reproduction, meaningful regression tests, and verification.
- `reviewer`: read-only review of the actual diff for material defects.

Do not spawn every role as a pipeline. An explorer is unnecessary when the code
path is understood; a worker can run its own focused tests. Add an independent
tester or reviewer when the risk or uncertainty justifies a separate check.

## Construct a bounded delegation

Before each spawn, inspect the active tool schema. Use its actual parameter names,
supported roles, and available models.

For tools that support `fork_turns`, use `"none"` for bounded tasks and provide a
self-contained brief. Do not combine `fork_turns = "all"` with explicit role,
model, or effort parameters when the schema forbids it. Full-history inheritance
is appropriate only when deliberately needed and supported.

Prefer `agent_type` with a matching installed role. Do not redundantly override
fixed role settings. If a different model is justified but a fixed role cannot
accept overrides, use a supported configurable role with the intended role
instructions and the same permission boundaries. Otherwise report the limitation.

Every brief contains:

1. Objective and repository path.
2. Relevant files, evidence, and necessary context.
3. Ownership: writable files or an explicit read-only assignment.
4. Constraints, including what would require a parent decision.
5. Deliverable and acceptance criteria, including focused verification.

Example, only when these fields are supported by the active tool:

```json
{
  "task_name": "export_validation",
  "agent_type": "explorer",
  "fork_turns": "none",
  "message": "Read-only: trace invoice export validation in /workspace/project. Read AGENTS.md. Return responsible files, existing tests, and the smallest implementation boundary. Do not edit files."
}
```

Keep one implementation owner per file or subsystem. Workers finish the bounded
assignment, including relevant checks, and return evidence rather than handing
routine decisions back to the parent.

## Schedule within the limit

Use the effective `agents.max_concurrent_threads_per_session` limit and any
stricter runtime limit. The profile cap counts child threads, excluding the root.
A max-2 profile changes concurrency only; it does not change reasoning or models.

Start independent assignments before waiting, up to available capacity. Queue
excess work in waves or reuse completed agents with the available follow-up tool.
Do not assume five available role definitions permit five simultaneous children.
Serialize dependent edits and never run overlapping writers without coordinated
ownership. Keep the root busy with integration, investigation, or verification
that does not duplicate the delegated assignment.

## Escalation and model availability

Keep focused tasks on their configured model. If Luna reports a reasoning blocker
after a focused attempt, the root can narrow the task, supply missing evidence,
or select Sol for the bounded complex work when available. Use Astra for difficult
architectural or security decisions when the risk justifies it. Preserve the user's
budget and model constraints; report a material escalation.

Higher reasoning is not a substitute for missing requirements or failing tools.
Raise effort for demonstrated reasoning difficulty rather than automatically
using `max` everywhere. Luna supports up to `max`, not `ultra`; use only efforts
advertised for the selected model. Do not enable automatic Ultra delegation on top
of this explicit routing without deliberately accounting for its extra work.

A model appearing in metadata does not prove account access during rollout.
On an unavailable-model error, report the rejected ID and check the active picker
or supported model list. Do not silently substitute models or change global
configuration. Use a confirmed available fallback within the user's constraints,
or request the missing decision if no acceptable fallback exists.

## Integrate and finish

Subagents return conclusions, changed paths, commands and results, and remaining
risks. Keep raw logs and copied context out of the parent unless needed as evidence.
Architecture changes, new dependencies, security decisions, and ownership conflicts
go back to the root before the worker expands scope.

For a failed assignment, inspect the cause, then narrow, retry, reassign, or handle
it in the root with the fallback disclosed. Avoid repeating the same failed call.

Before completion, account for every required assignment: completed and integrated,
or explicitly failed with its impact explained. Do not finish with required agents
still running. Resolve conflicting findings, inspect the final diff, and run or
confirm the narrowest checks that establish the requested behavior.

Report the outcome, verification evidence, and remaining gaps. Claim a model or
delegated action was used only when a successful spawn and runtime role/model
information support that claim.
