import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = ROOT / "setup.sh"
SETUP_PS1 = ROOT / "setup.ps1"
MANAGED_BEGIN = "<!-- BEGIN codex-astra-luna-orchestrator:managed -->"
MANAGED_END = "<!-- END codex-astra-luna-orchestrator:managed -->"


class InstallerIntegrationTests(unittest.TestCase):
    def run_installer(
        self,
        target: Path,
        answers: list[str],
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        input_text = "\n".join([str(target), *answers]) + "\n"
        if os.name == "nt":
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if shell is None:
                self.skipTest("PowerShell is unavailable")
            command = [shell, "-NoProfile", "-NonInteractive", "-File", str(SETUP_PS1)]
        else:
            command = ["sh", str(SETUP_SH)]
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            command,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=process_env,
        )

    def make_target(self, directory: str) -> Path:
        target = Path(directory) / "target project"
        target.mkdir()
        return target

    def test_max_two_profile_is_installed_from_numeric_selection(self) -> None:
        for selection, model in (("3", "gpt-6-astra"), ("4", "gpt-5.6-luna")):
            with self.subTest(selection=selection):
                with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
                    target = self.make_target(directory)
                    result = self.run_installer(target, [selection, "y", "y", "y"])

                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertTrue((target / ".codex" / "config.toml").is_file())
                    self.assertTrue((target / ".agents" / "skills" / "astra-orchestrator" / "SKILL.md").is_file())
                    config = (target / ".codex" / "config.toml").read_text()
                    self.assertIn("max_concurrent_threads_per_session = 2", config)
                    self.assertIn(f'model = "{model}"', config)

    def test_invalid_profile_does_not_touch_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            result = self.run_installer(target, ["not-a-profile"])

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / ".codex").exists())
            self.assertFalse((target / ".agents").exists())
            self.assertFalse((target / "AGENTS.md").exists())

    def test_unmanaged_agents_requires_update_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents = target / "AGENTS.md"
            original = "User-owned instructions\n"
            agents.write_text(original)

            result = self.run_installer(target, ["1", "n", "n", "y", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(agents.read_text(), original)

    def test_empty_agents_file_can_be_updated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents = target / "AGENTS.md"
            agents.write_text("")

            result = self.run_installer(target, ["1", "n", "n", "y", "y"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn(MANAGED_BEGIN, agents.read_text())
            self.assertIn(MANAGED_END, agents.read_text())

    def test_malformed_agents_marker_aborts_without_appending(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents = target / "AGENTS.md"
            original = f"User-owned instructions\n{MANAGED_END}\n"
            agents.write_text(original)

            result = self.run_installer(target, ["1", "n", "n", "y"])

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(agents.read_text(), original)
            self.assertFalse((target / ".codex").exists())
            self.assertFalse((target / ".agents").exists())

    def test_all_profiles_have_five_roles_and_expected_limits(self) -> None:
        expected_limits = {
            "pro": 4,
            "pro-max-2-subagents": 2,
            "plus": 4,
            "plus-max-2-subagents": 2,
        }
        for profile_name, expected_limit in expected_limits.items():
            with self.subTest(profile=profile_name):
                profile = ROOT / "profiles" / profile_name
                config = tomllib.loads((profile / "codex" / "config.toml").read_text())
                self.assertEqual(
                    config["agents"]["max_concurrent_threads_per_session"],
                    expected_limit,
                )
                self.assertEqual(len(list((profile / "codex" / "agents").glob("*.toml"))), 5)
                self.assertTrue((profile / "agents" / "skills" / "astra-orchestrator" / "SKILL.md").is_file())

        for base_name in ("pro", "plus"):
            with self.subTest(profile_pair=base_name):
                base = ROOT / "profiles" / base_name
                limited = ROOT / "profiles" / f"{base_name}-max-2-subagents"
                base_config = tomllib.loads((base / "codex" / "config.toml").read_text())
                limited_config = tomllib.loads((limited / "codex" / "config.toml").read_text())
                base_agents = dict(base_config["agents"])
                limited_agents = dict(limited_config["agents"])
                self.assertEqual(limited_config["model"], base_config["model"])
                self.assertEqual(limited_config["model_reasoning_effort"], base_config["model_reasoning_effort"])
                limited_agents["max_concurrent_threads_per_session"] = base_agents[
                    "max_concurrent_threads_per_session"
                ]
                self.assertEqual(limited_agents, base_agents)
                for role in ("explorer", "researcher", "reviewer", "tester", "worker"):
                    self.assertEqual(
                        (limited / "codex" / "agents" / f"{role}.toml").read_bytes(),
                        (base / "codex" / "agents" / f"{role}.toml").read_bytes(),
                    )
                self.assertEqual(
                    (limited / "agents" / "skills" / "astra-orchestrator" / "SKILL.md").read_bytes(),
                    (base / "agents" / "skills" / "astra-orchestrator" / "SKILL.md").read_bytes(),
                )

    def test_managed_agents_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            first = self.run_installer(target, ["1", "n", "n", "y"])
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            second = self.run_installer(target, ["1", "n", "n", "y"])
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            content = (target / "AGENTS.md").read_text()
            self.assertEqual(content.count(MANAGED_BEGIN), 1)
            self.assertEqual(content.count(MANAGED_END), 1)

    def test_managed_agents_are_line_ending_tolerant(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            first = self.run_installer(target, ["1", "n", "n", "y"])
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            agents = target / "AGENTS.md"
            agents.write_bytes(agents.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            second = self.run_installer(target, ["1", "n", "n", "y"])

            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            content = agents.read_bytes()
            self.assertEqual(content.count(MANAGED_BEGIN.encode()), 1)
            self.assertEqual(content.count(MANAGED_END.encode()), 1)

    def test_stale_managed_agents_requires_update_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            first = self.run_installer(target, ["1", "n", "n", "y"])
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            agents = target / "AGENTS.md"
            original = agents.read_text()
            agents.write_text(original.replace(
                "adaptive routing",
                "outdated routing",
            ))
            stale = agents.read_text()

            declined = self.run_installer(target, ["1", "n", "n", "y", "n"])
            self.assertEqual(declined.returncode, 0, declined.stderr + declined.stdout)
            self.assertEqual(agents.read_text(), stale)

            accepted = self.run_installer(target, ["1", "n", "n", "y", "y"])
            self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
            self.assertNotEqual(agents.read_text(), stale)
            self.assertEqual(agents.read_text().count(MANAGED_BEGIN), 1)
            self.assertEqual(agents.read_text().count(MANAGED_END), 1)

    def test_partial_component_installation_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            result = self.run_installer(target, ["1", "y", "n", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("partial", (result.stdout + result.stderr).lower())

    def test_existing_component_update_can_be_declined(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            custom = target / ".codex"
            custom.mkdir()
            (custom / "custom.txt").write_text("user-owned\n")

            result = self.run_installer(target, ["1", "y", "n", "n", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual((custom / "custom.txt").read_text(), "user-owned\n")
            self.assertFalse((custom / "config.toml").exists())

    def test_declined_profile_component_is_reported_as_partial(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            initial = self.run_installer(target, ["1", "y", "y", "y"])
            self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)

            result = self.run_installer(target, ["4", "y", "n", "y", "y", "y"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("partial", (result.stdout + result.stderr).lower())
            self.assertIn(
                "max_concurrent_threads_per_session = 4",
                (target / ".codex" / "config.toml").read_text(),
            )

    def test_incompatible_component_type_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            codex = target / ".codex"
            codex.write_text("user-owned\n")

            result = self.run_installer(target, ["1", "y", "n", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(codex.read_text(), "user-owned\n")
            self.assertIn("incompatible", (result.stdout + result.stderr).lower())

    def test_existing_symlink_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            linked = Path(directory) / "linked codex"
            linked.mkdir()
            link = target / ".codex"
            try:
                link.symlink_to(linked, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")

            result = self.run_installer(target, ["1", "y", "n", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(link.is_symlink())
            self.assertFalse((linked / "config.toml").exists())
            self.assertIn("symbolic link", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(os.name != "nt", "shell failure-injection test is POSIX-only")
    def test_failed_component_copy_rolls_back_prior_new_components(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            with tempfile.TemporaryDirectory(prefix=".codex fake bin ", dir=Path.home()) as fake_directory:
                fake_bin = Path(fake_directory)
                real_cp = shutil.which("cp")
                self.assertIsNotNone(real_cp)
                (fake_bin / "cp").write_text(
                    "#!/bin/sh\n"
                    "case \"$*\" in\n"
                    "  */.agents) exit 42 ;;\n"
                    "esac\n"
                    f"exec {real_cp!s} \"$@\"\n"
                )
                (fake_bin / "cp").chmod(0o755)
                env = {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

                result = self.run_installer(target, ["1", "y", "y"], env=env)

                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((target / ".codex").exists())
                self.assertFalse((target / ".agents").exists())
                self.assertFalse((target / "AGENTS.md").exists())
                self.assertIn("restoring", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(os.name != "nt", "shell failure-injection test is POSIX-only")
    def test_failed_restore_retains_transaction_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            codex = target / ".codex"
            codex.mkdir()
            (codex / "user-owned.txt").write_text("user-owned\n")
            with tempfile.TemporaryDirectory(prefix=".codex fake bin ", dir=Path.home()) as fake_directory:
                fake_bin = Path(fake_directory)
                real_cp = shutil.which("cp")
                self.assertIsNotNone(real_cp)
                (fake_bin / "cp").write_text(
                    "#!/bin/bash\n"
                    "last=\"${!#}\"\n"
                    "case \"$last\" in\n"
                    "  */.agents) exit 42 ;;\n"
                    "  */.codex|*/.codex/)\n"
                    "    case \"$*\" in *backup-.codex*) exit 43 ;; esac\n"
                    "    ;;\n"
                    "esac\n"
                    f"exec {real_cp!s} \"$@\"\n"
                )
                (fake_bin / "cp").chmod(0o755)
                env = {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

                result = self.run_installer(target, ["1", "y", "y", "y"], env=env)
                output = result.stdout + result.stderr

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("rollback was incomplete", output.lower())
                match = re.search(r"transaction backups were retained at (.+)", output)
                self.assertIsNotNone(match, output)
                backup_path = Path(match.group(1).strip())
                self.assertTrue(
                    (backup_path / "backup-.codex" / "user-owned.txt").is_file(),
                    f"backup path: {backup_path}; entries: {list(backup_path.parent.glob('codex-orchestrator-install.*'))}",
                )
                shutil.rmtree(backup_path)


if __name__ == "__main__":
    unittest.main()
