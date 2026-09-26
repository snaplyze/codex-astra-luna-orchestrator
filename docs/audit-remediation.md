# Audit remediation — 2026-09-26

## Scope and resume contract

This is the single execution record for the engineering audit of HEAD
`2eb8173211a90eb45335617839f9d5a5b5e9497d` (v0.3.0). Baseline: branch
`main`, clean working tree, no user changes. All 17 audit findings below are
accepted; the conditional USG-06 finding is accepted as a reconciliation/diagnostic
task, not as proof that every real log loses tokens.

The external audit is not required to continue: evidence, decisions, acceptance,
dependencies and verification are recorded here. Do not expand this work to
unrelated roadmap items, change model routing, add paid live benchmarks, rewrite
historical releases, or weaken permission defaults.

The audit's unnumbered future options are not accepted implementation work:
there is no measured scan-latency problem to justify an index/cache, the four
bundles need an equality test rather than a DSL, and automatic model/release
updates lack a chosen compatibility policy. A paid benchmark platform has no
established need and requires separate cost authority. Crash recovery after
SIGKILL/power loss and protection against a hostile racing process need a
separately defined guarantee; the transaction here handles normal failures and
observed concurrent edits. Extra ROADMAP/ARCHITECTURE files would duplicate this
plan and the development guide. These decisions use the audit's evidence, not
the low priority or former deferred label.

**Goal:** Complete all applicable findings INS-01/02, USG-01 through USG-08,
QA-01/02, AGT-01/02, PLAN-01, DOC-01 and MAINT-01 in
`/home/snaplyze/codex-orchestrator`, using this file as the authoritative plan
and finding registry. Continue through every queue; a documentation phase, a
passing subset or an empty short Todo is not completion. Preserve user changes,
use isolated fixtures, keep implementation/docs/tests consistent, and finish only
after all acceptance criteria pass or a finding is proved inapplicable. Record
unavailable external verification as incomplete, never as passed. Do not publish,
deploy, incur model charges or perform irreversible actions without applicable
authorization. Continue this same goal after compaction, reading AGENTS.md and
this execution record first.

Goal mechanism: native `create_goal/get_goal/update_goal` is available; initial
`get_goal` returned no active goal. Activation must follow the documentation gate.
Goal ID/status: **active**, thread ID
`01a0dd09-2476-74b0-a945-b7ce6b954541` (the native tool returns a thread ID,
not a separate goal ID). Activation confirmed by create_goal after D0.

## Architecture and validation boundaries

Ready-to-copy `profiles/*` are the distribution source. Their TOML files own model,
effort and permission settings; their identical skills own shared routing policy.
At baseline, root AGENTS.md served both source maintainers and installed projects.
The baseline installers validated a selected bundle, confirmed updates, backed up
components, copied files, migrated the old skill and updated a managed block.
Current transaction behavior is documented in the README and migration guide.
The Python stdlib CLI groups Codex rollout JSONL and renders usage. It is not a
billing system. Tests use unittest; baseline CI ran Python 3.12 on Ubuntu and
Windows, preferring pwsh on Windows. Native Codex/account access is separate
from static TOML validity.

