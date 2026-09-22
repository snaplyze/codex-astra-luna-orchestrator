# Changelog

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
