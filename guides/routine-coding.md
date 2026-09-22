# Routine Coding

For predictable, bounded work, lower the [Plus profile](plus-plan.md) root from
`max` to `high`. This uses the recommended starting effort for GPT-6 Luna in
the [official Codex model guidance](https://learn.chatgpt.com/docs/models).

Merge into project `.codex/config.toml` or your personal configuration:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "high"
```

The installed Luna roles remain at `high`; the Astra reviewer stays at `low`.
The skill reads effective settings, so no skill wording needs changing.

For simple edits, stay in the root. Try `medium` only when your own task checks
show it is sufficient. Fast service is a separate usage/latency choice and is
not enabled by this budget-oriented preset.
