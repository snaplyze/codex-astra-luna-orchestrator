# Plus Profiles

Choose this profile for a Luna root at `max` reasoning and Luna execution
subagents at `medium` reasoning, with an Astra reviewer at `low`.
The standard profile allows four concurrent subagent threads; the
`plus-max-2-subagents` profile keeps the same settings and allows two.

The installers (`setup.sh`, `setup.ps1`) ask for your plan and install the
standard profile automatically when you select `Plus`, or the two-thread
variant when you select Plus (max 2 subagents). Setup copies the selected
`profiles/<plan>/codex/` to `.codex/` and `profiles/<plan>/agents/` to `.agents/`
without rewriting configuration. For manual installation, copy those folders
and the repository's `AGENTS.md` to the target.

For a global setup, merge `profiles/plus/codex/config.toml` into:

`~/.codex/config.toml`

```toml
# Root
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "medium"
```

For the two-thread variant, copy the matching files from
`profiles/plus-max-2-subagents/`.

Subagents keep their pinned models from `.codex/agents/*.toml`. Explorer,
worker, tester, and researcher explicitly set `model = "gpt-5.6-luna"` and
`model_reasoning_effort = "medium"`. The reviewer stays on GPT-6 Astra
on the Plus plan too: it is a single, read-only, `low`-effort thread, and it
gives you an independent review by a different model than the one that
planned and wrote the change. If you want the whole session on Luna, change
`model` in `.codex/agents/reviewer.toml` as well.

See `token-usage.md` for how to measure the difference on your own tasks.

For global installation, also copy `profiles/plus/codex/agents/` to
`~/.codex/agents/` and `profiles/plus/agents/skills/astra-orchestrator/` to
`~/.agents/skills/astra-orchestrator/`. Use the skill from the same profile
as the configuration so its model and reasoning instructions match.
