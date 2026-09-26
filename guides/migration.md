# Migrate to Codex Orchestrator

Version `v0.3.0` renames the repository to
[`snaplyze/codex-orchestrator`](https://github.com/snaplyze/codex-orchestrator)
and the skill to `codex-orchestrator`. The four profiles, model choices, role
names, permissions, and concurrency limits are unchanged.

## Existing clones

Run these commands inside your clone:

```bash
git remote set-url origin https://github.com/snaplyze/codex-orchestrator.git
git pull --ff-only
```

The local checkout folder can keep its current name. To rename it, close tools
using the checkout and rename the folder to `codex-orchestrator` from its parent
directory. Reopen your editor in the renamed folder.

GitHub redirects the previous repository address, but recommends updating local
remotes. Do not create a new repository under the previous name: it replaces
that redirect. See [GitHub's rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

## Project installations

1. Run `./setup.sh` or `pwsh -File ./setup.ps1` from the updated checkout.
2. Select the target project and its profile.
3. Approve updates to `.codex`, `.agents`, and the managed `AGENTS.md` instructions.
4. Review custom instructions for references to `$astra-orchestrator` and change
   them to `$codex-orchestrator`.
5. Start a new Codex session in the target project.

Setup recognizes the previous `codex-astra-luna-orchestrator:managed` markers
and replaces their block with `codex-orchestrator:managed` markers. It preserves
instructions outside that block. Malformed or duplicate blocks stop the update
and trigger rollback.

When you approve the `.agents` update, setup moves the complete legacy
`.agents/skills/astra-orchestrator` directory to
`.agents/migration-backups/astra-orchestrator`. If that backup exists, setup
chooses a numbered suffix. Your previous skill customizations remain in this
backup, outside the directory where skills are discovered. Review and merge any
needed customizations into `.agents/skills/codex-orchestrator/SKILL.md`.

Declining a component leaves it unchanged and can leave the migration incomplete.
If you update `.agents` but decline the instruction update, old skill references
can stop resolving. Rerun setup and approve the remaining updates before starting
a new task.

## Failed updates and recovery

Setup journals each managed file and replaces its directory entry with a staged
file. Existing hardlinks therefore keep their original external contents.
On a normal failure or cancellation, rollback restores a file only while it still
matches the installer's recorded state. Concurrent user edits, deletions and
unrelated new files are preserved. Symbolic links and Windows reparse points are
rechecked before managed writes and rollback operations. Created directories are
removed only when empty; a legacy archive is not moved over an occupied path.

A conflict or failed restoration prints the retained transaction directory.
Keep it until you have reviewed the affected files. Each `entry-N` holds `before`
(when the target existed) and `after` copies; `manifest.txt` identifies the
target's relative path. Compare those
copies with the current target and merge the intended content manually. Do not
restore the whole component over newer work. The warning identifies any retained
legacy archive separately. Recovery copies can contain private configuration;
do not commit or publish them.

These safeguards handle normal failures and detected concurrent changes. They
are not crash recovery after a forced process kill or power loss, nor a guarantee
against a hostile process racing every filesystem operation. Avoid editing
managed paths during setup. Native platform verification and remaining limits
are recorded in the [audit remediation plan](../docs/audit-remediation.md).

## Manual or global installations

The project installer does not change your global configuration. For a global
installation, use the same profile for all copied files:

1. Back up `~/.codex/config.toml`, `~/.codex/agents/`, your installed skill, and
   any global `AGENTS.md` instructions.
2. Move `~/.agents/skills/astra-orchestrator/` to a backup location outside every
   `skills` directory. Keep any customizations for comparison.
3. Copy `profiles/<profile>/agents/skills/codex-orchestrator/` to
   `~/.agents/skills/codex-orchestrator/`.
4. Merge root configuration and copy all five role files from that profile.
   Preserve unrelated providers, plugins, permissions, and other roles.
5. Replace the previous managed instruction block with the block from this
   repository's `AGENTS.md`. Update custom references to the old skill name.
6. Start a new Codex session and invoke `$codex-orchestrator`.

For a manual project installation, use project `.codex/`, `.agents/`, and
`AGENTS.md` instead of their global equivalents. Copying the new skill alone
leaves the old skill discoverable, so retire the previous directory too.

## Releases and old tags

`v0.3.0` starts the release series under the new repository name. The previous
GitHub releases and tags, `v0.1.0` and `v0.2.0`, are retired. Their changes remain
in Git history and the [changelog](../CHANGELOG.md).

Update scripts pinned to those tags to use `v0.3.1` and the new repository URL.
Remove obsolete tags from an existing local clone if they are no longer needed:

```bash
git tag -d v0.1.0 v0.2.0
git fetch origin tag v0.3.1
```

Ordinary fetch/prune operations do not remove those local tags automatically.
