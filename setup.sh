#!/bin/sh

set -eu

script_dir=$(CDPATH=; cd -- "$(dirname -- "$0")" && pwd -P)

managed_begin='<!-- BEGIN codex-orchestrator:managed -->'
managed_end='<!-- END codex-orchestrator:managed -->'
legacy_managed_begin='<!-- BEGIN codex-astra-luna-orchestrator:managed -->'
legacy_managed_end='<!-- END codex-astra-luna-orchestrator:managed -->'
transaction_root=
managed_block_path=
transaction_entry_count=0
transaction_committed=no
transaction_preserved=no
legacy_skill_archived=no
legacy_archive_path=
agents_instructions_canonical=no

cat <<'BANNER'
+----------------------------+
|      CODEX ORCHESTRATOR    |
|  Astra, Luna, Sol profiles |
+----------------------------+
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

    if [ "${transaction_entry_count:-0}" -eq 0 ] && [ -z "${legacy_archive_path:-}" ]; then
        return 0
    fi

    printf '%s\n' 'Setup failed; reverting installer changes and preserving concurrent edits.' >&2
    rollback_failed=no
    entry=$transaction_entry_count
    while [ "$entry" -gt 0 ]; do
        entry_path=$transaction_root/entry-$entry
        IFS= read -r relative_path < "$entry_path/manifest.txt"
        entry_state=$(sed -n '2p' "$entry_path/manifest.txt")
        destination_path=$target_dir/$relative_path
        before_path=$entry_path/before
        after_path=$entry_path/after
        if ! safe_target_entry "$relative_path"; then
            printf 'WARNING: managed path %s became a symbolic link or passed through one; it was preserved with recovery copies in %s.\n' "$relative_path" "$entry_path" >&2
            rollback_failed=yes
            entry=$((entry - 1))
            continue
        fi
        if [ "$entry_state" = existing ] && [ -f "$destination_path" ] && files_match "$destination_path" "$before_path"; then
            entry=$((entry - 1))
            continue
        fi
        if [ "$entry_state" = existing ] && [ -f "$destination_path" ] && files_match "$destination_path" "$after_path"; then
            replacement=$(mktemp "$(dirname "$destination_path")/.codex-orchestrator-rollback.XXXXXXXX") || replacement=
            if [ -z "$replacement" ] || ! cp -p "$before_path" "$replacement" || ! mv -f "$replacement" "$destination_path"; then
                [ -z "$replacement" ] || rm -f "$replacement"
                printf 'Warning: could not restore %s from retained backup.\n' "$relative_path" >&2
                rollback_failed=yes
            fi
        elif [ "$entry_state" = new ] && [ -f "$destination_path" ] && files_match "$destination_path" "$after_path"; then
            if ! rm -f "$destination_path"; then
                printf 'Warning: could not remove failed installer output %s.\n' "$relative_path" >&2
                rollback_failed=yes
            fi
        else
            printf 'WARNING: concurrent change at %s was preserved; recovery copies are in %s.\n' "$relative_path" "$entry_path" >&2
            rollback_failed=yes
        fi
        entry=$((entry - 1))
    done
    if [ -f "$transaction_root/legacy-move" ]; then
        IFS='|' read -r legacy_original legacy_archive < "$transaction_root/legacy-move"
        if ! safe_target_entry "$legacy_archive" || ! safe_target_entry "$legacy_original"; then
            printf 'WARNING: legacy skill rollback path became a symbolic link; archive preserved at %s.\n' "$legacy_archive" >&2
            rollback_failed=yes
        elif [ -e "$target_dir/$legacy_archive" ] && [ ! -e "$target_dir/$legacy_original" ]; then
            if ! mv "$target_dir/$legacy_archive" "$target_dir/$legacy_original"; then
                printf 'Warning: could not restore archived legacy skill; it remains at %s.\n' "$legacy_archive" >&2
                rollback_failed=yes
            fi
        elif [ -e "$target_dir/$legacy_archive" ]; then
            printf 'WARNING: legacy skill rollback destination %s is occupied; archive retained at %s.\n' "$legacy_original" "$legacy_archive" >&2
            rollback_failed=yes
        fi
    fi
    if [ -f "$transaction_root/created-dirs" ]; then
        awk '{ paths[NR] = $0 } END { for (i = NR; i > 0; i--) print paths[i] }' "$transaction_root/created-dirs" > "$transaction_root/created-dirs-reverse"
        while IFS= read -r created_dir; do
            [ -n "$created_dir" ] || continue
            if ! safe_target_entry "$created_dir"; then
                printf 'WARNING: created directory %s now passes through a symbolic link; it was preserved.\n' "$created_dir" >&2
                rollback_failed=yes
            elif ! rmdir "$target_dir/$created_dir" 2>/dev/null; then
                :
            fi
        done < "$transaction_root/created-dirs-reverse"
    fi
    if [ "$rollback_failed" = yes ]; then
        transaction_preserved=yes
        printf 'Warning: rollback was incomplete; transaction backups were retained at %s\n' "$transaction_root" >&2
    fi
}