Sources used by the audit:
[Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents),
[skill discovery](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills),
[protocol rust-v0.157.1](https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/protocol/src/protocol.rs),
[GitHub Node 24 migration](https://github.blog/changelog/2026-09-23-node-20-is-no-longer-available-in-github-actions/).
Recheck version-sensitive decisions against primary sources. Do not infer paid
account access or live-model quality from these sources.

Baseline audit evidence: 34 unittest tests passed (23 installers, 3 profiles,
8 usage); shell syntax and ShellCheck passed; published CI run 36233983873
passed both jobs. These results describe the baseline, not future edits.

## Finding registry

Status vocabulary: planned, in progress, implemented / verification pending,
verified, externally blocked, proved inapplicable. Every item starts **planned**.

### INS-01 — hardlinks escape target write boundaries (P2; defect)

- Evidence: shell copy and PowerShell Copy-Item overwrite existing inodes.
  A config hardlinked to an external sentinel changes that sentinel; cancellation
  restores only the target. Reproduced in both engines on Linux.
- Decision: stage replacement files and replace directory entries; protect
  AGENTS writes too. Preserve required file metadata; reject incompatible paths.
  Do not add a runtime dependency merely to detect hardlinks.
- Components/docs: setup.sh, setup.ps1, tests/test_installers.py, README.md,
  guides/migration.md, guides/development.md.
- Dependencies: shared transaction design with INS-02.
- Acceptance/check: external hardlinked config and AGENTS stay byte-identical on
  success and rollback; normal install/update/migration pass on each supported
  engine; targeted hardlink regression tests plus full installer suite.

### INS-02 — component rollback erases concurrent user work (P2; defect)

- Evidence: approve .codex, wait at the next prompt, edit an unrelated user file
  and create another, then EOF. Both installers restore the old file and delete
  the new one because rollback removes the whole component.
- Decision: journal only touched paths, with before/installed states. Restore
  only unchanged installer-owned output; retain/report conflicting user changes
  and recovery data. Never recursively delete an existing component to roll back.
  Account for legacy skill moves and newly created directories.
- Components/docs: same as INS-01.
- Dependencies: common safe-write helper from INS-01.
- Acceptance/check: unrelated concurrent edits/new files survive; modified
  managed files produce a recovery warning and preserved backup; failed restores
  retain usable data; equivalent deterministic cancellation/failure tests for
  shell and PowerShell. An installer lock alone cannot satisfy this criterion.

### USG-01 — independent limit events are skipped (P2; defect)

- Evidence: token_count info=null makes the parser continue before rate_limits;
  snapshots 10%,20%,30% render 20%→20%. Official info and rate_limits are optional
  independently.
- Decision: parse limits independently from usage.
- Components/docs: scripts/token_usage.py, tests/test_token_usage.py,
  guides/token-usage.md. Dependencies: none.
- Acceptance/check: rate-only first/last events render 10%→30%; usage stays 100;
  regression fixture exercises the public report path.

### USG-02 — date-limited reports look complete (P2; contract mismatch)

- Evidence: root day 25=100 tokens, child day 26=200; --date day25 reports 100,
  without date 300. Help says date limits files, guide promises full session cost.
- Decision: preserve the date filter semantics; expose scan scope and incomplete
  coverage explicitly in Markdown/JSON and docs. Full-session examples omit date.
- Components/docs: usage CLI/tests, README.md, guides/token-usage.md.
- Dependencies: shared diagnostics/metadata with USG-03.
- Acceptance/check: filtered output is unmistakably partial; unfiltered fixture
  totals 300; JSON records scope and limitations. Do not imply an unfiltered
  directory proves all possible logs exist.

### USG-03 — malformed boundary data crashes reporting (P2; defect)

- Evidence: naive/aware timestamps, id=null with valid session_id, primary=42,
  infinite counters and bad UTF-8 each cause uncaught exceptions.
- Decision: validate identities/nested counters/windows, normalize timestamps,
  isolate read/decoding failures; surface warnings and partial status instead of
  silently converting corrupt data to authoritative zero.
- Components/docs: usage CLI/tests and token guide. Dependencies: none.
- Acceptance/check: all five corrupt cases avoid traceback; valid data remains
  reportable or a clear nonzero error is returned; diagnostics distinguish partial
  results. Include unavailable/disappearing input in the same boundary policy.

### USG-04 — legacy root identity is inconsistent (P3; defect)

- Evidence: collect uses session_id or id, thread_role requires both equal;
  legacy root becomes unknown and loses cwd/version/quota summary.
- Decision: share root fallback, retaining explicit subagent identity precedence.
- Components/docs: usage CLI/tests, token guide. Depends: USG-03 metadata policy.
- Acceptance/check: missing-session_id root receives root summary; child/guardian
  roles remain correct. Official legacy deserializer uses id as fallback.

### USG-05 — accepted dates are not canonicalized (P3; defect)

- Evidence: strptime accepts 2026-9-25, filesystem scan uses 2026/9/25 rather than
  existing 2026/09/25.
- Decision: return canonical ISO date from validation.
- Components/docs: usage CLI/tests, token guide. Dependencies: none.
- Acceptance/check: padded/unpadded dates select identical files; invalid
  calendar dates remain argparse errors.

### USG-06 — mixed counters can disagree silently (P2; conditional risk)

- Evidence: cumulative 100, delta 200, cumulative 300 yields response total 200.
  Real resume/upgrade prevalence was not established.
- Decision: retain per-response totals and cumulative evidence separately; expose
  mismatch/coverage status without guessing model attribution or adding both.
  Check official writer semantics before claiming any stronger reconciliation.
- Components/docs: usage CLI/tests, token guide. Depends: USG-03, USG-08.
- Acceptance/check: mixed fixture emits explicit mismatch; legacy-only and
  response-only values stay correct; no automatic double-counting; JSON preserves
  evidence needed to interpret the diagnostic.

### USG-07 — quota windows/reset labels are inaccurate (P3; defect)

- Evidence: window_minutes=60/1440 still prints 5h/7d; resets_at change is omitted.
  Official snapshot provides duration/reset/limit identity.
- Decision: show actual durations or unknown; warn when resets/limit identity
  make snapshots incomparable. Do not turn arrows into asserted task cost.
- Components/docs: usage CLI/tests, README.md, token guide.
- Dependencies: USG-01/03.
- Acceptance/check: 60/1440 correctly labeled; reset and limit-id change warned;
  missing durations not guessed; normal 5h/7d snapshots remain readable.

### USG-08 — revert segments inflate thread counts (P3; defect)

- Evidence: official revert retains stable thread id in a new rollout; fixture
  root+child+replacement-child reports 3 threads/2 children, actually 2/1.
- Decision: count unique stable IDs and make multiple segments explicit; preserve
  all distinct response costs. Duplicate cost from inherited records was NOT
  established; writer filters inherited TokenUsageRecord at spawn.
- Components/docs: usage CLI/tests and token guide. Depends: USG-03 identity.
- Acceptance/check: fixture reports 2 threads/1 child and preserves 3 records,
  600 tokens; Markdown/JSON/list consistently distinguish thread and segment.

### QA-01 — platform/runtime verification gaps (P2; risk)

- Evidence: README supports macOS/Linux and Windows PowerShell; CI only
  Ubuntu/Windows, automatically preferring pwsh; three failure tests POSIX-only.
- Decision: explicit installer engine selection in test harness; matrix Linux sh,
  macOS sh, Windows pwsh and Windows PowerShell; portable rollback regression
  coverage. Document native Codex discovery smoke independently of paid calls.
- Components/docs: tests/test_installers.py, .github/workflows/ci.yml,
  guides/development.md, README.md, model-selection guide.
- Dependencies: INS-01/02 for final native acceptance; QA-02 action compatibility.
- Acceptance/check: full suite on every promised native engine, meaningful failure
  coverage on both installers, explicit evidence for loaded roles or documented
  manual smoke procedure. Unavailable native runners remain pending, not passed.

### QA-02 — forced Node runtime for old Actions (P3; risk)

- Evidence: checkout@v4/setup-python@v5 target Node20; successful audit CI warns
  both are forced onto Node24. This is NOT a broken-build finding.
- Decision: select reviewed supported Node24 action releases from first-party
  sources; retain Python3.12 and contents:read; pin reviewed immutable revisions
  if practical. No extra permissions.
- Components/docs: workflow, development guide. Dependencies: none.
- Acceptance/check: action metadata declares Node24; workflow validates and new
  native jobs succeed without forced-runtime warning.

### AGT-01 — source checkout lacks discoverable required skill (P3; mismatch)

- Evidence: AGENTS requires codex-orchestrator, only profiles/*/agents/skills holds
  it; standard discovery does not scan templates; self-install is forbidden.
- Decision: explicit maintainer fallback path and local plan/testing instructions
  outside the distributed managed block. Fresh installation must copy only that
  managed block, like updates, to avoid leaking maintainer rules into clients.
- Components/docs: AGENTS.md, installer/tests, README.md, development guide.
- Dependencies: safe installer write changes.
- Acceptance/check: clean checkout instruction resolves without global skill;
  new target contains managed client guidance but no maintainer plan/rules;
  existing unmanaged text and managed updates remain idempotent.

### AGT-02 — carry authority explicitly in briefs (P3; improvement)

- Evidence: existing brief specifies files/constraints but not task mode or
  external action permissions; read-only research text only bans application edits.
- Decision: add mode, permitted write surface/external effects and inherited
  authorization to brief/role instructions. No new permissions and no repeated
  approval for already authorized work.
- Components/docs: all four skill copies, role developer_instructions, AGENTS.md.
- Dependencies: none; role TOML changes follow documentation gate.
- Acceptance/check: audit-only, authorized commit and unauthorized publish
  examples route correctly; role settings unchanged; scope/permission checks.

### PLAN-01 — benchmark lacks outcome/initial-state controls (P3; improvement)

- Evidence: protocol/table record tokens/time/quota but no success criteria or
  reset to identical source state.
- Decision: define acceptance before runs, exact source revision, isolated trial
  checkout, cache/session assumptions, pass/partial/fail and successful-run cost.
- Components/docs: guides/token-usage.md. Depends: trustworthy metrics for live use.
- Acceptance/check: protocol can reproduce one trial; failed work cannot count as
  a cheaper success. No live paid benchmark is part of this remediation.

### DOC-01 — cache proportion does not establish monetary savings (P3; improvement)

- Evidence: 96% cached input is used to assert >10x cost overstatement without
  price weights; allowance/token mapping is acknowledged unknown elsewhere.
- Decision: state measured cache fraction, not a derived billing multiplier;
  monetary estimates require model/tier/date/rates/formula, not plan inference.
- Components/docs: token guide. Dependencies: none.
- Acceptance/check: no unsupported factor remains; historical sample retained.

### MAINT-01 — shared policy identity is not enforced (P3; improvement)

- Evidence: four identical skills; tests check names, models and concurrency but
  not identical skill bodies.
- Decision: add a small equality invariant, no generator/dependency.
- Components/docs: tests/test_profiles.py, development guide.
- Dependencies: AGT-02 skill edits.
- Acceptance/check: intentional model/concurrency differences pass; one-profile
  accidental skill divergence fails the invariant.

## Ordered Todo and ownership

- [x] D0 Documentation gate: registry, current limitations, development/agent rules,
  benchmark correction, linked entrypoint; docs-only diff reviewed.
- [x] G0 Activate the native goal; save returned status/identifier here.
- [x] I1 Implement INS-01/02 and installer half of AGT-01 with regression tests.
- [x] U1 Implement USG-01..08 with explicit scope, diagnostics and segment semantics.
- [ ] Q1 Implement QA-01/02 and MAINT-01; verify supported runtime documentation.
- [x] A1 Complete AGT-01/02, test client/source instruction separation.
- [x] D1 Synchronize final README/guides with actual behavior and PLAN-01/DOC-01.
- [ ] V1 Independent review, focused regressions, full checks and docs gate.
- [ ] R1 Reconcile every ID; obtain required external runner evidence if missing;
  only then mark applicable items and goal complete.

I1 and U1 may run concurrently with disjoint file ownership after G0.
Root owns planning/docs/CI/integration. Installer worker owns both installers and
installer tests. Usage worker owns analyzer and its tests. Shared acceptance
changes require root coordination. No worker may publish or edit global settings.

## Verification commands and review focus

Local: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v`,
`sh -n setup.sh`, `shellcheck setup.sh`. PowerShell: parse setup.ps1 with its
Language.Parser, then run tests through explicit engine selection.
CI: Python3.12 on supported native platforms. Docs: relative link/anchor check
and commands/examples against current code. No Mermaid changes are required.

Review focus: hardlinks in config/AGENTS; unrelated and managed concurrent writes;
rollback failure/recovery retention; legacy skill archive conflicts; malformed
usage values and disappearing files; cross-day scope; repeated stable thread IDs;
unsupported assumptions about live model access and native platform success.

## Execution checkpoint

### Current per-finding status

| IDs | Status | Evidence / next check |
|---|---|---|
| INS-01/02 | implemented / native verification pending | full sh suite and independent link/hardlink probes pass; portable PowerShell and native CI follow |
| USG-01..08 | verified | 21 usage tests pass; independent review plus final malformed-type regression; integrated suite still pending |
| QA-01 | in progress | four native matrix entries configured; harness and native execution pending |
| QA-02 | implemented / verification pending | checkout v7.0.1 + setup-python v7.0.0 commit pins verified against official action.yml: node24; native run pending |
| AGT-01 | verified | source fallback documented; managed-only new install, CRLF/idempotence and stale prompt regression pass |
| AGT-02 | verified | independent read-only reviewer resolved audit-only/authorized-commit/local-fix scenarios correctly; all role settings unchanged; profile tests pass |
| PLAN-01, DOC-01 | verified | benchmark acceptance/source-state/cache controls and corrected cost claim reviewed against implementation and audit |
| MAINT-01 | verified | 4 profile tests pass; isolated one-profile mutation yields exactly 1 expected assertion failure |

- Current stage: native goal active; U1 implemented and verified locally.
  Installer review corrections finished; integrated sh and portable PowerShell
  suites passed. Native CI follows the complete local check.
- Baseline confirmed unchanged from audit: main at 2eb8173, clean tree.
- Implementation branch: `fix/audit-remediation`, created from that baseline;
  no pre-existing user changes or other branches were modified.
- Scope: all 17 findings accepted as above; no unrelated deferred roadmap included.
- Documentation fact/plan separation: limitations describe baseline; this registry
  specifies intended changes, not completed guarantees.
- Documentation updated: README, AGENTS, migration/token guides, this plan and
  development guide. All 17 IDs have evidence, decisions, dependencies, acceptance
  and checks. PLAN-01/DOC-01 text is implemented; final consistency check pending.
- At the completed documentation gate only Markdown had changed; link checker
  passed 28 links in 12 files. Implementation started only after goal activation.
- Ownership: installer worker owns setup.sh/setup.ps1/tests/test_installers.py;
  usage worker owns scripts/token_usage.py/tests/test_token_usage.py. Root owns
  CI, profile tests, docs, agent instructions and integration.
- Next operation: commit installer/docs group, push the reviewed branch and
  inspect all four native CI jobs.
- Root check after instruction/profile changes: Python3.13 unittest
  tests.test_profiles — 4 passed. Mutation check in a temporary profile copy
  detects a one-profile policy change. Existing model/effort/sandbox assertions pass.
- Workflow sources: official checkout v7.0.1 commit
  3d3c42e5aac5ba805825da76410c181273ba90b1 and setup-python v7.0.0 commit
  5fda3b95a4ea91299a34e894583c3862153e4b97; both declare node24. Python3.12 and
  contents:read retained; checkout credential persistence disabled.
- Independent rules/CI review: no material findings; three authority scenarios
  evaluated at instruction level, not as live model benchmarks. Transitional
  baseline caveats in README/migration/token docs must be replaced after workers'
  implementations pass. No model settings or sandbox permissions were changed.
- Workflow validation: actionlint 1.7.12 passed after replacing unsupported
  matrix expressions in step shell with explicit pwsh/powershell parser steps.
  YAML parsing confirms all four OS/engine entries and contents:read.
- Latest docs link check: 28 links in 16 Markdown files, 0 broken. Advisory prose
  lint flags existing/technical semicolons and long sentences; no blocking docs
  gate is configured. No diagrams were added or changed.
- Installer design accepted: per-path before/installed images, safe entry
  replacement, conflict-aware rollback, empty-only created-directory removal and
  separately journaled legacy move. No whole-component restore fallback.
- Usage independent review found acceptance gaps during implementation: malformed
  IDs in --list, malformed accounting payloads silently skipped, non-CLI legacy
  root classification, oversized date overflow, and component-only cumulative
  mismatches. Parent additionally flagged top-level limit_id handling, dropped
  list diagnostics and non-finite metadata export. These remain in USG-03/04/05/06/07,
  with focused regressions assigned to the usage owner; no extra roadmap scope.
- Usage docs now describe the implemented output contract: explicit scan scope,
  per-segment rows, unique thread counts, diagnostics and cumulative evidence.
  Final usage tests/review subsequently passed, as recorded below.
- Installer review is exercising managed deletions, permission edits, symlink/
  reparse substitutions and created-directory rollback. A Windows-only .NET
  compatibility issue was identified before native CI: GetUnixFileMode exists
  on modern runtimes but is unsupported on Windows, so OS gating is required
  ([Microsoft API](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.getunixfilemode)).
  All corrections remain within INS-01/02 and QA-01 acceptance.
- AGENTS prompt-race regression added to installer scope: outside-block user
  text can change while confirmation waits. Re-read/revalidate or abort on that
  change, preserving user bytes; do not write a stale pre-confirmation snapshot.
- Additional local instruction validation: installed PyYAML parsed all 4 skill
  frontmatters; tomllib parsed all 20 role files and their required text fields.
  The optional plugin linter's missing frontmatter package was not added as a
  project dependency; structural checks and independent semantic review are
  recorded separately from that unavailable tool.
- Usage final check: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  tests.test_token_usage -v` — 21 passed. Independent review found one final
  unvalidated record-type crash; the parent added list/dict type fixtures,
  observed the failure, validated type before dispatch and reran all 21 tests.
  This result applies to the uncommitted implementation on fix/audit-remediation.
  No private rollout logs or paid model calls were used.
- Root quota reporting intentionally identifies one rollout segment rather than
  inventing chronology across reverts; JSON retains each segment's snapshots.
- Installer independent review found legacy-move rollback and empty-directory
  cleanup still followed a swapped ancestor link. Both engines are being guarded
  at those remaining mutation points. Three old failure-injection tests must be
  adapted to the new staging path; failures are not counted as passes.
- Final rules/docs review found one exit-status wording mismatch: zero --root
  matches returns 2, not 1. The guide now matches that behavior. The reviewer
  found no other material issue in its scope; model/effort/sandbox settings stay
  unchanged. Root checked CLI --help and all 29 then-existing local links.
- README and migration now describe per-file staging, conflict preservation,
  retained before/after copies and recovery limits. Installer native acceptance
  remains pending. The review requires actual write/restore fault injection in
  addition to cancellation tests; replacing those tests with EOF alone is not
  accepted. Root requested restoration of that coverage before integration.
- Publishing authority: the user's earlier explicit instruction to push after
  review is used only after reviewed local checks, for fix/audit-remediation and
  its native CI. No new release, tag deletion, production change or paid model
  benchmark is included. The earlier audit-only phase has ended with the user's
  explicit remediation request.
- Reviewed local commits: `5176f4c` implements usage reporting/tests/guide;
  `5d2c37a` implements delegation authority, policy invariant and native CI matrix.
  Installer and final integration docs remain uncommitted until their checks pass.
  No branch has been pushed during this remediation checkpoint.
- Root integrated sh verification: `TMPDIR=/home/snaplyze/.cache/codex-orchestrator-audit-tools/test-tmp
  CODEX_INSTALLER_TEST_ENGINE=sh PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  discover -v` — **56 passed** (31 installer, 4 profile, 21 usage). This is
  HEAD 5d2c37a plus the reviewed uncommitted installer/docs changes. Temporary
  helpers use an executable filesystem because this host's /tmp is noexec.
- `sh -n setup.sh`, `shellcheck setup.sh`, PowerShell 7.6.6 Language.Parser and
  `git diff --check` passed. Final relative Markdown check: 30 links across
  17 files, zero broken paths/anchors. Actionlint 1.7.12 already passed the
  unchanged workflow. No new project dependencies were added.
- Independent installer review now reports no remaining implementation defect:
  both engines pass legacy rollback/empty-directory link substitution, .codex
  ancestor substitution and target-root substitution probes. Config hardlink
  rollback preserves the external file and 0600 mode. The actual write/restore
  fault tests include injection markers and retained before-image assertions.
- Recovery entries now use `manifest.txt` in both installers: normalized relative
  path on line one, `existing` or `new` on line two. Manifest and before/after
  copies remain available after restoration conflicts/failures.
- Root portable PowerShell verification: the same executable TMPDIR with
  `CODEX_INSTALLER_TEST_ENGINE=pwsh`,
  `CODEX_INSTALLER_TEST_EXECUTABLE=/home/snaplyze/.cache/codex-orchestrator-pwsh-7.6.6/pwsh`
  and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_installers -v`
  — **31 passed** in a single full run. This does not substitute for native
  Windows tests. Independent installer reviewer has no unresolved finding.
