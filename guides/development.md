# Development and verification

This repository distributes ready-to-copy Codex configuration, not a running
service. Profile TOML owns model/effort/permission settings; the identical skills
own shared delegation policy. Installers copy a selected bundle and manage only
their instruction block in the target project's AGENTS.md. Runtime overrides
remain authoritative for an already running Codex session.

The current work queue, evidence and acceptance criteria are in the
[audit remediation plan](../docs/audit-remediation.md). Read its latest checkpoint
before resuming work. Keep implementation claims separate from planned changes.

## Local checks

Use Python 3.12 or newer for the unittest suite (it imports tomllib), a POSIX shell
for setup.sh, and PowerShell for setup.ps1. No Python packages are required.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
sh -n setup.sh
shellcheck setup.sh
```

Tests create temporary targets; never use a real user's project to reproduce a
destructive installer failure. Keep synthetic rollout logs separate from private
Codex sessions. Do not publish logs containing prompts, credentials or private
paths. Use targeted tests while editing, then the full suite before completion.

The workflow is configured for Python 3.12 on Linux/macOS with sh and on Windows
with separate pwsh and powershell jobs. It runs ShellCheck on Linux. The audit
remediation plan records which revision has actually passed this matrix; changing
the YAML does not establish a native-platform pass. A local Linux PowerShell pass
is not native Windows evidence.

Select an installed test engine explicitly with `CODEX_INSTALLER_TEST_ENGINE`
(`sh`, `pwsh` or `powershell`). `CODEX_INSTALLER_TEST_EXECUTABLE` can point to a
portable executable of that engine. A requested unavailable engine must fail
instead of silently skipping its suite.

For example, on a Linux host with portable PowerShell:

```bash
CODEX_INSTALLER_TEST_ENGINE=pwsh \
CODEX_INSTALLER_TEST_EXECUTABLE=/absolute/path/to/pwsh \
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_installers -v
```

Failure-injection fixtures execute temporary helpers. If the system temporary
directory is mounted `noexec`, create a private temporary directory on an
executable filesystem and set `TMPDIR` to it for the tests. Do not disable the
failure tests or change a system mount to obtain a pass.

## Codex integration smoke check

Static tests verify the bundled values; they do not establish account access.
For a supported-client update, record the CLI version, install each profile into
a disposable project, open it as trusted using the normal Codex trust flow, and
inspect the loaded root settings, five named roles and codex-orchestrator skill.
Use the client settings/picker to check advertised models; a paid model call is
not required for discovery. Restart after changing configuration. Record each
unverified platform/account separately; do not change global config for a test.

The model guide records validation against CLI 0.155.1. The audit inspected
0.157.1 protocol sources and local CLI help, without a new live session. This is
not a claim that every client version or account has been tested.

## Change boundaries

Keep all four skills identical while they implement the same policy. Max-2
variants change concurrency only. Do not replace the profile layout with a
generator without a concrete need. Preserve user instructions outside managed
markers and unrelated target files. Treat install rollback, file links and
concurrent user writes as data-integrity boundaries.

Historical changelog entries remain historical. Update user-facing behavior
docs when code lands; record current checks and remaining limits in the plan.
Publishing, production actions and model charges require applicable authority.