file_metadata() {
    stat -c '%a:%u:%g' "$1" 2>/dev/null || stat -f '%Lp:%u:%g' "$1" 2>/dev/null || printf '%s' unknown
}

files_match() {
    [ ! -L "$1" ] && [ -f "$1" ] && cmp -s "$1" "$2" && [ "$(file_metadata "$1")" = "$(file_metadata "$2")" ]
}

safe_target_entry() {
    relative_path=$1
    remainder=$relative_path
    current_path=$target_dir
    [ ! -L "$current_path" ] || return 1
    while :; do
        case "$remainder" in
            */*) part=${remainder%%/*}; remainder=${remainder#*/} ;;
            *) part=$remainder; remainder= ;;
        esac
        current_path=$current_path/$part
        [ ! -L "$current_path" ] || return 1
        [ -z "$remainder" ] && return 0
    done
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
    source_namespace=$(classify_managed_block "$source_agents_normalized") || {
        printf '%s\n' 'Error: setup source AGENTS.md has an invalid managed block.' >&2
        exit 1
    }
    if [ "$source_namespace" != canonical ] || \
        ! extract_managed_block "$source_agents_normalized" "$managed_block_path" "$source_namespace"; then
        printf '%s\n' 'Error: setup source AGENTS.md has an invalid managed block.' >&2
        exit 1
    fi
}

ensure_target_directory() {
    relative_directory=$1
    current_path=$target_dir
    remainder=$relative_directory
    while :; do
        case "$remainder" in
            */*) directory_part=${remainder%%/*}; remainder=${remainder#*/} ;;
            *) directory_part=$remainder; remainder= ;;
        esac
        current_path=$current_path/$directory_part
        if [ -L "$current_path" ]; then
            printf 'Error: managed path passes through a symbolic link: %s\n' "$current_path" >&2
            return 1
        fi
        if [ ! -d "$current_path" ]; then
            if [ -e "$current_path" ]; then
                printf 'Error: managed directory path is incompatible: %s\n' "$current_path" >&2
                return 1
            fi
            mkdir "$current_path" || return 1
            printf '%s\n' "${current_path#"$target_dir"/}" >> "$transaction_root/created-dirs"
        fi
        [ -z "$remainder" ] && break
    done
}

