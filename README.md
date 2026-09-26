# Codex Orchestrator

<!-- Modified for this distribution: adaptive delegation guidance, setup URL, and maintainer details. -->

A configurable Codex setup with four profiles: standard Pro and Plus profiles allow four concurrent subagent threads, while `pro-max-2-subagents` and `plus-max-2-subagents` cap concurrency at two. Pro uses GPT-6 Astra as root; Plus uses GPT-6 Luna as root.

Repository: [snaplyze/codex-orchestrator](https://github.com/snaplyze/codex-orchestrator).
For an existing installation, follow the [rename migration guide](guides/migration.md).

The installer offers a quality-oriented Pro profile and a budget-oriented Plus profile. Pro uses Astra for coordination, Sol for implementation and testing, and Luna for exploration and research. Plus keeps coordination and execution on Luna. Both retain the independent Astra reviewer. Max-2 variants change only concurrency.

These are project presets, not model access restrictions imposed by your subscription. See [model selection and migration](guides/model-selection.md) for the verified September 22, 2026 release details, routing rationale, and rollout fallback.

## Layout

```text
.
├── profiles/
│   ├── pro/
│   │   ├── codex/           (config.toml and agents/*.toml)
│   │   └── agents/          (skills/codex-orchestrator/SKILL.md)
│   ├── pro-max-2-subagents/  (same Pro settings, max 2 concurrent threads)
│   ├── plus/
│   │   ├── codex/           (config.toml and agents/*.toml)
│   │   └── agents/          (skills/codex-orchestrator/SKILL.md)
│   └── plus-max-2-subagents/ (same Plus settings, max 2 concurrent threads)
├── guides/
│   ├── migration.md
│   ├── model-selection.md
│   ├── fast-iteration.md
│   ├── complex-repo-work.md
│   ├── routine-coding.md
│   ├── full-orchestration.md
│   ├── plus-plan.md
│   └── token-usage.md
├── scripts/
│   └── token_usage.py
├── AGENTS.md
├── CHANGELOG.md
├── setup.sh
├── setup.ps1
└── LICENSE
```

## Current profile configuration

| Role or setting | Pro | Pro max-2 | Plus | Plus max-2 |
|---|---|---|---|---|
| Orchestrator | GPT-6 Astra — medium | GPT-6 Astra — medium | GPT-6 Luna — max | GPT-6 Luna — max |
| Explorer, researcher | GPT-6 Luna — high | GPT-6 Luna — high | GPT-6 Luna — high | GPT-6 Luna — high |
| Worker, tester | GPT-6 Sol — medium | GPT-6 Sol — medium | GPT-6 Luna — high | GPT-6 Luna — high |
| Default subagent | GPT-6 Luna — high | GPT-6 Luna — high | GPT-6 Luna — high | GPT-6 Luna — high |
| Independent reviewer | GPT-6 Astra — low | GPT-6 Astra — low | GPT-6 Astra — low | GPT-6 Astra — low |
| Concurrent subagent limit | 4 | 2 | 4 | 2 |

### Pro — `profiles/pro/codex/config.toml`

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"

approval_policy = "on-request"
sandbox_mode = "workspace-write"

[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
```

### Plus — `profiles/plus/codex/config.toml`

```toml
model = "gpt-6-luna"
model_reasoning_effort = "max"

approval_policy = "on-request"
sandbox_mode = "workspace-write"

[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
```

The installer copies `profiles/<plan>/codex` to `.codex` and
`profiles/<plan>/agents` to `.agents` in the target repository. Each profile
is ready to copy, with no configuration rewriting during setup.

Each role file pins its own model and effort. Changing only `default_subagent_model` affects generic spawned agents, not these named roles. Pro pins worker/tester to Sol `medium`; all Luna subagents use `high`, and every reviewer uses Astra `low`.

The skill reads effective settings instead of duplicating model IDs and efforts. Session overrides and loaded role definitions remain authoritative until you start a new session.

When updating an existing installation, rerun setup and approve `.codex`, `.agents`, and managed `AGENTS.md` updates.
For manual installation, copy the config, role files, skill, and managed instructions together from the selected profile.
Replace `<profile>` below with `pro`, `pro-max-2-subagents`, `plus`, or `plus-max-2-subagents`.

If you want all named roles, including the reviewer, to follow the `[agents]` defaults, remove both the `model` and `model_reasoning_effort` overrides from their role files.

## Project setup

Clone this repository:

```bash
git clone https://github.com/snaplyze/codex-orchestrator.git
cd codex-orchestrator
```

The target project must already exist and must be different from this setup
repository.

### macOS and Linux

Run the shell installer:

```bash
./setup.sh
```

### Windows

Run the PowerShell installer from Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

With PowerShell 7, you can use:

```powershell
pwsh -File .\setup.ps1
```

### Installer prompts

When asked for the target repository, enter its absolute or relative path. For
example:

```text
Target repository path: ../my-project
```

Next, choose your Codex plan:

```text
Codex plan:
  1) Pro  - Astra root; Luna defaults/explore/research; Sol worker/tester; Astra reviewer
  2) Plus - Luna root (max); Luna defaults/roles; Astra reviewer
  3) Pro (max 2 subagents)  - Pro topology with two concurrent subagent threads
  4) Plus (max 2 subagents) - Plus topology with two concurrent subagent threads
