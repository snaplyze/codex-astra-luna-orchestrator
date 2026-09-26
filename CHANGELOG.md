# Changelog

## Unreleased

- Replace managed files through staging and journal rollback per path; preserve
  hardlinked external files and concurrent user work, with conflict recovery copies.
- Keep maintainer instructions out of fresh project installations and carry task
  authority explicitly through delegation briefs and role instructions.
- Report usage scan scope, malformed-input diagnostics, quota windows and rollout
  segments without treating observed tokens as a complete bill.
- Verify Linux, macOS, PowerShell 7 and Windows PowerShell 5.1 with explicit test
  engines; enforce identical shared skill policy across profiles.
- Add the audit execution record and development guide; clarify benchmark quality,
  source-state and cache controls. Model routing and permissions are unchanged.

## 0.3.0 — 2026-09-26

- Rename the project and repository to Codex Orchestrator at
  `snaplyze/codex-orchestrator`.
- Rename the skill to `codex-orchestrator` across all four profiles, installation
  paths, agent instructions, and usage examples.
- Migrate legacy managed instructions in place and archive the previous skill
  outside `skills`, preserving custom files and existing backups.
- Reject malformed or duplicate instruction blocks and restore component changes
  if installation fails.
- Retire the previous GitHub releases and tags. Preserve the project history and
  the existing model routing, permissions, and concurrency limits.

### Upgrade

Update your clone's `origin` to
`https://github.com/snaplyze/codex-orchestrator.git`, pull the release, and rerun
setup. Approve `.codex`, `.agents`, and managed `AGENTS.md` updates together before
starting a new Codex session. Replace custom `$astra-orchestrator` references with
`$codex-orchestrator`. Old references can refer to the retired skill.

For global installations, move the old skill outside discovered skill directories
and copy its renamed replacement. Update scripts pinned to `v0.1.0` or `v0.2.0`
to use `v0.3.0`. See the [migration guide](https://github.com/snaplyze/codex-orchestrator/blob/v0.3.0/guides/migration.md) for exact paths,
backup behavior, and partial-update recovery.

## 0.2.0 — 2026-09-22

- Migrate Plus roots and Luna subagents to GPT-6 Luna; use `high` for Luna
  subagents and retain `max` for Plus coordination.
- Route Pro implementation and testing to GPT-6 Sol at `medium`; retain Astra
  coordination/review and use Luna for exploration/research.
- Preserve all four profile names, five role names, permission defaults, and
  four/two-child concurrency limits.
- Consolidate duplicated orchestration rules into a shorter skill that reads
  effective settings, respects thread limits, and reports model fallbacks.
- Correct installer banners and document rollout, migration, optional Sol
  coordination, and model-specific reasoning choices with official sources.
- Add regression coverage for role models, reasoning, sandbox defaults,
  complete installation output, and upgrades preserving unrelated files.

Update the config, all role files, and the skill together, then start a new Codex
session. Account access depends on the model rollout. These presets have not been
benchmarked against the previous release; the historical token sample remains
unchanged. See [model selection and migration](guides/model-selection.md).

## 0.1.0 — 2026-09-18

- Sync upstream Pro/Plus profiles and add max-2 variants.
- Harden POSIX and PowerShell installers, managed instructions, and rollback.
- Improve token-usage parsing and add Ubuntu/Windows CI coverage.
