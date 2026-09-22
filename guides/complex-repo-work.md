# Complex Repository Work

For architecture changes and difficult debugging, raise the
[Pro profile](full-orchestration.md) root from Astra `medium` to `high`:

```toml
model = "gpt-6-astra"
model_reasoning_effort = "high"
```

Merge these root keys into project `.codex/config.toml` or your personal config.
The Sol worker/tester remain at `medium`, Luna explorer/researcher at `high`,
and the Astra reviewer at `low`. Adjust individual roles only when their task
needs deeper reasoning.

The skill reads effective model settings; no wording edits are required.
Leave service tier unset unless your active model advertises a tier you intend
to use. Higher reasoning and more children can increase usage; compare
[measured runs](token-usage.md).

Use explicit bounded delegation for independent work. Ultra has its own automatic
delegation behavior and is not enabled by these profiles. See
[model selection](model-selection.md) before changing that setting.