Select plan [1-4] (default 1):
```

The selected configuration sets both the root and default subagent reasoning.
The max-2 choices preserve the corresponding models, roles, and reasoning while
limiting concurrent subagent threads to two. Role names are the same in both
plans, but Pro's worker/tester use Sol and Plus's use Luna. Reviewers use Astra
at low effort on all four profiles.

The installer then asks whether to install each component:

- `profiles/<plan>/codex` contains the root configuration and agent role profiles, installed as `.codex`.
- `profiles/<plan>/agents` contains the `codex-orchestrator` skill, installed as `.agents`.
- `AGENTS.md` gives Codex the project-level orchestration instructions. If it
  already exists, setup asks separately before appending to an unmanaged file or
  updating an older managed block, and preserves the user-owned contents.
  Re-running setup recognizes the managed block idempotently, including when the
  file uses CRLF line endings. Symbolic links and incompatible targets are
  skipped.

Press Enter or answer `y` to install a component; answer `n` to skip it. All
three components are selected by default.

If a component already exists, the installer lists the exact paths that would
be overwritten and asks again before making changes:

```text
WARNING: the following existing files will be overwritten:
  - .codex/config.toml
Update .codex? New files will be added; only paths listed above will be replaced. [y/N]
```

Existing-file updates default to `n`. If approved, missing files are added and
only the listed paths are replaced. When migrating an older installation, setup
also lists and archives the legacy skill outside `skills` before installing its
replacement. Other files already present in the target component remain untouched.
Component changes are backed up during the run and
rolled back if a later installation step fails. If you decline one or more
components, setup completes but reports that the installation is partial.

After setup, launch Codex from the target repository. Project-scoped `.codex`
configuration is loaded only for trusted projects.

See `guides/` for copy-paste model presets and the Astra + Sol + Luna topology. The
guides are intentionally separate from the installers so you can review and
adapt settings for your Codex version without changing a global config
automatically.

## Personal/global setup

For agents, copy the TOML files from `profiles/<plan>/codex/agents/` to:

```text
~/.codex/agents/
```

For the skill, copy `profiles/<plan>/agents/skills/codex-orchestrator/` to:

```text
~/.agents/skills/codex-orchestrator/
```

Merge the settings from the matching profile, such as
`profiles/pro/codex/config.toml`, `profiles/pro-max-2-subagents/codex/config.toml`,
`profiles/plus/codex/config.toml`, or
`profiles/plus-max-2-subagents/codex/config.toml`, into your existing:

```text
~/.codex/config.toml
```

Do not blindly overwrite your existing global config if you already have MCP servers, providers, permissions, or other settings.

For an existing global installation, also migrate the previous skill directory
and its instruction references as described in the [migration guide](guides/migration.md#manual-or-global-installations).

## Using the skill

Codex may select the skill automatically when the task matches its description.

You can also invoke it explicitly from Codex CLI or the IDE extension with:

```text
$codex-orchestrator
```

Example prompt:

```text
$codex-orchestrator

