# Token Usage

There is no single token number for this setup. Usage depends on repository
size, task shape, how many subagents the root actually spawns, and how much
of each subagent's context is served from cache. What this guide gives you
instead is a repeatable way to measure your own runs, one sample run for
scale, and the caveats needed to read the numbers correctly.

There are four profile choices: standard Pro and Plus profiles with a
four-thread limit, and `pro-max-2-subagents` plus `plus-max-2-subagents` with
a two-thread limit. Max-2 profiles preserve their corresponding root models,
role models, reasoning efforts, and adaptive routing policy. Pro uses GPT-6
Astra at `medium`; Plus uses GPT-6 Luna at `max`. Both use an Astra reviewer
at `low`. The bundled limits are deliberate; change them manually only after
confirming that your Codex version and plan support a higher concurrency cap.

## What Codex records

Codex stores rollout JSONL under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Root and subagent threads have
separate histories. A revert can create another rollout segment with the same
stable thread ID, so file counts are not thread counts. The relevant fields are:

- `session_meta` (line 1): `id`, `session_id` (the root thread id, shared by
  every subagent), `parent_thread_id`, `cwd`, `cli_version`, and
  `source.subagent.thread_spawn.agent_role` for spawned agents.
- `turn_context`: the `model` and `effort` in force for the turn. Response usage
  is attributed to the model from the preceding context, not one model guessed
  for the entire history. The displayed effort is the final known effort for
  that segment's last model; historical effort changes are not aggregated.
- `token_usage_record`: one per model response, with per-response
  `input_tokens`, `cached_input_tokens`, `output_tokens`,
  `reasoning_output_tokens`, and `total_tokens`.
- `token_count` (inside `event_msg`): optional cumulative totals and independent
  `rate_limits` snapshots. Each primary/secondary window can provide
  `used_percent`, `window_minutes` and `resets_at`; the snapshot can identify
  its `limit_id` and `plan_type`.

Grouping available rollouts by `session_id` estimates recorded usage for an
orchestrated session, split by thread, role, and model. This is not a billing
record. Missing files, legacy formats and partial scans can limit completeness.

Reports distinguish unique threads from rollout segments, describe their scan
scope and include diagnostics for damaged input or conflicting counters.
Implementation status and verification evidence for USG-01 through USG-08 are
tracked in the [remediation plan](../docs/audit-remediation.md).

## Measuring a run

`scripts/token_usage.py` does the grouping. It is standard-library Python and
read-only.

```bash
# Which sessions spawned subagents today?
scripts/token_usage.py --list --date 2026-09-07

# Report on one session (any unique id prefix works)
scripts/token_usage.py --root 01a079f2

# Report on the most recent session that used subagents
scripts/token_usage.py --latest

# Machine-readable output
scripts/token_usage.py --root 01a079f2 --format json
```

Omitting `--date` scans the whole sessions directory, which is slower. `--date`
limits files by their directory date, not by the full lifetime of a session.
A session continued across midnight can have children outside that directory.
Use it for discovery or deliberately partial reports; omit it for a session-wide
scan. Date-filtered reports are explicitly marked partial. An unfiltered scan
still cannot prove that every related rollout exists in the scanned directory.
Codex auto-review (guardian) threads are listed but excluded from totals by
default; add `--include-guardian` to count them.

If you have a plain root-only session to compare against, run the same
command with its id. The script works for sessions with zero subagents.

## Report contract and limitations

Markdown rows identify the thread and rollout segment. Thread counts use stable
IDs across segments; response records from earlier segments remain counted.
Quota labels use recorded durations, or `unknown` when unavailable. Resets or
changed limit identities make the snapshots unsuitable for a simple cost delta.

JSON retains `root` and `threads` and adds:

- `thread_count` and `segment_count`: distinct stable IDs and scanned rollouts.
- `scope`: canonical `date_filter`, `scan`, `partial`, `coverage_unknown` and
  explanatory `limitations`. Unknown coverage remains true even without a date.
