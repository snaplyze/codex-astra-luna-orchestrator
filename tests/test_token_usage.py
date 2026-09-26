import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.token_usage import analyze_thread, thread_role

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "token_usage.py"
STRING_ROLES = ("review", "compact", "memory_consolidation")


class ThreadRoleTests(unittest.TestCase):
    def test_string_subagent_sources(self):
        for role in STRING_ROLES:
            with self.subTest(role=role):
                self.assertEqual(thread_role({"source": {"subagent": role}}), (role, ""))

    def test_existing_source_shapes(self):
        cases = [
            ({"id": "root", "session_id": "root", "source": "cli"}, ("root", "")),
            (
                {
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "agent_role": "worker",
                                "agent_nickname": "Luna",
                            }
                        }
                    }
                },
                ("worker", "Luna"),
            ),
            ({"source": {"subagent": {"other": "guardian"}}}, ("guardian", "")),
            (
                {"id": "child", "source": "cli", "thread_source": "guardian_review"},
                ("guardian_review", ""),
            ),
        ]
        for meta, expected in cases:
            with self.subTest(meta=meta):
                self.assertEqual(thread_role(meta), expected)

    def test_scalar_subagent_source_is_classified_as_unknown(self):
        self.assertEqual(thread_role({"source": {"subagent": 42}}), ("unknown", ""))