install_file() {
    source_file=$1
    relative_path=$2
    destination_file=$target_dir/$relative_path
    safe_target_entry "$relative_path" || {
        printf 'Error: refusing to write through a symbolic link: %s\n' "$relative_path" >&2
        return 1
    }
    next_entry=$((transaction_entry_count + 1))
    entry_path=$transaction_root/entry-$next_entry
    mkdir "$entry_path"
    if [ -e "$destination_file" ] || [ -L "$destination_file" ]; then
        if [ -L "$destination_file" ] || [ ! -f "$destination_file" ]; then
            printf 'Error: managed file path is incompatible: %s\n' "$relative_path" >&2
            rm -rf "$entry_path"
            return 1
        fi
        cp -p "$destination_file" "$entry_path/before" || { rm -rf "$entry_path"; return 1; }
        cp -p "$destination_file" "$entry_path/after" || { rm -rf "$entry_path"; return 1; }
        cat "$source_file" > "$entry_path/after" || { rm -rf "$entry_path"; return 1; }
        entry_state=existing
    else
        cp -p "$source_file" "$entry_path/after" || { rm -rf "$entry_path"; return 1; }
        entry_state=new
    fi
    printf '%s\n%s\n' "$relative_path" "$entry_state" > "$entry_path/manifest.txt"
    transaction_entry_count=$next_entry
    parent_relative=${relative_path%/*}
    if [ "$parent_relative" != "$relative_path" ]; then
        ensure_target_directory "$parent_relative" || return 1
    fi
    temporary_file=$(mktemp "$(dirname "$destination_file")/.codex-orchestrator-install.XXXXXXXX") || return 1
    safe_target_entry "$relative_path" || { rm -f "$temporary_file"; return 1; }
    if [ "$entry_state" = existing ]; then
        if ! files_match "$destination_file" "$entry_path/before"; then
            rm -f "$temporary_file"
            printf 'Error: managed file changed during setup; preserving current contents: %s\n' "$relative_path" >&2
            return 1
        fi
    elif [ -e "$destination_file" ] || [ -L "$destination_file" ]; then
        rm -f "$temporary_file"
        printf 'Error: managed path appeared during setup; preserving current contents: %s\n' "$relative_path" >&2
        return 1
    fi
    if ! cp -p "$entry_path/after" "$temporary_file" || ! mv -f "$temporary_file" "$destination_file"; then
        rm -f "$temporary_file"
        return 1
    fi
}

install_tree() {
    source_path=$1
    component=$2
    if [ ! -d "$target_dir/$component" ]; then
        mkdir "$target_dir/$component" || return 1
        printf '%s\n' "$component" >> "$transaction_root/created-dirs"
    fi
    find "$source_path" -type f -print > "$transaction_root/source-files"
    while IFS= read -r source_file; do
        relative_inside=${source_file#"$source_path"/}
        install_file "$source_file" "$component/$relative_inside" || exit 1
    done < "$transaction_root/source-files"
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
        agents/skills/codex-orchestrator/SKILL.md; do
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
    printf '%s\n' '  1) Pro  - Astra root; Luna defaults/explore/research; Sol worker/tester; Astra reviewer'
    printf '%s\n' '  2) Plus - Luna root (max); Luna defaults/roles; Astra reviewer'
    printf '%s\n' '  3) Pro (max 2 subagents)  - Pro topology with two concurrent subagent threads'
    printf '%s\n' '  4) Plus (max 2 subagents) - Plus topology with two concurrent subagent threads'

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
    namespace=$3
    if [ "$namespace" = legacy ]; then
        begin_marker=$legacy_managed_begin
        end_marker=$legacy_managed_end
    else
        begin_marker=$managed_begin
        end_marker=$managed_end
    fi

    awk -v begin="$begin_marker" -v end="$end_marker" '
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

classify_managed_block() {
    source_path=$1
    awk -v cb="$managed_begin" -v ce="$managed_end" \
        -v lb="$legacy_managed_begin" -v le="$legacy_managed_end" '
        $0 == cb { cbn++; cbi = NR }
        $0 == ce { cen++; cei = NR }
        $0 == lb { lbn++; lbi = NR }
        $0 == le { len++; lei = NR }
        END {
            if (cbn == 0 && cen == 0 && lbn == 0 && len == 0) exit 2
            if (cbn == 1 && cen == 1 && lbn == 0 && len == 0 && cbi < cei) {
                print "canonical"; exit 0
            }
            if (lbn == 1 && len == 1 && cbn == 0 && cen == 0 && lbi < lei) {
                print "legacy"; exit 0
            }
            exit 1
        }
    ' "$source_path"
}

prepare_legacy_skill_archive() {
    legacy_skill_path=$target_dir/.agents/skills/astra-orchestrator
    legacy_archive_path=
    if [ ! -e "$legacy_skill_path" ] && [ ! -L "$legacy_skill_path" ]; then
        return 0
    fi
    if [ -L "$legacy_skill_path" ] || [ ! -d "$legacy_skill_path" ]; then
        printf '%s\n' 'Error: refusing to archive an incompatible or symbolic link legacy skill path.' >&2
        return 1
    fi

    archive_root=$target_dir/.agents/migration-backups
    if { [ -e "$archive_root" ] || [ -L "$archive_root" ]; } && { [ -L "$archive_root" ] || [ ! -d "$archive_root" ]; }; then
        printf '%s\n' 'Error: migration backup path must be a regular directory.' >&2
        return 1
    fi
    archive_name=astra-orchestrator
    archive_candidate=$archive_root/$archive_name
    archive_suffix=1
    while [ -e "$archive_candidate" ] || [ -L "$archive_candidate" ]; do
        archive_candidate=$archive_root/$archive_name.$archive_suffix
        archive_suffix=$((archive_suffix + 1))
    done
    legacy_archive_path=${archive_candidate#"$target_dir/"}
}

archive_legacy_skill() {
    [ -n "$legacy_archive_path" ] || return 0
    legacy_skill_path=$target_dir/.agents/skills/astra-orchestrator
    archive_destination=$target_dir/$legacy_archive_path
    safe_target_entry .agents/skills/astra-orchestrator || return 1
    safe_target_entry "$legacy_archive_path" || return 1
    ensure_target_directory .agents/migration-backups || return 1
    if [ -e "$archive_destination" ] || [ -L "$archive_destination" ]; then
        printf 'Error: migration archive destination appeared during setup: %s\n' "$legacy_archive_path" >&2
        return 1
    fi
    printf '%s|%s\n' '.agents/skills/astra-orchestrator' "$legacy_archive_path" > "$transaction_root/legacy-move"
    if ! mv "$legacy_skill_path" "$archive_destination"; then
        rm -f "$transaction_root/legacy-move"
        printf 'Error: could not archive legacy skill to %s.\n' "$legacy_archive_path" >&2
        return 1
    fi
    legacy_skill_archived=yes
    printf 'Archived legacy skill: .agents/skills/astra-orchestrator -> %s\n' "$legacy_archive_path"
}

replace_managed_block() {
    normalized_path=$1
    destination_path=$2
    replacement_path=$3
    replacement_output=$transaction_root/agents-updated

    if ! awk -v begin="$replace_begin_marker" -v end="$replace_end_marker" -v replacement="$replacement_path" '
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

    if [ "${preserve_crlf:-no}" = yes ]; then
        crlf_output=$transaction_root/agents-updated-crlf
        if ! awk '{ printf "%s\r\n", $0 }' "$replacement_output" > "$crlf_output"; then
            printf 'Error: could not preserve CRLF line endings in %s.\n' "$destination_path" >&2
            return 1
        fi
        replacement_output=$crlf_output
    fi
    install_file "$replacement_output" AGENTS.md || {
        printf 'Error: could not write the managed block to %s.\n' "$destination_path" >&2
        return 1
    }
}

install_managed_agents() {
    destination_path=$1
    safe_target_entry AGENTS.md || {
        printf '%s\n' 'Error: AGENTS.md path passes through a symbolic link.' >&2
        return 1
    }
    normalized_path=$transaction_root/agents-normalized
    current_block_path=$transaction_root/current-managed-block

    if ! sed 's/\r$//' "$destination_path" > "$normalized_path"; then
        printf 'Error: could not read existing AGENTS.md.\n' >&2
        return 1
    fi
    crlf_count=$(LC_ALL=C tr -cd '\r' < "$destination_path" | wc -c | tr -d ' ')
    preserve_crlf=no
    if [ "$crlf_count" -gt 0 ]; then
        preserve_crlf=yes
    fi

    if current_namespace=$(classify_managed_block "$normalized_path"); then
        if ! extract_managed_block "$normalized_path" "$current_block_path" "$current_namespace"; then
            printf '%s\n' 'Error: existing AGENTS.md has a malformed managed block.' >&2
            return 1
        fi
        if cmp -s "$current_block_path" "$managed_block_path"; then
            printf '%s\n' 'Skipped AGENTS.md: managed instructions are already up to date.'
            component_satisfied=yes
            agents_instructions_canonical=yes
            return 0
        fi

        printf '%s\n' 'WARNING: AGENTS.md contains an older managed instruction block.'
        if ! cp -p "$destination_path" "$transaction_root/agents-original"; then
            printf '%s\n' 'Error: could not snapshot AGENTS.md before prompting.' >&2
            return 1
        fi
        if ! confirm 'Update the managed instructions in AGENTS.md?' no; then
            printf '%s\n' 'Skipped AGENTS.md (existing managed instructions left unchanged).'
            return 0
        fi
        if ! files_match "$destination_path" "$transaction_root/agents-original"; then
            printf '%s\n' 'Error: AGENTS.md changed while setup was waiting; no instruction text was replaced. Rerun setup to review the new file.' >&2
            return 1
        fi
        if [ "$current_namespace" = legacy ]; then
            replace_begin_marker=$legacy_managed_begin
            replace_end_marker=$legacy_managed_end
        else
            replace_begin_marker=$managed_begin
            replace_end_marker=$managed_end
        fi
        if ! replace_managed_block "$normalized_path" "$destination_path" "$managed_block_path"; then
            return 1
        fi
        printf '%s\n' 'Updated the managed instructions in AGENTS.md.'
        component_installed=yes
        component_satisfied=yes
        agents_instructions_canonical=yes
        return 0
    else
        classify_status=$?
        if [ "$classify_status" -ne 2 ]; then
            printf '%s\n' 'Error: existing AGENTS.md has malformed, mixed, duplicate, or reversed managed markers.' >&2
            return 1
        fi
    fi

    printf '%s\n' 'WARNING: existing AGENTS.md has no managed instruction block; setup will append one.'
    if ! cp -p "$destination_path" "$transaction_root/agents-original"; then
        printf '%s\n' 'Error: could not snapshot AGENTS.md before prompting.' >&2
        return 1
    fi
    if ! confirm 'Add the managed instructions to AGENTS.md?' no; then
        printf '%s\n' 'Skipped AGENTS.md (existing contents left unchanged).'
        return 0
    fi
    if ! files_match "$destination_path" "$transaction_root/agents-original"; then
        printf '%s\n' 'Error: AGENTS.md changed while setup was waiting; no instruction text was replaced. Rerun setup to review the new file.' >&2
        return 1
    fi
    if [ -s "$destination_path" ]; then
        printf '\n\n' >> "$normalized_path"
    fi
    if ! cat "$managed_block_path" >> "$normalized_path"; then
        printf 'Error: could not append managed instructions to %s.\n' "$destination_path" >&2
        return 1
    fi
    install_file "$normalized_path" AGENTS.md || return 1
    printf '%s\n' 'Appended managed instructions to AGENTS.md. Existing contents preserved.'
    component_installed=yes
    component_satisfied=yes
    agents_instructions_canonical=yes
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
    safe_target_entry "$name" || {
        printf 'Skipped %s: target path passes through a symbolic link.\n' "$name" >&2
        return 0
    }

    if [ "$name" = AGENTS.md ] && [ ! -e "$destination_path" ] && [ ! -L "$destination_path" ]; then
        source_path=$managed_block_path
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
        if [ "$name" = .agents ]; then
            if ! prepare_legacy_skill_archive; then
                return 1
            fi
            if [ -n "$legacy_archive_path" ]; then
                printf 'This update will archive .agents/skills/astra-orchestrator to %s.\n' "$legacy_archive_path"
            fi
        fi
        if ! confirm "Update $name? New files will be added; only paths listed above will be replaced." no; then
            printf 'Skipped %s (existing target left unchanged).\n' "$name"
            return 0
        fi

        if [ -d "$source_path" ] && [ -d "$destination_path" ]; then
            if [ "$name" = .agents ] && ! archive_legacy_skill; then
                return 1
            fi
            if ! install_tree "$source_path" "$name"; then
                printf 'Error: could not update %s.\n' "$name" >&2
                return 1
            fi
        elif [ -f "$source_path" ] && [ -f "$destination_path" ]; then
            if ! install_file "$source_path" "$name"; then
                printf 'Error: could not update %s.\n' "$name" >&2
                return 1
            fi
        else
            printf 'Error: source and target types are incompatible for %s.\n' "$name" >&2
            return 1
        fi
        printf 'Updated %s.\n' "$name"
    else
        if [ -d "$source_path" ]; then
            if ! install_tree "$source_path" "$name"; then
                printf 'Error: could not install %s.\n' "$name" >&2
                return 1
            fi
        elif ! install_file "$source_path" "$name"; then
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
        if [ "$component" = AGENTS.md ] && [ "$component_satisfied" = yes ]; then
            agents_instructions_canonical=yes
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
if [ "$legacy_skill_archived" = yes ] && [ "$agents_instructions_canonical" != yes ]; then
    printf '%s\n' 'WARNING: the legacy skill was archived, but AGENTS.md may still reference astra-orchestrator. Approve the AGENTS.md update or edit those references, then rerun setup.' >&2
fi
if [ "$agents_instructions_canonical" = yes ] && [ ! -f "$target_dir/.agents/skills/codex-orchestrator/SKILL.md" ]; then
    printf '%s\n' 'WARNING: AGENTS.md now invokes codex-orchestrator, but the canonical skill is missing because .agents was skipped or declined. Approve the .agents update, then rerun setup.' >&2
fi
if [ "$satisfied" -lt 3 ]; then
    printf 'WARNING: partial installation completed (%s of 3 components satisfied).\n' "$satisfied" >&2
fi
printf '\nSetup complete. %s component(s) installed in %s (plan: %s).\n' "$installed" "$target_dir" "$plan"
printf '%s\n' 'See guides/ for optional Codex model and Fast-mode configurations.'