- `diagnostics`: input/reconciliation warnings. Treat a partial report as
  observed usable data, not a complete bill.

Each entry in `threads` represents a segment and includes `stable_thread_id`,
`segment` and `segment_count`. `cumulative_total` and `cumulative_fields` preserve
the available cumulative evidence. The Markdown quota line identifies its root
segment; inspect the per-segment JSON snapshots when a root has several rollouts.
It does not merge snapshots with uncertain chronology. If per-response usage is
present, the displayed totals use those records. A mismatch with cumulative evidence produces a diagnostic; the
two values are not added together and an unexplained remainder is not assigned
to a model. Legacy histories without response records use the cumulative fallback.

Exit status is 0 for a rendered report, including a diagnosed partial report;
1 when the scan finds no usable sessions or `--latest` has no eligible session;
2 for invalid arguments, zero or multiple `--root` matches, or a missing sessions
directory. Automated consumers
must inspect diagnostics/scope, not only the exit status. Invalid input is skipped
or rejected with a diagnostic rather than treated as trustworthy zero usage.

## Benchmark protocol

If you want numbers that are comparable across configurations:

1. Pick three or four representative tasks in one repository: a single-file
   fix, a multi-file feature, a cross-component bug, and a research-heavy
   change. Write the prompts down and reuse them verbatim. Define acceptance
   checks before running: tests, required behavior and review criteria. Record
   the exact source commit and prepare a separate disposable checkout of that
   same state for each trial. Do not reuse a previous trial's code changes.
2. Run each task in at least two configurations:
   - Baseline: Astra root only, `[agents] enabled = false`, no skill.
   - Orchestrated: the selected Pro, Pro max-2, Plus, or Plus max-2 profile as installed.
   - Optional floor: Luna root only, to see the cheapest possible run.
3. Use a fresh session for each trial and state the cache conditions you can
   control. Do not claim cold caches if the provider cache cannot be reset.
   Record for every run: acceptance checks and success/partial/fail outcome;
   per-model uncached input, cached input, output and
   reasoning tokens; number of subagents spawned; wall time; and the change
   in comparable `used_percent` snapshots. Record other account activity and
   reset boundaries; omit quota deltas when those conditions are unknown.
4. Repeat each cell two or three times. Variance between runs of the same
   prompt is large enough that a single sample misleads.
5. Record the profile and any overrides: Pro and Pro max-2 use Astra `medium`,
   Sol `medium` worker/tester, and Luna `high` explorer/researcher; Plus and
   Plus max-2 use Luna `max` with Luna `high` execution roles.
   All profiles use an Astra `low` reviewer. Note whether the concurrency
   limit is 4 or 2, plus the Codex version. Caching behaviour and subagent context handling
   change between releases.
6. Compare cost and latency among successful trials, and separately report the
   success fraction and spread. A short incomplete answer is not an economical
   success. Save redacted commands/results sufficient to repeat one trial.

Suggested results table:

| Task / source commit | Config / client | Acceptance result | Astra uncached / cached / out | Sol uncached / cached / out | Luna uncached / cached / out | Subagents | Wall | Comparable quota delta |
|---|---|---|---|---|---|---:|---:|---|

## Reading the numbers

In the historical sample below, 96.3% of input tokens were cache hits.
`total_tokens` is not monetary cost. Read cached input, uncached input and output
separately. A monetary estimate requires model-specific prices, processing tier,
date and an explicit formula; a cache fraction alone does not establish a savings
multiplier. API prices do not establish Plus/Pro allowance consumption.

Rate-limit percentages describe account quota snapshots. The mapping from tokens
to quota consumption is not published and may differ by model. A difference is
only interpretable when both snapshots refer to the same limit and reset period.
Other account activity, resets and missing snapshots prevent attribution to one
task. Read actual window durations when available instead of assuming every
primary/secondary pair is five hours/seven days.

The root thread was the largest line item in the historical sample below. It stays
alive for the whole task, polls subagents, and re-reads its context on every
response. Parallelism trades tokens for latency: every spawned subagent
re-reads its own context on every response.

