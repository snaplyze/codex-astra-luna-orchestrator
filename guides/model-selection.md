# Model Selection and GPT-6 Migration

Verified on September 22, 2026 against official OpenAI documentation and local
Codex CLI 0.155.1 model metadata. Metadata and documentation confirm supported
configuration; they do not prove that every account can run a model.

## What changed

OpenAI released GPT-6 Sol and GPT-6 Luna in Codex and ChatGPT Work. Access is
rolling out across paid plans and depends on client and workspace settings.
Use `/model` in Codex to check your account.
[Release announcement](https://learn.chatgpt.com/docs/changelog)

| Model ID | Intended workload | Standard API input / output per 1M tokens |
|---|---|---|
| `gpt-6-luna` | Focused, repeatable, high-volume tasks | $0.10 / $0.50 |
| `gpt-6-sol` | Complex coding and agentic workflows | $2.00 / $10.00 |

Prices are API rates, not Plus/Pro allowances. See the official
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) model pages for
caching, context-length, and processing-tier conditions. This repository does
not infer subscription savings from API price ratios.

OpenAI recommends starting explicit subagent settings at Luna `high`, Sol
`medium`, and Astra `low`. Reasoning levels are not directly equivalent across
generations. [Subagent guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents)

## Routing choices in this repository

These are maintainers' presets, not benchmark results or plan restrictions:

- **Plus:** keep the Luna root at `max` for coordination, upgrade it to GPT-6,
  and use Luna `high` for bounded execution. The [routine preset](routine-coding.md)
  lowers root effort when the task does not need that depth.
- **Pro:** retain Astra `medium` for coordination, use Sol `medium` for
  implementation/testing, and Luna `high` for exploration/research. This
  replaces the old policy of running every execution role on Luna `max`.
- **Both:** retain an independent Astra `low` reviewer. Generic children
  default to Luna `high`; use named roles for the intended specialization.
- **Max-2:** change concurrency from four child threads to two, nothing else.

Sol is available as an optional coordinator on either profile. To select it,
change only these root keys in the effective configuration:

```toml
model = "gpt-6-sol"
model_reasoning_effort = "medium"
```

Named role models remain pinned. Choose the Pro role files if you also want
Sol worker/tester. To use Sol for one difficult delegated task, the orchestrator
must select it through the actual spawn tool and preserve the role's instructions
and permissions; mentioning Sol in a brief does not configure a model.

## Upgrade an existing project

For the repository and skill rename, first follow the [migration guide](migration.md).

1. Pull this release and rerun `setup.sh` or `setup.ps1` for the target project.
2. Select the same profile or intentionally choose a different one.
3. Review and approve updates to `.codex`, `.agents`, and managed `AGENTS.md` instructions. Updating only the
   root config leaves named role pins and old skill instructions behind.
4. Start a new Codex session in the trusted target project. Check `/model`
   and the loaded roles before relying on the new topology.
5. Compare representative tasks using [the measurement protocol](token-usage.md).
   Installer and configuration tests do not measure model quality or live access.

For manual/global installation, merge root settings and copy all five role files
and the skill together. Preserve unrelated providers, plugins, and permissions.

## Availability and fallback

If Codex rejects a new model, check rollout status and workspace access first.
Do not assume an API listing or a cached picker entry grants access. GPT-5.6
models remain available during rollout according to the
[model guide](https://learn.chatgpt.com/docs/models).

For a temporary fallback, select models your account actually supports. For
example, replace unavailable Luna pins with `gpt-5.6-luna` in the root (Plus),
generic default, and affected role files together. If Sol is unavailable, use a
confirmed available execution model in both Pro worker/tester files. Use an effort
that model supports. Record the override and start a new session; setup does not
perform silent substitutions.

Luna supports up to `max`, not `ultra`. Ultra on supported models adds automatic
delegation; these profiles use explicit routing and do not enable it. Model
availability, supported effort, and actual runtime overrides take precedence over
a copied example. [Model and reasoning guidance](https://learn.chatgpt.com/docs/models)
