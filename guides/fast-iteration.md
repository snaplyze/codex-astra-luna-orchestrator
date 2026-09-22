# Fast Iteration

For a Sol coordinator with the [Pro profile](full-orchestration.md), override
only the root model and effort:

```toml
model = "gpt-6-sol"
model_reasoning_effort = "medium"
```

Merge these root keys into project `.codex/config.toml` or your personal config.
Sol worker/tester, Luna explorer/researcher, and the Astra reviewer keep their
installed settings. The skill follows the active configuration.

This is an alternative for coding iterations; measure latency and quality on your
tasks. For narrow routine edits, use the [Luna preset](routine-coding.md).

If your active model and account advertise Fast mode, you can additionally set:

```toml
service_tier = "fast"
```

Fast mode trades increased usage for latency. It is optional, separate from model
choice, and omitted from the bundled profiles. Remove the setting if unavailable.
See the [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
