#!/usr/bin/env python3
"""Aggregate Codex token usage for an orchestrated session.

Codex writes rollout JSONL segments under ~/.codex/sessions. Subagent threads
carry the root thread id in `session_id`, so grouping available files by that
value reports observed usage by stable thread, segment, role, and model. A
directory scan cannot establish that every related rollout is present, and
token usage is not a billing total.

Usage:
  scripts/token_usage.py --list [--date YYYY-MM-DD]
  scripts/token_usage.py --root <root-thread-id-or-prefix> [--format md|json]
  scripts/token_usage.py --latest

Standard library only. Read-only: it never modifies the session files.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date as date_type, datetime, timezone
from pathlib import Path

USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
MAX_COUNTER = 2**64 - 1


def finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_COUNTER
    return isinstance(value, float) and math.isfinite(value)


def valid_counter(value: object) -> bool:
    return finite_number(value) and 0 <= value <= MAX_COUNTER and int(value) == value


def empty_usage() -> dict[str, int]:
    return {k: 0 for k in USAGE_KEYS}


def add_usage(target: dict[str, int], usage: dict, diagnostics: list[str] | None = None, context: str = "usage") -> None:
    for k in USAGE_KEYS:
        value = usage.get(k)
        if value is None:
            continue
        if not valid_counter(value):
            if diagnostics is not None:
                diagnostics.append(f"{context}: invalid {k} counter; value ignored")
            continue
        target[k] += int(value)


def parse_ts(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def iter_rollouts(sessions_dir: Path, date: str | None):
    if date:
        y, m, d = date.split("-")
        base = sessions_dir / y / m / d
        if not base.is_dir():
            return
        yield from sorted(base.glob("rollout-*.jsonl"))
        return
    yield from sorted(sessions_dir.rglob("rollout-*.jsonl"))


def date_arg(value: str) -> str:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}", value):
            raise ValueError
        parts = value.split("-")
        return date_type(*(int(part) for part in parts)).isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("expected date in YYYY-MM-DD format") from exc


def read_meta(path: Path, diagnostics: list[str] | None = None) -> dict | None:
    try:
        with path.open("rb") as fh:
            first = fh.readline().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        if diagnostics is not None:
            diagnostics.append(f"{path.name}: cannot read session metadata ({exc.__class__.__name__})")
        return None
    try:
        obj = json.loads(first)
    except (ValueError, UnicodeError, RecursionError):
        if diagnostics is not None:
            diagnostics.append(f"{path.name}: malformed session metadata JSON")
        return None
    if not isinstance(obj, dict) or obj.get("type") != "session_meta":
        if diagnostics is not None:
            diagnostics.append(f"{path.name}: missing or invalid session_meta record")
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        if diagnostics is not None:
            diagnostics.append(f"{path.name}: invalid session metadata payload")
        return None
    return payload


def thread_role(meta: dict) -> tuple[str, str]:
    """Return (role, nickname) for a thread."""
    source = meta.get("source")
    if isinstance(source, dict):
        sub = source.get("subagent") or {}
        if isinstance(sub, str):
            return sub, ""
        if isinstance(sub, dict):
            spawn = sub.get("thread_spawn")
            if isinstance(spawn, dict):
                role = spawn.get("agent_role")
                nickname = spawn.get("agent_nickname")
                return (
                    role if isinstance(role, str) and role else "subagent",
                    nickname if isinstance(nickname, str) else "",
                )
            other = sub.get("other")
            if other:
                return str(other), ""
    meta_id = meta.get("id")
    session_id = meta.get("session_id")
    effective_id = meta_id if isinstance(meta_id, str) and meta_id else session_id
    if isinstance(effective_id, str) and effective_id and effective_id == session_id:
        return "root", ""
    thread_source = meta.get("thread_source")
    if isinstance(thread_source, str) and thread_source:
        return thread_source, ""
    if isinstance(meta_id, str) and meta_id and not isinstance(session_id, str) and not meta.get("parent_thread_id"):
        return "root", ""
    if meta.get("parent_thread_id"):
        return "subagent", ""
    return "unknown", ""


def clean_rate_limits(value: object, path: Path, diagnostics: list[str]) -> dict | None:
    if not isinstance(value, dict):
        if value is not None:
            diagnostics.append(f"{path.name}: invalid rate_limits object")
        return None
    cleaned = {}
    for key in ("primary", "secondary"):
        window = value.get(key)
        if window is None:
            continue
        if not isinstance(window, dict):
            diagnostics.append(f"{path.name}: invalid {key} rate limit")
            continue
        output = {}
        percent = window.get("used_percent")
        if percent is not None:
            if finite_number(percent) and percent >= 0:
                output["used_percent"] = percent
            else:
                diagnostics.append(f"{path.name}: invalid {key} used_percent")
        minutes = window.get("window_minutes")
        if minutes is not None:
            if valid_counter(minutes) and minutes > 0:
                output["window_minutes"] = minutes
            else:
                diagnostics.append(f"{path.name}: invalid {key} window_minutes")
        resets = window.get("resets_at")
        if resets is not None:
            if finite_number(resets) and abs(resets) <= MAX_COUNTER:
                output["resets_at"] = resets
            else:
                diagnostics.append(f"{path.name}: invalid {key} resets_at")
        limit_id = window.get("limit_id")
        if limit_id is not None:
            if isinstance(limit_id, str):
                output["limit_id"] = limit_id
            else:
                diagnostics.append(f"{path.name}: invalid {key} limit_id")
        cleaned[key] = output
    plan = value.get("plan_type")
    if plan is not None:
        if isinstance(plan, str):
            cleaned["plan_type"] = plan
        else:
            diagnostics.append(f"{path.name}: invalid rate limit plan_type")
    limit_id = value.get("limit_id")
    if limit_id is not None:
        if isinstance(limit_id, str):
            cleaned["limit_id"] = limit_id
        else:
            diagnostics.append(f"{path.name}: invalid rate limit limit_id")
    return cleaned or None


def analyze_thread(path: Path, meta: dict, diagnostics: list[str]) -> dict:
    role, nickname = thread_role(meta)
    per_model: dict[str, dict[str, int]] = defaultdict(empty_usage)
    responses: dict[str, int] = defaultdict(int)
    model = None
    effort = None
    first_ts = parse_ts(meta.get("timestamp"))
    if meta.get("timestamp") is not None and first_ts is None:
        diagnostics.append(f"{path.name}: invalid session timestamp")
    last_ts = first_ts
    last_total = None
    last_total_fields: list[str] = []
    rate_first = None
    rate_last = None

    try:
        fh = path.open("rb")
    except OSError as exc:
        diagnostics.append(f"{path.name}: cannot read rollout ({exc.__class__.__name__})")
        fh = None
    line_number = 0
    if fh is not None:
        with fh:
            try:
                for raw_line in fh:
                    line_number += 1
                    try:
                        line = raw_line.decode("utf-8")
                    except UnicodeDecodeError:
                        diagnostics.append(f"{path.name}:{line_number}: invalid UTF-8; record skipped")
                        continue
                    try:
                        obj = json.loads(line)
                    except (ValueError, RecursionError):
                        diagnostics.append(f"{path.name}:{line_number}: malformed JSON record skipped")
                        continue
                    if not isinstance(obj, dict):
                        diagnostics.append(f"{path.name}:{line_number}: invalid rollout record; skipped")
                        continue
                    ts = parse_ts(obj.get("timestamp"))
                    if obj.get("timestamp") is not None and ts is None:
                        diagnostics.append(f"{path.name}:{line_number}: invalid record timestamp")
                    if ts and (last_ts is None or ts > last_ts):
                        last_ts = ts
                    kind = obj.get("type")
                    if not isinstance(kind, str):
                        diagnostics.append(f"{path.name}:{line_number}: invalid record type; skipped")
                        continue
                    payload = obj.get("payload")
                    if not isinstance(payload, dict):
                        if kind in {"token_usage_record", "event_msg"}:
                            diagnostics.append(f"{path.name}:{line_number}: invalid {kind} payload")
                        continue
                    if kind == "turn_context":
                        candidate_model = payload.get("model")
                        if isinstance(candidate_model, str) and candidate_model:
                            model = candidate_model
                        elif candidate_model is not None:
                            diagnostics.append(f"{path.name}:{line_number}: invalid model identity")
                        candidate_effort = payload.get("effort")
                        if isinstance(candidate_effort, str):
                            effort = candidate_effort or effort
                        elif candidate_effort is not None:
                            diagnostics.append(f"{path.name}:{line_number}: invalid model effort")
                    elif kind == "token_usage_record" or (
                        kind == "event_msg" and payload.get("type") == "token_usage_record"
                    ):
                        usage = payload.get("usage")
                        if not isinstance(usage, dict):
                            diagnostics.append(f"{path.name}:{line_number}: invalid response usage object")
                            continue
                        key = model or "unknown"
                        add_usage(per_model[key], usage, diagnostics, f"{path.name}:{line_number}")
                        responses[key] += 1
                    elif kind == "event_msg" and payload.get("type") == "token_count":
                        info = payload.get("info")
                        if isinstance(info, dict):
                            total_usage = info.get("total_token_usage")
                            if isinstance(total_usage, dict):
                                validated = empty_usage()
                                add_usage(validated, total_usage, diagnostics, f"{path.name}:{line_number} cumulative")
                                last_total = validated
                                last_total_fields = [
                                    key for key in USAGE_KEYS if key in total_usage and valid_counter(total_usage[key])
                                ]
                            elif total_usage is not None:
                                diagnostics.append(f"{path.name}:{line_number}: invalid cumulative usage object")
                        elif info is not None:
                            diagnostics.append(f"{path.name}:{line_number}: invalid token_count info object")
                        cleaned_limits = clean_rate_limits(payload.get("rate_limits"), path, diagnostics)
                        if cleaned_limits:
                            if rate_first is None:
                                rate_first = cleaned_limits
                            rate_last = cleaned_limits
            except OSError as exc:
                diagnostics.append(f"{path.name}: read failed ({exc.__class__.__name__}); report is partial")

    # Older Codex builds may not emit token_usage_record; fall back to the
    # cumulative counter attributed to the last active model.
    if not per_model and isinstance(last_total, dict):
        add_usage(per_model[model or "unknown"], last_total, diagnostics, f"{path.name} cumulative")

    if last_total is not None and per_model:
        response_components = {key: sum(usage[key] for usage in per_model.values()) for key in USAGE_KEYS}
        mismatches = [
            key for key in last_total_fields
            if response_components[key] != last_total[key]
        ]
        if mismatches:
            diagnostics.append(
                f"{path.name}: cumulative counters differ from per-response counters for {', '.join(mismatches)}; per-response records are reported"
            )

    thread_id = meta.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        thread_id = (
            meta.get("session_id")
            if role == "root" and isinstance(meta.get("session_id"), str)
            else None
        )
        diagnostics.append(f"{path.name}: missing or invalid thread id; using fallback identity")
    parent_thread_id = meta.get("parent_thread_id")
    if parent_thread_id is not None and not isinstance(parent_thread_id, str):
        diagnostics.append(f"{path.name}: invalid parent thread id")
        parent_thread_id = None

    return {
        "id": thread_id or f"unknown:{path.stem}",
        "stable_thread_id": thread_id or f"unknown:{path.stem}",
        "segment": 1,
        "segment_count": 1,
        "parent_thread_id": parent_thread_id,
        "role": role,
        "nickname": nickname,
        "model": model,
        "effort": effort if isinstance(effort, str) else None,
        "cwd": meta.get("cwd") if isinstance(meta.get("cwd"), str) else None,
        "cli_version": meta.get("cli_version") if isinstance(meta.get("cli_version"), str) else None,
        "started": first_ts,
        "ended": last_ts,
        "per_model": dict(per_model),
        "responses": dict(responses),
        "cumulative_total": last_total,
        "cumulative_fields": last_total_fields,
        "rate_first": rate_first,
        "rate_last": rate_last,
        "path": str(path),
    }


def collect_sessions(sessions_dir: Path, date: str | None, diagnostics: list[str] | None = None) -> dict[str, list[tuple[Path, dict]]]:
    sessions: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for path in iter_rollouts(sessions_dir, date):
        meta = read_meta(path, diagnostics)
        if not meta:
            continue
        session_id = meta.get("session_id")
        thread_id = meta.get("id")
        root = session_id if isinstance(session_id, str) and session_id else thread_id
        if not isinstance(root, str) or not root:
            if diagnostics is not None:
                diagnostics.append(f"{path.name}: missing or invalid session identity; rollout skipped")
            continue
        if not isinstance(meta.get("id"), str) or not meta.get("id"):
            if diagnostics is not None:
                diagnostics.append(f"{path.name}: missing or invalid thread identity")
        if meta.get("session_id") is not None and not isinstance(meta.get("session_id"), str):
            if diagnostics is not None:
                diagnostics.append(f"{path.name}: invalid session identity; using thread id fallback")
        sessions[root].append((path, meta))
    return sessions


def is_guardian(role: str) -> bool:
    return role in {"guardian", "guardian_review"}


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_pct(limits: dict | None, key: str) -> str:
    if not limits or not limits.get(key):
        return "-"
    return f"{limits[key].get('used_percent', '-')}%"


def fmt_window(limits: dict | None, key: str) -> str:
    window = limits.get(key) if limits else None
    minutes = window.get("window_minutes") if isinstance(window, dict) else None
    return f"{int(minutes)}m" if isinstance(minutes, (int, float)) else "unknown window"


def rate_warnings(first: dict | None, last: dict | None) -> list[str]:
    warnings = []
    if not first or not last:
        return warnings
    if first.get("limit_id") != last.get("limit_id"):
        warnings.append("limit identity changed; snapshots may not be comparable")
    if first.get("plan_type") != last.get("plan_type"):
        warnings.append("plan identity changed; snapshots may not be comparable")
    for key in ("primary", "secondary"):
        a, b = first.get(key), last.get(key)
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if a.get("window_minutes") != b.get("window_minutes"):
            warnings.append(f"{key} window duration changed; snapshots may not be comparable")
        if a.get("resets_at") != b.get("resets_at"):
            warnings.append(f"{key} reset time changed; snapshots may not be comparable")
        if a.get("limit_id") != b.get("limit_id"):
            warnings.append(f"{key} limit identity changed; snapshots may not be comparable")
    return warnings


def fmt_duration(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return "-"
    seconds = int((end - start).total_seconds())
    return f"{seconds // 60}m{seconds % 60:02d}s"


def render_markdown(root_id: str, threads: list[dict], include_guardian: bool, scope: dict, diagnostics: list[str]) -> str:
    root = next((t for t in threads if t["role"] == "root"), None)
    counted = [t for t in threads if include_guardian or not is_guardian(t["role"])]
    skipped = [t for t in threads if t not in counted]

    starts = [t["started"] for t in threads if t["started"]]
    ends = [t["ended"] for t in threads if t["ended"]]
    wall = fmt_duration(min(starts), max(ends)) if starts and ends else "-"

    lines: list[str] = []
    lines.append(f"### Session `{root_id[:8]}`")
    lines.append("")
    if root:
        lines.append(f"- cwd: `{root['cwd']}`")
        lines.append(f"- codex: `{root['cli_version']}`")
    unique_counted = {t["stable_thread_id"] for t in counted}
    unique_skipped = {t["stable_thread_id"] for t in skipped}
    unique_total = len({t["stable_thread_id"] for t in threads})
    lines.append(f"- threads: {unique_total} ({len(unique_counted)} counted, {len(unique_skipped)} auto-review skipped), unique across {len(threads)} rollout segments")
    lines.append(f"- wall time: {wall}")
    if scope["date_filter"]:
        lines.append(f"- coverage: partial; scanned only rollouts dated `{scope['date_filter']}`")
    else:
        lines.append("- coverage: scanned sessions directory; complete log coverage is unknown")
    if root and root["rate_first"] and root["rate_last"]:
        rf, rl = root["rate_first"], root["rate_last"]
        plan = rl.get("plan_type") or "-"
        lines.append(
            f"- rate limit ({plan}, root segment {root['segment']}/{root['segment_count']}): "
            f"{fmt_window(rf, 'primary')} {fmt_pct(rf, 'primary')} -> {fmt_window(rl, 'primary')} {fmt_pct(rl, 'primary')}, "
            f"{fmt_window(rf, 'secondary')} {fmt_pct(rf, 'secondary')} -> {fmt_window(rl, 'secondary')} {fmt_pct(rl, 'secondary')}"
        )
        lines.extend(f"- warning: {warning}" for warning in rate_warnings(rf, rl))
        if root["segment_count"] > 1:
            lines.append(
                f"- warning: rate limit line uses root segment {root['segment']}; inspect other segments separately"
            )
    elif root and root["segment_count"] > 1:
        lines.append(
            f"- rate limit snapshots vary by root rollout segment; inspect each segment in JSON ({root['segment_count']} segments)"
        )
    lines.append("")

    lines.append("| Thread | Segment | Role | Model / effort | Responses | Uncached in | Cached in | Output | Reasoning | Total | Duration |")
    lines.append("|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|")
    grand = empty_usage()
    by_model: dict[str, dict[str, int]] = defaultdict(empty_usage)
    by_model_responses: dict[str, int] = defaultdict(int)
    for t in counted:
        for model, usage in sorted(t["per_model"].items()):
            uncached = usage["input_tokens"] - usage["cached_input_tokens"]
            label = t["role"] + (f" ({t['nickname']})" if t["nickname"] else "")
            effort = t["effort"] if model == t["model"] else "?"
            lines.append(
                f"| `{t['stable_thread_id'][:8]}` | {t['segment']}/{t['segment_count']} | {label} | {model} / {effort} | {t['responses'].get(model, 0)} | "
                f"{fmt_int(uncached)} | {fmt_int(usage['cached_input_tokens'])} | {fmt_int(usage['output_tokens'])} | "
                f"{fmt_int(usage['reasoning_output_tokens'])} | {fmt_int(usage['total_tokens'])} | "
                f"{fmt_duration(t['started'], t['ended'])} |"
            )
            add_usage(grand, usage)
            add_usage(by_model[model], usage)
            by_model_responses[model] += t["responses"].get(model, 0)
    lines.append("")

    lines.append("| Model | Threads | Responses | Uncached in | Cached in | Output | Reasoning | Total |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for model, usage in sorted(by_model.items()):
        n_threads = len({t["stable_thread_id"] for t in counted if model in t["per_model"]})
        uncached = usage["input_tokens"] - usage["cached_input_tokens"]
        lines.append(
            f"| {model} | {n_threads} | {by_model_responses[model]} | {fmt_int(uncached)} | "
            f"{fmt_int(usage['cached_input_tokens'])} | {fmt_int(usage['output_tokens'])} | "
            f"{fmt_int(usage['reasoning_output_tokens'])} | {fmt_int(usage['total_tokens'])} |"
        )
    g_uncached = grand["input_tokens"] - grand["cached_input_tokens"]
    lines.append(
        f"| **all** | {len(unique_counted)} | {sum(by_model_responses.values())} | {fmt_int(g_uncached)} | "
        f"{fmt_int(grand['cached_input_tokens'])} | {fmt_int(grand['output_tokens'])} | "
        f"{fmt_int(grand['reasoning_output_tokens'])} | {fmt_int(grand['total_tokens'])} |"
    )
    if grand["input_tokens"]:
        pct = 100.0 * grand["cached_input_tokens"] / grand["input_tokens"]
        lines.append("")
        lines.append(f"Cache hit rate on input: {pct:.1f}%")
    if skipped:
        lines.append("")
        lines.append(
            "Skipped auto-review threads: "
            + ", ".join(f"`{t['id'][:8]}` ({t['model'] or 'unknown'})" for t in skipped)
            + ". Pass `--include-guardian` to count them."
        )
    if diagnostics:
        lines.extend(("", "Diagnostics:", *(f"- {item}" for item in diagnostics)))
    return "\n".join(lines)


def to_json(root_id: str, threads: list[dict], include_guardian: bool, scope: dict, diagnostics: list[str]) -> str:
    def clean(t: dict) -> dict:
        out = dict(t)
        out["started"] = t["started"].isoformat() if t["started"] else None
        out["ended"] = t["ended"].isoformat() if t["ended"] else None
        out["counted"] = include_guardian or not is_guardian(t["role"])
        return out

    thread_count = len({t["stable_thread_id"] for t in threads})
    return json.dumps({
        "root": root_id,
        "scope": scope,
        "diagnostics": diagnostics,
        "thread_count": thread_count,
        "segment_count": len(threads),
        "threads": [clean(t) for t in threads],
    }, indent=2, allow_nan=False)


def list_sessions(sessions: dict[str, list[tuple[Path, dict]]], limit: int) -> None:
    rows = []
    for root_id, items in sessions.items():
        metas = [m for _, m in items]
        root_meta = next((m for m in metas if (m.get("session_id") or m.get("id")) == root_id and thread_role(m)[0] == "root"), None)
        started = parse_ts((root_meta or metas[0]).get("timestamp"))
        children = {
            m.get("id") for m in metas
            if isinstance(m.get("id"), str) and m.get("id") != root_id and not is_guardian(thread_role(m)[0])
        }
        n_sub = len(children)
        rows.append((started or datetime.min.replace(tzinfo=timezone.utc), root_id, n_sub, len(items), (root_meta or metas[0]).get("cwd")))
    rows.sort(reverse=True)
    print("started (UTC)       root id   subagents  segments  cwd")
    for started, root_id, n_sub, n_segments, cwd in rows[:limit]:
        print(f"{started.strftime('%Y-%m-%d %H:%M'):<19} {root_id[:8]}  {n_sub:>9}  {n_segments:>8}  {cwd}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sessions-dir", default=os.path.expanduser("~/.codex/sessions"))
    parser.add_argument(
        "--date",
        type=date_arg,
        help="Only scan this day's rollouts (YYYY-MM-DD); reports explicitly mark this scope partial.",
    )
    parser.add_argument("--list", action="store_true", help="List root sessions and their subagent counts.")
    parser.add_argument("--limit", type=int, default=20, help="Rows to show with --list.")
    parser.add_argument("--root", help="Root thread id (or unique prefix) to report on.")
    parser.add_argument("--latest", action="store_true", help="Report on the most recent session that spawned subagents.")
    parser.add_argument("--include-guardian", action="store_true", help="Count Codex auto-review threads in totals.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    sessions_dir = Path(args.sessions_dir)
    if not sessions_dir.is_dir():
        print(f"sessions dir not found: {sessions_dir}", file=sys.stderr)
        return 2

    diagnostics: list[str] = []
    sessions = collect_sessions(sessions_dir, args.date, diagnostics)
    if not sessions:
        print("no rollouts found", file=sys.stderr)
        for diagnostic in diagnostics:
            print(f"warning: {diagnostic}", file=sys.stderr)
        return 1

    if args.list:
        list_sessions(sessions, args.limit)
        if args.date:
            print(f"scope: partial date-filtered scan for {args.date}", file=sys.stderr)
        for diagnostic in diagnostics:
            print(f"warning: {diagnostic}", file=sys.stderr)
        return 0

    root_id = None
    if args.root:
        matches = [r for r in sessions if r.startswith(args.root)]
        if len(matches) != 1:
            print(f"--root matched {len(matches)} sessions; give a longer prefix", file=sys.stderr)
            return 2
        root_id = matches[0]
    elif args.latest:
        candidates = []
        for rid, items in sessions.items():
            subs = [m for _, m in items if m.get("id") != rid and not is_guardian(thread_role(m)[0])]
            if subs:
                root_meta = next((m for _, m in items if m.get("id") == rid), items[0][1])
                candidates.append((parse_ts(root_meta.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), rid))
        if not candidates:
            print("no session with subagents found", file=sys.stderr)
            return 1
        root_id = max(candidates)[1]
    else:
        parser.print_help()
        return 2

    threads = [analyze_thread(path, meta, diagnostics) for path, meta in sessions[root_id]]
    order = {"root": 0}
    threads.sort(key=lambda t: (order.get(t["role"], 1), t["started"] or datetime.max.replace(tzinfo=timezone.utc)))
    segments: dict[str, list[dict]] = defaultdict(list)
    for thread in threads:
        segments[thread["stable_thread_id"]].append(thread)
    for same_thread in segments.values():
        same_thread.sort(key=lambda t: (t["started"] or datetime.max.replace(tzinfo=timezone.utc), t["path"]))
        for index, thread in enumerate(same_thread, start=1):
            thread["segment"] = index
            thread["segment_count"] = len(same_thread)
        rate_segments = [thread for thread in same_thread if thread["rate_first"] or thread["rate_last"]]
        if rate_segments:
            for segment in rate_segments:
                diagnostics.extend(
                    f"{segment['stable_thread_id']} segment {segment['segment']}: {warning}"
                    for warning in rate_warnings(segment["rate_first"], segment["rate_last"])
                )
    diagnostics = list(dict.fromkeys(diagnostics))
    scope = {
        "date_filter": args.date,
        "scan": "date-filtered-directory" if args.date else "sessions-directory",
        "partial": bool(args.date or diagnostics),
        "coverage_unknown": True,
        "limitations": [
            "A date filter omits rollouts stored under other dates.",
            "Scanning this directory cannot establish that every related rollout exists here.",
        ],
    }

    if args.format == "json":
        print(to_json(root_id, threads, args.include_guardian, scope, diagnostics))
    else:
        print(render_markdown(root_id, threads, args.include_guardian, scope, diagnostics))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
