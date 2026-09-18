#!/bin/sh

set -eu

script_dir=$(CDPATH=; cd -- "$(dirname -- "$0")" && pwd -P)

managed_begin='<!-- BEGIN codex-astra-luna-orchestrator:managed -->'
managed_end='<!-- END codex-astra-luna-orchestrator:managed -->'
transaction_root=
managed_block_path=
changed_components=
transaction_committed=no
transaction_preserved=no

cat <<'BANNER'
+---------------------------------------+
|    _    ____ _____ ____      _        |
|   / \  / ___|_   _|  _ \    / \       |
|  / _ \ \___ \ | | | |_) |  / _ \      |
| / ___ \ ___) || | |  _ <  / ___ \     |
|/_/   \_\____/ |_| |_| \_\/_/   \_\    |
|                                       |
|       O R C H E S T R A T O R         |
|   Plan and orchestrate with Astra.    |
|          Execute with Luna.           |
+---------------------------------------+
BANNER
printf '%s\n' 'Interactive project setup'
printf '%s' 'Target repository path: '
IFS= read -r target_path || exit 1

if [ -z "$target_path" ] || [ ! -d "$target_path" ]; then
    printf 'Error: target must be an existing directory: %s\n' "${target_path:-<empty>}" >&2
    exit 1
fi

target_dir=$(CDPATH=; cd -- "$target_path" && pwd -P)
if [ "$target_dir" = "$script_dir" ]; then
    printf 'Error: target repository must be different from the setup source directory.\n' >&2
    exit 1
fi

rollback() {
    if [ -z "${transaction_root:-}" ] || [ "${transaction_committed:-no}" = yes ]; then
        return 0
    fi

    if [ -z "${changed_components:-}" ]; then
        return 0
    fi

    printf '%s\n' 'Setup failed; restoring the target to its previous state.' >&2
    rollback_failed=no
    while IFS='|' read -r component state; do
        [ -n "$component" ] || continue
        destination_path=$target_dir/$component
        if [ "$state" = existing ]; then
            if ! rm -rf "$destination_path"; then
                printf 'Warning: could not remove the failed component before restoring %s.\n' "$component" >&2
                rollback_failed=yes
                continue
            fi
            if ! cp -R "$transaction_root/backup-$component" "$destination_path"; then
                printf 'Warning: could not restore %s from backup.\n' "$component" >&2
                rollback_failed=yes
            fi
        else
            if ! rm -rf "$destination_path"; then
                printf 'Warning: could not remove the failed new component: %s.\n' "$component" >&2
                rollback_failed=yes
            fi
        fi
    done <<EOF_CHANGES
$changed_components
EOF_CHANGES
    if [ "$rollback_failed" = yes ]; then
        transaction_preserved=yes
        printf 'Warning: rollback was incomplete; transaction backups were retained at %s\n' "$transaction_root" >&2
    fi
}

cleanup_transaction() {
    if [ -n "${transaction_root:-}" ]; then
        if [ "${transaction_preserved:-no}" = yes ]; then
            printf 'Transaction backups remain at %s\n' "$transaction_root" >&2
            return 0
        fi
        if ! rm -rf "$transaction_root"; then
            transaction_preserved=yes
            printf 'Warning: could not remove transaction backups; retained at %s\n' "$transaction_root" >&2
            return 0
        fi
    fi
    transaction_root=
    managed_block_path=
    changed_components=
    transaction_preserved=no
}