Implement the new invoice export endpoint.
Have explorer map the existing invoice/export path first.
Use workers for bounded implementation, tester for verification,
and reviewer for an independent final review.
```

## Suggested topology

All four profiles choose delegation depth according to the task:

| Tier | Task | Workflow |
|---|---|---|
| 1 — Root-only | Small, localized work | Root implements and verifies directly |
| 2 — Lightweight delegation | Bounded work that benefits from separation | One worker completes the assignment; root verifies |
| 3 — Full orchestration | Risky or cross-cutting work with multiple workstreams | Add investigation, testing, and independent review as needed |

Start with the lightest tier that fits. Specialists are conditional, and review
depth follows risk. The diagram shows the available Pro roles; it is not a
mandatory sequence for every task. Plus uses a Luna root with the same routing
policy.

```text
                 GPT-6 Astra
             root / orchestrator
                      |
      +---------------+---------------+
      |               |               |
   explorer          worker         researcher
     Luna              Sol             Luna
      |               |
      +-------+-------+
              |
           tester
             Sol
              |
          reviewer
           Astra
              |
              v
         GPT-6 Astra
      integrate + verify
```

## Tuning

For cheaper/faster runs:

- lower Pro's Astra reasoning from `medium` to `low`
- lower Luna subagent reasoning from `high` to `medium` for simple, bounded tasks
- use Sol `medium` as an optional root for complex coding; see [model selection](guides/model-selection.md)
- choose a max-2 profile when two concurrent threads are enough for the task

For larger codebases:

- consider raising Pro's Astra reasoning to `high`
- start with each role's configured model and effort, then adjust based on results
- use the standard profile's four-thread cap for independent work; the max-2
  profiles intentionally cap concurrency at two
- if you manually raise `max_concurrent_threads_per_session`, confirm that
  your Codex version and plan support the higher limit before relying on it

For strict parent/child separation:

- keep explorer/reviewer/researcher read-only
- keep worker/tester workspace-write
- leave the root in workspace-write so it can integrate changes

## Token usage

Orchestration is not free: the root stays in the loop for the whole task and
every subagent carries its own context. Usage depends on repository size and
task shape, so there is no single number. `scripts/token_usage.py` reads the
rollout logs Codex already writes under `~/.codex/sessions` and reports usage
per thread, role, and model, plus the change in your 5-hour and 7-day rate
limit windows:

```bash
scripts/token_usage.py --list --date 2026-09-07
scripts/token_usage.py --latest --date 2026-09-07
```

See [`guides/token-usage.md`](guides/token-usage.md) for a measurement
protocol, one sample run with real numbers, and tips for reducing usage.

Plus users: long root threads can dominate usage; keeping the root on Luna
is the budget-oriented starting point. Measure representative tasks before
assuming savings. Selecting `Plus` in the installer does this for you; for a
manual or global setup see [`guides/plus-plan.md`](guides/plus-plan.md):

```toml
# Root
model = "gpt-6-luna"
model_reasoning_effort = "max"
```

## Important behavior

Explicit model choices during a spawn override `[agents]` defaults. Custom agent files that specify `model` or `model_reasoning_effort` also take precedence over inherited defaults.

The selected profile determines the root model: Pro uses Astra, while Plus uses
Luna. Pro's worker/tester use Sol; the other execution roles use Luna.
The reviewer is pinned to Astra for an independent final review.

New models roll out by account and workspace. Confirm availability with `/model`
and start a fresh session after updating files. Setup copies configuration; it
does not grant model access or change your global Codex installation.

## License

Maintained by [snaplyze](https://github.com/snaplyze) ([github@snaplyze.me](mailto:github@snaplyze.me)).

Copyright 2026 snaplyze. Applies to modifications in this distribution.

Licensed under the [Apache License 2.0](LICENSE).
