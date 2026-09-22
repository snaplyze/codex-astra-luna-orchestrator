# Pro Profiles: Astra, Sol, and Luna

Choose Pro for an Astra coordinator, Sol implementation and testing, and Luna
exploration and research. Select Pro in `setup.sh` or `setup.ps1` for four
concurrent child threads, or Pro (max 2 subagents) for two. Setup copies the
selected profile's `codex/` and `agents/` folders without rewriting them.

```text
Astra root (medium)
├── Luna explorer (high)
├── Sol worker (medium)
├── Sol tester (medium)
├── Luna researcher (high)
└── Astra reviewer (low)
```

These are available roles, not five simultaneous children or a required pipeline.
Use only roles that add value, within the selected concurrency cap.

Put root settings in project `.codex/config.toml`, or merge them into
`~/.codex/config.toml` for personal use:

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"

[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
```

The max-2 profile changes only `max_concurrent_threads_per_session` to `2`.
Copy all five role files from the matching profile's `codex/agents/` too:

| Role files | Model | Effort | Sandbox |
|---|---|---|---|
| explorer, researcher | `gpt-6-luna` | `high` | read-only |
| worker, tester | `gpt-6-sol` | `medium` | workspace-write |
| reviewer | `gpt-6-astra` | `low` | read-only |

Named roles override the generic subagent defaults. Copy the matching
`agents/skills/astra-orchestrator/` folder alongside configuration; the skill
reads effective settings so optional overrides do not require prose edits.

See [model selection](model-selection.md) for rationale and availability, or
[Plus](plus-plan.md) for the budget-oriented Luna-root profile.