class TokenUsageCliTests(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            for index, role in enumerate(("root", *STRING_ROLES)):
                source = "cli" if role == "root" else {"subagent": role}
                records = [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": role,
                            "session_id": "root",
                            "source": source,
                            "timestamp": "2026-09-09T12:00:00Z",
                            "cwd": "/example",
                        },
                    },
                    {"type": "turn_context", "payload": {"model": "test-model"}},
                    {
                        "type": "token_usage_record",
                        "payload": {
                            "usage": {"input_tokens": 90, "output_tokens": 10, "total_tokens": 100},
                        },
                    },
                ]
                path = Path(directory) / f"rollout-{index}.jsonl"
                path.write_text(
                    "\n".join(json.dumps(record) for record in records), encoding="utf-8"
                )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--sessions-dir", directory, *args],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_list_counts_string_subagent_sources(self):
        output = self.run_cli("--list")
        self.assertRegex(output, r"root\s+3\s+4\s+/example")

    def test_latest_renders_string_subagent_roles(self):
        output = self.run_cli("--latest")
        self.assertIn("4 (4 counted, 0 auto-review skipped)", output)
        for role in STRING_ROLES:
            self.assertIn(f"| {role} | test-model", output)

    def test_root_json_preserves_roles_and_usage(self):
        report = json.loads(self.run_cli("--root", "root", "--format", "json"))
        self.assertEqual({thread["role"] for thread in report["threads"]}, {"root", *STRING_ROLES})
        self.assertEqual(
            sum(thread["per_model"]["test-model"]["total_tokens"] for thread in report["threads"]),
            400,
        )

    def test_invalid_date_is_reported_as_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sessions-dir",
                    directory,
                    "--date",
                    "not-a-date",
                    "--list",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_oversized_date_year_is_reported_as_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--sessions-dir", directory, "--date",
                 "999999999999999999999-1-1", "--list"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_metadata_and_rollout_records_are_skipped_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            valid_records = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "root",
                        "session_id": "root",
                        "source": "cli",
                        "timestamp": "2026-09-09T12:00:00Z",
                    },
                },
                {"type": "turn_context", "payload": {"model": "test-model"}},
                {
                    "type": "token_usage_record",
                    "payload": {
                        "usage": {"input_tokens": 90, "output_tokens": 10, "total_tokens": 100},
                    },
                },
            ]
            (Path(directory) / "rollout-valid.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(valid_records[0]),
                        "[]",
                        json.dumps({"timestamp": [1]}),
                        json.dumps(valid_records[1]),
                        json.dumps({"type": [], "payload": None}),
                        json.dumps({"type": {}, "payload": None}),
                        json.dumps({"type": "token_usage_record", "payload": []}),
                        json.dumps(valid_records[2]),
                    ]
                ),
                encoding="utf-8",
            )
            (Path(directory) / "rollout-malformed-meta.jsonl").write_text(
                json.dumps({"type": "session_meta", "payload": "not-a-dict"}),
                encoding="utf-8",
            )
            (Path(directory) / "rollout-scalar-subagent.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "scalar-subagent",
                                    "session_id": "root",
                                    "source": {"subagent": 42},
                                },
                            }
                        ),
                        json.dumps(valid_records[1]),
                        json.dumps(valid_records[2]),
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sessions-dir",
                    directory,
                    "--root",
                    "root",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["threads"]), 2)
        self.assertEqual(
            next(thread for thread in report["threads"] if thread["id"] == "scalar-subagent")["role"],
            "unknown",
        )
        self.assertEqual(report["threads"][0]["per_model"]["test-model"]["total_tokens"], 100)
        self.assertTrue(report["scope"]["partial"])
        self.assertTrue(any("invalid record type" in item for item in report["diagnostics"]))

    def test_rate_limits_are_independent_of_usage_info(self):
        report = self.run_fixture_report(
            {
                "rollout-root.jsonl": [
                    self.meta("root", "root", "2026-09-25T12:00:00Z"),
                    {"type": "event_msg", "payload": {"type": "token_count", "info": None,
                     "rate_limits": {"primary": {"used_percent": 10}}}},
                    {"type": "event_msg", "payload": {"type": "token_count", "info": {},
                     "rate_limits": {"primary": {"used_percent": 30}}}},
                ]
            }
        )
        self.assertEqual(report["threads"][0]["per_model"], {})
        self.assertEqual(report["threads"][0]["rate_first"]["primary"]["used_percent"], 10)
        self.assertEqual(report["threads"][0]["rate_last"]["primary"]["used_percent"], 30)

    def test_date_scope_is_reported_and_unfiltered_counts_cross_day_rollouts(self):
        files = {
            "2026/09/25/rollout-root.jsonl": [
                self.meta("root", "root", "2026-09-25T23:59:00Z"),
                self.usage(100),
            ],
            "2026/09/26/rollout-child.jsonl": [
                self.meta("child", "root", "2026-09-26T00:01:00Z"),
                self.usage(200),
            ],
        }
        filtered = self.run_fixture_report(files, date="2026-09-25")
        complete_scan = self.run_fixture_report(files)
        self.assertEqual(filtered["scope"]["date_filter"], "2026-09-25")
        self.assertTrue(filtered["scope"]["partial"])
        self.assertEqual(sum_usage(filtered), 100)
        self.assertEqual(complete_scan["scope"]["date_filter"], None)
        self.assertTrue(complete_scan["scope"]["coverage_unknown"])
        self.assertEqual(sum_usage(complete_scan), 300)

    def test_invalid_values_are_diagnostic_and_valid_records_survive(self):
        files = {
            "rollout-root.jsonl": [
                self.meta(None, "root", "2026-09-25T12:00:00"),
                {"type": "turn_context", "payload": {"model": "model", "effort": float("nan")}},
                {"type": "token_usage_record", "payload": {"usage": {"total_tokens": float("inf")}}},
                {"type": "token_usage_record", "payload": {"usage": {"total_tokens": 10**100}}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": None,
                 "rate_limits": {"primary": 42}}},
                self.usage(100),
            ],
        }
        report = self.run_fixture_report(files)
        self.assertEqual(sum_usage(report), 100)
        self.assertTrue(report["diagnostics"])
        self.assertTrue(report["scope"]["partial"])

    def test_legacy_root_fallback_and_normalized_dates(self):
        report = self.run_fixture_report(
            {"2026/09/25/rollout-root.jsonl": [
                {"type": "session_meta", "payload": {"id": "root", "timestamp": "2026-09-25T12:00:00Z",
                 "source": "cli", "cwd": "/example"}}, self.usage(100),
            ]},
            date="2026-9-25",
        )
        self.assertEqual(report["threads"][0]["role"], "root")
        self.assertEqual(report["threads"][0]["cwd"], "/example")
        self.assertEqual(report["scope"]["date_filter"], "2026-09-25")

    def test_legacy_root_id_fallback_handles_non_cli_source(self):
        report = self.run_fixture_report(
            {"rollout-root.jsonl": [
                {"type": "session_meta", "payload": {"id": "root", "timestamp": "2026-09-25T12:00:00Z",
                 "source": "vscode", "cwd": "/example"}},
                self.usage(100),
            ]}
        )
        self.assertEqual(report["threads"][0]["role"], "root")

    def test_invalid_utf8_and_malformed_accounting_payload_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout-root.jsonl"
            path.write_bytes(
                (json.dumps(self.meta("root", "root", "2026-09-25T12:00:00Z")) + "\n").encode()
                + b'{"type":"token_usage_record","payload":[]}\n\xff\n'
                + (json.dumps(self.usage(100)) + "\n").encode()
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--sessions-dir", directory, "--root", "root", "--format", "json"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(sum_usage(report), 100)
        self.assertTrue(report["scope"]["partial"])
        self.assertTrue(any("invalid token_usage_record payload" in d for d in report["diagnostics"]))
        self.assertTrue(any("invalid UTF-8" in d for d in report["diagnostics"]))

    def test_disappearing_rollout_is_a_reported_read_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout-root.jsonl"
            meta = {"id": "root", "session_id": "root", "source": "cli"}
            path.write_text("temporary", encoding="utf-8")
            path.unlink()
            diagnostics = []
            analyze_thread(path, meta, diagnostics)
        self.assertTrue(any("cannot read rollout" in diagnostic for diagnostic in diagnostics))

    def test_list_handles_malformed_thread_id_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout-root.jsonl"
            path.write_text(json.dumps({"type": "session_meta", "payload": {
                "id": [], "session_id": "root", "timestamp": "2026-09-25T12:00:00Z", "source": "cli",
            }}) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--sessions-dir", directory, "--list"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("invalid thread identity", result.stderr)

    def test_list_counts_unique_threads_and_rollout_segments(self):
        files = {
            "rollout-root.jsonl": [self.meta("root", "root", "2026-09-25T12:00:00Z")],
            "rollout-child-a.jsonl": [self.meta("child", "root", "2026-09-25T12:01:00Z", child=True)],
            "rollout-child-b.jsonl": [self.meta("child", "root", "2026-09-25T12:02:00Z", child=True)],
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, records in files.items():
                (Path(directory) / name).write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--sessions-dir", directory, "--list"],
                                    capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"root\s+1\s+3\s+None")

    def test_cumulative_mismatch_is_diagnostic_without_double_counting(self):
        report = self.run_fixture_report(
            {"rollout-root.jsonl": [
                self.meta("root", "root", "2026-09-25T12:00:00Z"),
                {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 100}}}},
                self.usage(200),
                {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 300}}}},
            ]}
        )
        self.assertEqual(sum_usage(report), 200)
        self.assertEqual(report["threads"][0]["cumulative_total"]["total_tokens"], 300)
        self.assertTrue(any("cumulative" in d.lower() for d in report["diagnostics"]))

    def test_cumulative_component_mismatch_is_diagnostic(self):
        report = self.run_fixture_report(
            {"rollout-root.jsonl": [
                self.meta("root", "root", "2026-09-25T12:00:00Z"),
                {"type": "token_usage_record", "payload": {"usage": {
                    "input_tokens": 80, "cached_input_tokens": 0, "output_tokens": 20, "total_tokens": 100,
                }}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 60, "cached_input_tokens": 50,
                     "output_tokens": 40, "total_tokens": 100},
                }}},
            ]}
        )
        self.assertEqual(sum_usage(report), 100)
        self.assertTrue(any("input_tokens" in d and "output_tokens" in d for d in report["diagnostics"]))

    def test_rate_windows_and_thread_segments_are_explicit(self):
        files = {
            "rollout-root.jsonl": [
                self.meta("root", "root", "2026-09-25T12:00:00Z"),
                {"type": "event_msg", "payload": {"type": "token_count", "info": None,
                 "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 60,
                                                  "resets_at": 100},
                                 "secondary": {"used_percent": 40, "window_minutes": 1440,
                                                "resets_at": 1000}, "limit_id": "first"}}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": None,
                 "rate_limits": {"primary": {"used_percent": 20, "window_minutes": 60,
                                                  "resets_at": 200},
                                 "secondary": {"used_percent": 45, "window_minutes": 1440,
                                                "resets_at": 1000}, "limit_id": "second"}}},
                self.usage(100),
            ],
            "rollout-child-a.jsonl": [self.meta("child", "root", "2026-09-25T12:01:00Z", child=True), self.usage(200)],
            "rollout-child-b.jsonl": [self.meta("child", "root", "2026-09-25T12:02:00Z", child=True), self.usage(300)],
        }
        report = self.run_fixture_report(files)
        self.assertEqual(report["thread_count"], 2)
        self.assertEqual(report["threads"][1]["segment_count"], 2)
        self.assertEqual(sum_usage(report), 600)
        rendered = self.render_fixture_markdown(files)
        self.assertIn("60m 10% -> 60m 20%", rendered)
        self.assertIn("1440m 40% -> 1440m 45%", rendered)
        self.assertIn("reset time changed", rendered)
        self.assertIn("limit identity changed", rendered)

    @staticmethod
    def meta(thread_id, root_id, timestamp, child=False):
        payload = {"id": thread_id, "session_id": root_id, "timestamp": timestamp, "source": "cli"}
        if child:
            payload["source"] = {"subagent": {"thread_spawn": {"agent_role": "worker"}}}
        return {"type": "session_meta", "payload": payload}

    @staticmethod
    def usage(total):
        return {"type": "token_usage_record", "payload": {"usage": {"input_tokens": total,
                "total_tokens": total}}}

    def run_fixture_report(self, files, date=None):
        with tempfile.TemporaryDirectory() as directory:
            for name, records in files.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
            args = ["--sessions-dir", directory, "--root", "root", "--format", "json"]
            if date:
                args.extend(("--date", date))
            result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def render_fixture_markdown(self, files):
        with tempfile.TemporaryDirectory() as directory:
            for name, records in files.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--sessions-dir", directory, "--root", "root"],
                                    capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


def sum_usage(report):
    return sum(t["per_model"][model]["total_tokens"] for t in report["threads"]
               for model in t["per_model"])


if __name__ == "__main__":
    unittest.main()