on_exit() {
    exit_status=$?
    if [ "$exit_status" -ne 0 ]; then
        rollback || true
    fi
    cleanup_transaction || true
    trap - EXIT
    exit "$exit_status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

begin_transaction() {
    transaction_root=$(mktemp -d "${TMPDIR:-/tmp}/codex-orchestrator-install.XXXXXXXX") || {
        printf '%s\n' 'Error: could not create a transaction directory.' >&2
        exit 1
    }
    managed_block_path=$transaction_root/managed-block
    source_agents_normalized=$transaction_root/source-agents-normalized
    if ! sed 's/\r$//' "$script_dir/AGENTS.md" > "$source_agents_normalized"; then
        printf '%s\n' 'Error: could not read setup source AGENTS.md.' >&2
        exit 1
    fi
    if ! extract_managed_block "$source_agents_normalized" "$managed_block_path"; then
        printf '%s\n' 'Error: setup source AGENTS.md has an invalid managed block.' >&2
        exit 1
    fi
}

backup_component() {
    component=$1
    destination_path=$target_dir/$component

    if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
        if [ -L "$destination_path" ]; then
            printf 'Error: refusing to back up symbolic link component: %s\n' "$component" >&2
            return 1
        fi
        if ! cp -R "$destination_path" "$transaction_root/backup-$component"; then
            printf 'Error: could not back up existing component: %s\n' "$component" >&2
            return 1
        fi
        changed_components="$component|existing
$changed_components"
    else
        changed_components="$component|new
$changed_components"
    fi
}

validate_profile() {
    profile_path=$script_dir/profiles/$plan
    for relative_path in \
        codex/config.toml \
        codex/agents/explorer.toml \
        codex/agents/researcher.toml \
        codex/agents/reviewer.toml \
        codex/agents/tester.toml \
        codex/agents/worker.toml \
        agents/skills/astra-orchestrator/SKILL.md; do
        if [ ! -f "$profile_path/$relative_path" ] || [ -L "$profile_path/$relative_path" ]; then
            printf 'Error: selected profile is incomplete: %s\n' "$profile_path/$relative_path" >&2
            return 1
        fi
    done

    role_count=$(find "$profile_path/codex/agents" -type f -name '*.toml' -print | wc -l | tr -d ' ')
    if [ "$role_count" -ne 5 ]; then
        printf 'Error: selected profile must contain exactly five role files: %s\n' "$profile_path/codex/agents" >&2
        return 1
    fi
}

confirm() {
    prompt=$1
    default_yes=$2
    if [ "$default_yes" = yes ]; then
        suffix='[Y/n]'
    else
        suffix='[y/N]'
    fi

    while :; do
        printf '%s %s ' "$prompt" "$suffix"
        if ! IFS= read -r answer; then
            printf '\nSetup cancelled: input ended before setup was complete.\n' >&2
            exit 1
        fi

        case "$answer" in
            y|Y|yes|YES|Yes) return 0 ;;
            n|N|no|NO|No) return 1 ;;
            '') [ "$default_yes" = yes ] && return 0 || return 1 ;;
            *) printf '%s\n' 'Please answer yes or no.' ;;
        esac
    done
}

overwrite_paths() {
    source_path=$1
    destination_path=$2
    component_name=$(basename "$source_path")

    if [ -f "$source_path" ]; then
        if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
            printf '%s\n' "$component_name"
        else
            return
        fi
        return
    fi

    find "$source_path" -type f -print | while IFS= read -r source_file; do
        relative_path=${source_file#"$source_path"/}
        destination_file=$destination_path/$relative_path
        if [ -e "$destination_file" ] || [ -L "$destination_file" ]; then
            printf '%s\n' "$component_name/$relative_path"
        fi
    done
}

print_overwrites() {
    source_path=$1
    destination_path=$2

    overwrite_list=$(overwrite_paths "$source_path" "$destination_path")
    if [ -z "$overwrite_list" ]; then
        return
    fi

    printf '%s\n' 'WARNING: the following existing files will be overwritten:'
    printf '%s\n' "$overwrite_list" | sed 's/^/  - /'
}

merge_conflicts() {
    source_path=$1
    destination_path=$2

    find "$source_path" -type f -print | while IFS= read -r source_file; do
        relative_path=${source_file#"$source_path"/}
        destination_file=$destination_path/$relative_path
        if { [ -e "$destination_file" ] || [ -L "$destination_file" ]; } && [ ! -f "$destination_file" ]; then
            printf '%s\n' "$relative_path"
        fi
    done

    find "$source_path" -type d -print | while IFS= read -r source_directory; do
        if [ "$source_directory" = "$source_path" ]; then
            continue
        fi
        relative_path=${source_directory#"$source_path"/}
        destination_directory=$destination_path/$relative_path
        if { [ -e "$destination_directory" ] || [ -L "$destination_directory" ]; } && [ ! -d "$destination_directory" ]; then
            printf '%s\n' "$relative_path"
        fi
    done
}

select_plan() {
    printf '%s\n' 'Codex plan:'
    printf '%s\n' '  1) Pro  - GPT-6 Astra orchestrates, GPT-5.6 Luna executes, GPT-6 Astra reviews'
    printf '%s\n' '  2) Plus - GPT-5.6 Luna (max reasoning) orchestrates, GPT-5.6 Luna executes, GPT-6 Astra reviews'
    printf '%s\n' '  3) Pro (max 2 subagents)  - Pro profile with two concurrent subagent threads'
    printf '%s\n' '  4) Plus (max 2 subagents) - Plus profile with two concurrent subagent threads'

    while :; do
        printf '%s' 'Select plan [1-4] (default 1): '
        if ! IFS= read -r answer; then
            printf '\nSetup cancelled: input ended before setup was complete.\n' >&2
            exit 1
        fi

        case "$answer" in
            1|pro|PRO|Pro|'') plan=pro; return ;;
            2|plus|PLUS|Plus) plan=plus; return ;;
            3|pro-max-2-subagents|PRO-MAX-2-SUBAGENTS) plan=pro-max-2-subagents; return ;;
            4|plus-max-2-subagents|PLUS-MAX-2-SUBAGENTS) plan=plus-max-2-subagents; return ;;
            *) printf '%s\n' 'Please answer 1 (Pro), 2 (Plus), 3 (Pro max 2), or 4 (Plus max 2).' ;;
        esac
    done
}

