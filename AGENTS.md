# Codex Orchestrator project instructions

<!-- Modified for this distribution: adaptive delegation routing guidance. -->

## Maintaining this source repository

Read `docs/audit-remediation.md` and its latest execution checkpoint before
continuing audit remediation, including after context compaction. Use its finding
IDs and acceptance criteria; keep status and verification evidence current.
For development commands and validation boundaries, read `guides/development.md`.

The installed paths below describe target projects. In a clean source checkout,
read `profiles/pro/agents/skills/codex-orchestrator/SKILL.md` directly when the
skill is not discovered; all bundled profiles share that policy. Model defaults
come from the selected profile and active runtime, not the example path.

Preserve user changes. Give each delegated task an explicit mode (audit or
implementation), writable scope and authorized external actions. Delegation does
not expand permissions or require repeating approvals already given. Run focused
regressions and applicable full checks; distinguish unavailable checks from passes.
Do not install this distribution into its own checkout or edit global settings
to satisfy a test. Keep these maintainer rules outside the distributed block.

<!-- BEGIN codex-orchestrator:managed -->
For complex coding tasks, use the `codex-orchestrator` skill when its trigger conditions match.

The root agent owns architecture, scope decisions, delegation, integration, and final verification.
Prefer specialized subagents for bounded exploration, implementation, testing, review, and technical research.

Treat orchestration as adaptive routing, not a fixed pipeline:

- For small, localized work: the root handles it directly.
- For bounded work that benefits from separation: one capable worker may be enough.
- For risky or cross-cutting work: expand into investigation, implementation, verification, and independent review.

Workers get bounded ownership and should finish their assignment rather than repeatedly handing it back.
Every delegation carries the user's task mode, permitted file changes and authorized Git/external actions. Delegation does not expand authority; preserve approvals already given within scope.
Specialists (tester, reviewer, researcher) are conditional, not mandatory pipeline stages.
Review should be proportional to risk rather than automatically invoking the full topology.

Do not delegate trivial work merely for parallelism.
Do not let multiple implementation agents edit the same files without explicit ownership boundaries.
Schedule independent work within the configured child-thread cap; queue excess work or reuse completed agents.
Model and reasoning assignments live in `.codex/config.toml` and `.codex/agents/*.toml`; this file defines behavior and boundaries rather than duplicating configuration.
Use the active runtime role definitions when a session predates a configuration update. Report unavailable models and explicit fallbacks rather than silently substituting them.
User instructions always take precedence over this orchestration policy.
<!-- END codex-orchestrator:managed -->