The auto-review guardian threads are Codex's own approval reviewer, not part
of this setup. They are small but not free.

## Sample run

One run, one repository, one Codex version. Treat it as a scale reference,
not a benchmark.

- Task: cross-component bug fix (file-watcher refresh on external rename) in
  a small TypeScript desktop app, about 16 source files and 6k lines.
- Config: historical setup, before the current Pro/Plus profiles. Astra root at `low`, Luna subagents at
  `medium`, Astra reviewer at `low`.
- Codex `0.153.4`, Plus plan, 2026-09-07.
- Agents spawned: explorer, worker, tester, reviewer (4). Three guardian
  threads excluded.
- Wall time: 13m49s.
- Rate limit: 5h window 0% to 66%, 7d window 31% to 42%.

| Thread | Role | Model / effort | Responses | Uncached in | Cached in | Output | Reasoning | Total | Duration |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `01a079f2` | root | gpt-6-astra / low | 83 | 118,590 | 4,668,928 | 6,860 | 900 | 4,794,378 | 13m49s |
| `01a079f4` | explorer | gpt-5.6-luna / medium | 11 | 50,574 | 538,880 | 2,701 | 727 | 592,155 | 1m34s |
| `01a079f5` | tester | gpt-5.6-luna / medium | 27 | 56,318 | 1,313,024 | 5,329 | 1,918 | 1,374,671 | 11m05s |
| `01a079f5` | worker | gpt-5.6-luna / medium | 34 | 67,089 | 1,842,688 | 8,868 | 1,599 | 1,918,645 | 7m12s |
| `01a079fa` | reviewer | gpt-6-astra / low | 16 | 47,797 | 588,928 | 2,214 | 172 | 638,939 | 3m35s |

| Model | Threads | Responses | Uncached in | Cached in | Output | Reasoning | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-5.6-luna | 3 | 72 | 173,981 | 3,694,592 | 16,898 | 4,244 | 3,885,471 |
| gpt-6-astra | 2 | 99 | 166,387 | 5,257,856 | 9,074 | 1,072 | 5,433,317 |
| all | 5 | 171 | 340,368 | 8,952,448 | 25,972 | 5,316 | 9,318,788 |

Cache hit rate on input: 96.3%.

Takeaways from this single run:

- About 340k uncached input tokens and 26k output tokens did the real work.
  The 9.3M total is almost entirely cache hits.
- The Astra root alone accounted for roughly half of all usage while only
  emitting 6.9k output tokens. Orchestration overhead is mostly the root
  staying in the loop.
- One medium-sized task consumed two thirds of a fresh Plus 5-hour window.
  This historical Astra-root run does not establish the capacity of the
  current Plus profile. Measure fresh runs with the selected profile; use
  the `routine-coding.md` preset or root-only mode for small edits.

## Reducing usage

In rough order of impact:

- On Plus, start with the Luna root and measure the result. Long root threads
  can dominate usage; savings depend on the task and model behavior. The
  installer does this when you select the Plus plan; for manual setups see
  `plus-plan.md`:

  ```toml
  # Root
  model = "gpt-6-luna"
  model_reasoning_effort = "max"
  ```

- Do not orchestrate small tasks. The skill's delegation gate already says
  this; enforce it by not invoking `$codex-orchestrator` for one-file edits.
- Keep `max_concurrent_threads_per_session` low. Each extra concurrent
  subagent is a second full context being re-read on every response.
- Ask subagents for short reports. Raw logs pasted into the root are re-read by the
  root on every subsequent response.
- Skip the reviewer for low-risk changes. It is Astra, and it re-reads the
  diff and surrounding context.
- For simple tasks, try lowering Luna roles from `high` to `medium` and
  compare quality and usage. Pro's worker/tester use Sol; change the intended
  role file rather than only the generic subagent default.

## Contributing results

If you run the protocol on your own projects, open a pull request adding a
row to the table above with the task description, repository size, Codex
version, plan type, and the script output. Please redact repository paths
you do not want published.