extract_managed_block() {
    source_path=$1
    output_path=$2

    awk -v begin="$managed_begin" -v end="$managed_end" '
        BEGIN { begin_count = 0; end_count = 0; inside = 0 }
        $0 == begin {
            begin_count++
            if (begin_count == 1) inside = 1
        }
        inside { print }
        $0 == end {
            end_count++
            inside = 0
        }
        END {
            if (begin_count != 1 || end_count != 1 || inside != 0) exit 1
        }
    ' "$source_path" > "$output_path"
}

replace_managed_block() {
    normalized_path=$1
    destination_path=$2
    replacement_path=$3
    replacement_output=$transaction_root/agents-updated

    if ! awk -v begin="$managed_begin" -v end="$managed_end" -v replacement="$replacement_path" '
        BEGIN { replaced = 0; inside = 0 }
        $0 == begin {
            while ((getline line < replacement) > 0) print line
            close(replacement)
            replaced = 1
            inside = 1
            next
        }
        $0 == end && inside {
            inside = 0
            next
        }
        !inside { print }
        END {
            if (!replaced || inside) exit 1
        }
    ' "$normalized_path" > "$replacement_output"; then
        printf 'Error: could not replace the managed block in %s.\n' "$destination_path" >&2
        return 1
    fi

    if ! cp "$replacement_output" "$destination_path"; then
        printf 'Error: could not write the managed block to %s.\n' "$destination_path" >&2
        return 1
    fi
}

install_managed_agents() {
    destination_path=$1
    normalized_path=$transaction_root/agents-normalized
    current_block_path=$transaction_root/current-managed-block

    if ! sed 's/\r$//' "$destination_path" > "$normalized_path"; then
        printf 'Error: could not read existing AGENTS.md.\n' >&2
        return 1
    fi

    if awk -v begin="$managed_begin" -v end="$managed_end" \
        '$0 == begin || $0 == end { found = 1 } END { exit !found }' "$normalized_path"; then
        if ! extract_managed_block "$normalized_path" "$current_block_path"; then
            printf '%s\n' 'Error: existing AGENTS.md has a malformed managed block.' >&2
            return 1
        fi
        if cmp -s "$current_block_path" "$managed_block_path"; then
            printf '%s\n' 'Skipped AGENTS.md: managed instructions are already up to date.'
            component_satisfied=yes
            return 0
        fi

        printf '%s\n' 'WARNING: AGENTS.md contains an older managed instruction block.'
        if ! confirm 'Update the managed instructions in AGENTS.md?' no; then
            printf '%s\n' 'Skipped AGENTS.md (existing managed instructions left unchanged).'
            return 0
        fi
        if ! backup_component AGENTS.md; then
            return 1
        fi
        if ! replace_managed_block "$normalized_path" "$destination_path" "$managed_block_path"; then
            return 1
        fi
        printf '%s\n' 'Updated the managed instructions in AGENTS.md.'
        component_installed=yes
        component_satisfied=yes
        return 0
    fi

    printf '%s\n' 'WARNING: existing AGENTS.md has no managed instruction block; setup will append one.'
    if ! confirm 'Add the managed instructions to AGENTS.md?' no; then
        printf '%s\n' 'Skipped AGENTS.md (existing contents left unchanged).'
        return 0
    fi
    if ! backup_component AGENTS.md; then
        return 1
    fi
    if [ -s "$destination_path" ]; then
        printf '\n\n' >> "$destination_path"
    fi
    if ! cat "$managed_block_path" >> "$destination_path"; then
        printf 'Error: could not append managed instructions to %s.\n' "$destination_path" >&2
        return 1
    fi
    printf '%s\n' 'Appended managed instructions to AGENTS.md. Existing contents preserved.'
    component_installed=yes
    component_satisfied=yes
}

