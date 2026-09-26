# Plus Profiles

Choose Plus for a GPT-6 Luna root at `max`, Luna execution roles at `high`,
and an independent Astra reviewer at `low`. This preserves the budget-oriented
Luna topology. For complex coding, consider the optional Sol root in
[model selection](model-selection.md).

The standard profile permits four concurrent child threads; `plus-max-2-subagents`
permits two with identical models, reasoning, and routing.

Select Plus or Plus (max 2 subagents) in `setup.sh` or `setup.ps1`. For a manual
installation, copy `codex/` to project `.codex/`, `agents/` to project `.agents/`,
and add the managed instructions from the repository's `AGENTS.md`.

For a global setup, merge the root settings into `~/.codex/config.toml`:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
```

Use `2` for the max-2 variant. Also copy the five role files to
`~/.codex/agents/` and the skill to `~/.agents/skills/codex-orchestrator/`.
Merge global settings without replacing unrelated configuration.
For existing installations, follow the [rename migration guide](migration.md).

Explorer, worker, tester, and researcher pin `gpt-6-luna` at `high`.
Reviewer pins `gpt-6-astra` at `low` with read-only defaults. The reviewer
provides a separate assessment from the model that planned and implemented
the work; use it when independent review adds value.

If you deliberately want every role on Luna, update the reviewer model too.
The skill follows the effective role settings; start a fresh session after
changing files. See [token usage](token-usage.md) to compare representative runs.