copy_component() {
    name=$1
    source_path=${2:-$script_dir/$name}
    destination_path=$target_dir/$name
    component_installed=no
    component_satisfied=no

    if [ ! -e "$source_path" ] && [ ! -L "$source_path" ]; then
        printf 'Error: setup source is missing: %s\n' "$source_path" >&2
        return 1
    fi

    if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
        if [ "$name" = AGENTS.md ]; then
            if [ -L "$destination_path" ] || [ ! -f "$destination_path" ]; then
                printf 'Skipped %s: target must be a regular file, not a symbolic link.\n' "$name" >&2
                return 0
            fi
            install_managed_agents "$destination_path"
            return $?
        fi
        if [ -L "$destination_path" ]; then
            printf 'Skipped %s: refusing to replace a symbolic link.\n' "$name" >&2
            return 0
        fi
        if [ ! -L "$destination_path" ] && [ -d "$source_path" ] && [ -d "$destination_path" ]; then
            linked_path=$(find "$destination_path" -type l -print -quit)
            if [ -n "$linked_path" ]; then
                printf 'Skipped %s: the existing target contains a symbolic link (%s).\n' \
                    "$name" "$linked_path" >&2
                return 0
            fi
            conflict_list=$(merge_conflicts "$source_path" "$destination_path")
            if [ -n "$conflict_list" ]; then
                printf 'Skipped %s: source and target types conflict at:\n' "$name" >&2
                printf '%s\n' "$conflict_list" | sed 's/^/  /' >&2
                return 0
            fi
        elif [ ! -L "$destination_path" ] && {
            { [ -d "$source_path" ] && [ ! -d "$destination_path" ]; } ||
            { [ -f "$source_path" ] && [ ! -f "$destination_path" ]; };
        }; then
            printf 'Skipped %s: source and target types are incompatible.\n' "$name" >&2
            return 0
        fi

        print_overwrites "$source_path" "$destination_path"
        if ! confirm "Update $name? New files will be added; only paths listed above will be replaced." no; then
            printf 'Skipped %s (existing target left unchanged).\n' "$name"
            return 0
        fi

        if ! backup_component "$name"; then
            return 1
        fi
        if [ -d "$source_path" ] && [ -d "$destination_path" ]; then
            if ! cp -R "$source_path"/. "$destination_path"/; then
                printf 'Error: could not update %s.\n' "$name" >&2
                return 1
            fi
        elif [ -f "$source_path" ] && [ -f "$destination_path" ]; then
            if ! cp "$source_path" "$destination_path"; then
                printf 'Error: could not update %s.\n' "$name" >&2
                return 1
            fi
        else
            printf 'Error: source and target types are incompatible for %s.\n' "$name" >&2
            return 1
        fi
        printf 'Updated %s.\n' "$name"
    else
        if ! backup_component "$name"; then
            return 1
        fi
        if ! cp -R "$source_path" "$destination_path"; then
            printf 'Error: could not install %s.\n' "$name" >&2
            return 1
        fi
        printf 'Installed %s.\n' "$name"
    fi
    component_installed=yes
    component_satisfied=yes
}

plan=pro
select_plan
if ! validate_profile; then
    exit 1
fi
begin_transaction

installed=0
satisfied=0
for component in .codex .agents AGENTS.md; do
    component_installed=no
    component_satisfied=no
    if confirm "Install $component?" yes; then
        if [ "$component" = .codex ]; then
            if ! copy_component "$component" "$script_dir/profiles/$plan/codex"; then
                exit 1
            fi
        elif [ "$component" = .agents ]; then
            if ! copy_component "$component" "$script_dir/profiles/$plan/agents"; then
                exit 1
            fi
        else
            if ! copy_component "$component"; then
                exit 1
            fi
        fi
        if [ "$component_installed" = yes ]; then
            installed=$((installed + 1))
        fi
        if [ "$component_satisfied" = yes ]; then
            satisfied=$((satisfied + 1))
        fi
    else
        printf 'Skipped %s.\n' "$component"
    fi
done

transaction_committed=yes
if [ "$satisfied" -lt 3 ]; then
    printf 'WARNING: partial installation completed (%s of 3 components satisfied).\n' "$satisfied" >&2
fi
printf '\nSetup complete. %s component(s) installed in %s (plan: %s).\n' "$installed" "$target_dir" "$plan"
printf '%s\n' 'See guides/ for optional Codex model and Fast-mode configurations.'
