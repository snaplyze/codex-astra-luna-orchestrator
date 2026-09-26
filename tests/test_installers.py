import os
import re
import shutil
import subprocess
import tempfile
import threading
import tomllib
import unittest
from queue import Queue
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = ROOT / "setup.sh"
SETUP_PS1 = ROOT / "setup.ps1"
MANAGED_BEGIN = "<!-- BEGIN codex-orchestrator:managed -->"
MANAGED_END = "<!-- END codex-orchestrator:managed -->"
LEGACY_MANAGED_BEGIN = "<!-- BEGIN codex-astra-luna-orchestrator:managed -->"
LEGACY_MANAGED_END = "<!-- END codex-astra-luna-orchestrator:managed -->"


class InstallerIntegrationTests(unittest.TestCase):
    def run_installer(
        self,
        target: Path,
        answers: list[str],
        env: dict[str, str] | None = None,
        installer_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        input_text = "\n".join([str(target), *answers]) + "\n"
        command = self.engine_command()
        if installer_path is not None:
            command[-1] = str(installer_path)
        return subprocess.run(
            command,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=self.engine_environment(env),
        )

    @classmethod
    def setUpClass(cls) -> None:
        engine = os.environ.get("CODEX_INSTALLER_TEST_ENGINE", "").lower()
        if engine not in {"", "sh", "pwsh", "powershell"}:
            raise ValueError(f"Unsupported installer test engine: {engine}")

    def is_shell_engine(self) -> bool:
        engine = os.environ.get("CODEX_INSTALLER_TEST_ENGINE", "").lower()
        return engine == "sh" or (not engine and os.name != "nt")

    def engine_environment(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        environment = {**os.environ, **(overrides or {})}
        if not self.is_shell_engine():
            # Python launched by PS7 otherwise passes PS7-only modules to WinPS.
            # Each test child must construct module paths for its own runtime.
            environment = {key: value for key, value in environment.items() if key.upper() != "PSMODULEPATH"}
        return environment

    def engine_command(self) -> list[str]:
        engine = os.environ.get("CODEX_INSTALLER_TEST_ENGINE", "").lower()
        executable = os.environ.get("CODEX_INSTALLER_TEST_EXECUTABLE")
        if engine in {"pwsh", "powershell"} or (not engine and os.name == "nt"):
            shell = executable or ("pwsh" if engine == "pwsh" else None)
            shell = shell or (shutil.which("pwsh") if engine != "powershell" else None)
            shell = shell or (shutil.which("powershell") if engine != "pwsh" else None)
            if shell is None:
                if engine:
                    raise RuntimeError(f"Requested PowerShell engine is unavailable: {engine}")
                self.skipTest("PowerShell is unavailable")
            return [shell, "-NoProfile", "-NonInteractive", "-File", str(SETUP_PS1)]
        return [executable or "sh", str(SETUP_SH)]

    def start_until_prompt(self, target: Path, answers: list[str], prompt: str):
        process = subprocess.Popen(
            self.engine_command(),
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            env=self.engine_environment(),
        )
        assert process.stdin is not None and process.stdout is not None
        output: Queue[str] = Queue()

        def collect_output() -> None:
            assert process.stdout is not None
            while chunk := process.stdout.read(1):
                output.put(chunk)

        reader = threading.Thread(target=collect_output, daemon=True)
        reader.start()
        process.stdin.write("\n".join([str(target), *answers]) + "\n")
        seen = ""
        while prompt not in seen:
            try:
                seen += output.get(timeout=10)
            except Exception:
                process.kill()
                process.wait(timeout=10)
                self.fail(f"installer did not reach synchronization prompt {prompt!r}; output={seen!r}")
        return process, reader, output, seen

    def finish_interactive(self, process, reader, output: Queue[str], seen: str, answer: str = ""):
        assert process.stdin is not None
        if answer:
            process.stdin.write(answer)
        process.stdin.close()
        return_code = process.wait(timeout=10)
        stderr = process.stderr.read() if process.stderr else ""
        reader.join(timeout=2)
        while not output.empty():
            seen += output.get_nowait()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
        return subprocess.CompletedProcess(process.args, return_code, seen, stderr)

    def make_fault_injector(self, directory: Path, mode: str) -> tuple[dict[str, str], Path | None, Path | None]:
        engine = os.environ.get("CODEX_INSTALLER_TEST_ENGINE", "").lower()
        marker = directory / "fault-injected.marker"
        if engine == "sh" or (not engine and os.name != "nt"):
            executable_root = Path.home() / ".cache" / "codex-orchestrator-audit-tools" / "test-tmp"
            executable_root.mkdir(parents=True, exist_ok=True)
            injection_directory = Path(tempfile.mkdtemp(prefix="installer-fault-", dir=executable_root))
            fake_bin = injection_directory / "bin"
            fake_bin.mkdir()
            real_mv = shutil.which("mv")
            self.assertIsNotNone(real_mv)
            shim = fake_bin / "mv"
            shim.write_text(
                "#!/bin/sh\n"
                "last=\n"
                "for argument do last=$argument; done\n"
                f"case \"{mode}:$*:$last\" in\n"
                f"  write:*codex-orchestrator-install*:*researcher.toml) : > '{marker}'; exit 42 ;;\n"
                f"  restore:*codex-orchestrator-rollback*:*config.toml) : > '{marker}'; exit 43 ;;\n"
                "esac\n"
                f"exec {real_mv!s} \"$@\"\n"
            )
            shim.chmod(0o755)
            return {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}, None, injection_directory

        launcher = directory / "fault-launcher.ps1"
        setup_path = str(SETUP_PS1).replace("'", "''")
        marker_path = str(marker).replace("'", "''")
        launcher.write_text(
            "$global:realCopyItem = Get-Command Copy-Item -CommandType Cmdlet\n"
            "function global:Copy-Item {\n"
            "  [CmdletBinding()] param([string]$LiteralPath,[string]$Path,[string]$Destination,[switch]$Force,[switch]$Recurse)\n"
                f"  if ((($env:CODEX_TEST_FAULT_MODE -eq 'write') -and ($LiteralPath -like '*researcher.toml')) -or (($env:CODEX_TEST_FAULT_MODE -eq 'restore') -and ($Destination -like '*rollback-*'))) {{\n"
            f"    [IO.File]::WriteAllText('{marker_path}', 'injected')\n"
            "    throw 'Injected installer file operation failure'\n"
            "  }\n"
            "  Microsoft.PowerShell.Management\\Copy-Item @PSBoundParameters\n"
            "}\n"
            f"& '{setup_path}'\n"
            "exit $LASTEXITCODE\n"
        )
        return {"CODEX_TEST_FAULT_MODE": mode}, launcher, None

    def test_new_agents_file_contains_only_managed_client_instructions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            result = self.run_installer(target, ["1", "n", "n", "y"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            installed = (target / "AGENTS.md").read_text()
            source = (ROOT / "AGENTS.md").read_text()
            managed = source.split(MANAGED_BEGIN, 1)[1].split(MANAGED_END, 1)[0]
            self.assertEqual(installed, f"{MANAGED_BEGIN}{managed}{MANAGED_END}\n")
            self.assertNotIn("Maintaining this source repository", installed)

    @unittest.skipUnless(hasattr(os, "link"), "hard links unavailable")
    def test_hardlinked_config_replacement_does_not_change_external_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            codex = target / ".codex"
            shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
            config = codex / "config.toml"
            config.write_text("external sentinel\n")
            external = Path(directory) / "external.toml"
            os.link(config, external)

            result = self.run_installer(target, ["1", "y", "y", "n", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(external.read_text(), "external sentinel\n")
            self.assertEqual(config.read_bytes(), (ROOT / "profiles" / "pro" / "codex" / "config.toml").read_bytes())

    def test_cancelled_update_preserves_unrelated_concurrent_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            codex = target / ".codex"
            shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
            config = codex / "config.toml"
            config.write_text("old managed config\n")
            process = subprocess.Popen(
                self.engine_command(),
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
                env=self.engine_environment(),
            )
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            output: Queue[str] = Queue()

            def collect_output() -> None:
                assert process.stdout is not None
                while chunk := process.stdout.read(1):
                    output.put(chunk)

            reader = threading.Thread(target=collect_output, daemon=True)
            reader.start()
            process.stdin.write(f"{target}\n1\ny\ny\n")
            seen = ""
            while "Install .agents?" not in seen:
                try:
                    seen += output.get(timeout=10)
                except Exception:
                    process.kill()
                    self.fail(f"installer did not reach synchronization prompt; output={seen!r}")

            config.write_text("concurrent managed edit\n")
            (codex / "concurrent.txt").write_text("concurrent new file\n")
            process.stdin.close()
            return_code = process.wait(timeout=10)
            stderr = process.stderr.read() if process.stderr else ""
            reader.join(timeout=2)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

            self.assertNotEqual(return_code, 0, seen + stderr)
            self.assertEqual(config.read_text(), "concurrent managed edit\n")
            self.assertEqual((codex / "concurrent.txt").read_text(), "concurrent new file\n")
            self.assertIn("concurrent change", stderr.lower())
            self.assertIn("retained", stderr.lower())

    def test_cancelled_fresh_install_removes_only_installer_created_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            result = self.run_installer(target, ["1", "y"])

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / ".codex").exists())
            self.assertFalse((target / ".agents").exists())
            self.assertFalse((target / "AGENTS.md").exists())

    @unittest.skipUnless(hasattr(os, "link"), "hard links unavailable")
    def test_hardlinked_agents_replacement_does_not_change_external_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            source = (ROOT / "AGENTS.md").read_text()
            stale = source.replace("adaptive routing", "outdated routing")
            agents = target / "AGENTS.md"
            agents.write_text(stale)
            external = Path(directory) / "external-agents.md"
            os.link(agents, external)

            result = self.run_installer(target, ["1", "n", "n", "y", "y"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(external.read_text(), stale)
            self.assertNotIn("outdated routing", agents.read_text())

    def test_deleted_managed_output_is_preserved_as_a_rollback_conflict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            codex = target / ".codex"
            shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
            config = codex / "config.toml"
            config.write_text("old managed config\n")
            process, reader, output, seen = self.start_until_prompt(target, ["1", "y", "y"], "Install .agents?")
            config.unlink()
            result = self.finish_interactive(process, reader, output, seen)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(config.exists())
            self.assertIn("concurrent change", result.stderr.lower())
            recovery = re.search(r"recovery copies are in (.+)\.", result.stderr)
            self.assertIsNotNone(recovery, result.stderr)
            self.assertEqual((Path(recovery.group(1)) / "before").read_text(), "old managed config\n")

    def test_agents_edit_while_update_prompt_is_open_aborts_without_losing_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            source = (ROOT / "AGENTS.md").read_text()
            initial = "User instructions\n\n" + source.replace("adaptive routing", "outdated routing")
            agents = target / "AGENTS.md"
            agents.write_text(initial)
            process, reader, output, seen = self.start_until_prompt(
                target, ["1", "n", "n", "y"], "Update the managed instructions in AGENTS.md?"
            )
            concurrent = initial.replace("User instructions", "Concurrent user instructions")
            agents.write_text(concurrent)
            result = self.finish_interactive(process, reader, output, seen, "y\n")

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(agents.read_text(), concurrent)
            self.assertIn("changed while setup was waiting", result.stderr)

    def test_legacy_rollback_does_not_follow_concurrent_skills_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents_dir = target / ".agents"
            shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
            (agents_dir / "skills" / "codex-orchestrator").rename(agents_dir / "skills" / "astra-orchestrator")
            (agents_dir / "skills" / "astra-orchestrator" / "SKILL.md").write_text("legacy user skill\n")
            legacy_agents = (ROOT / "AGENTS.md").read_text()
            (target / "AGENTS.md").write_text(
                legacy_agents.replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                .replace(MANAGED_END, LEGACY_MANAGED_END)
                .replace("codex-orchestrator", "astra-orchestrator")
            )
            external_skills = Path(directory) / "external skills"
            external_skill = external_skills / "codex-orchestrator"
            external_skill.mkdir(parents=True)
            process, reader, output, seen = self.start_until_prompt(target, ["1", "n", "y", "y"], "Install AGENTS.md?")
            original_skills = agents_dir / "original-skills"
            (agents_dir / "skills").rename(original_skills)
            try:
                (agents_dir / "skills").symlink_to(external_skills, target_is_directory=True)
            except OSError as exc:
                process.kill()
                process.wait(timeout=10)
                self.skipTest(f"symbolic links unavailable: {exc}")
            result = self.finish_interactive(process, reader, output, seen)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(external_skill.is_dir())
            self.assertEqual(list(external_skill.iterdir()), [])
            self.assertFalse((external_skills / "astra-orchestrator").exists())
            self.assertIn("symbolic link", result.stderr.lower())

    def test_file_write_failure_rolls_back_prior_managed_replacements(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            fixture = Path(directory)
            target = self.make_target(directory)
            codex = target / ".codex"
            shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
            (codex / "config.toml").write_text("old config\n")
            (codex / "agents" / "explorer.toml").write_text("old explorer role\n")
            (codex / "user-owned.txt").write_text("user data\n")
            before = {path.relative_to(codex): path.read_bytes() for path in codex.rglob("*") if path.is_file()}
            env, launcher, injection_directory = self.make_fault_injector(fixture, "write")
            if injection_directory is not None:
                self.addCleanup(shutil.rmtree, injection_directory, ignore_errors=True)

            result = self.run_installer(target, ["1", "y", "y", "n", "n"], env=env, installer_path=launcher)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((fixture / "fault-injected.marker").is_file())
            after = {path.relative_to(codex): path.read_bytes() for path in codex.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_failed_file_restore_retains_before_image_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            fixture = Path(directory)
            target = self.make_target(directory)
            codex = target / ".codex"
            shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
            (codex / "config.toml").write_text("old config\n")
            (codex / "user-owned.txt").write_text("user data\n")
            env, launcher, injection_directory = self.make_fault_injector(fixture, "restore")
            if injection_directory is not None:
                self.addCleanup(shutil.rmtree, injection_directory, ignore_errors=True)

            result = self.run_installer(target, ["1", "y", "y"], env=env, installer_path=launcher)
            output = result.stdout + result.stderr

            self.assertNotEqual(result.returncode, 0, output)
            self.assertTrue((fixture / "fault-injected.marker").is_file())
            self.assertIn("rollback was incomplete", output.lower())
            retained = re.search(r"transaction backups were retained at (.+)", output)
            self.assertIsNotNone(retained, output)
            transaction = Path(retained.group(1).strip())
            config_entry = next(entry for entry in transaction.glob("entry-*") if (entry / "manifest.txt").read_text().splitlines()[0] == ".codex/config.toml")
            self.assertEqual((config_entry / "before").read_text(), "old config\n")
            self.assertIn(".codex/config.toml", (config_entry / "manifest.txt").read_text())
            self.assertEqual((codex / "user-owned.txt").read_text(), "user data\n")

    def make_target(self, directory: str) -> Path:
        target = Path(directory) / "target project"
        target.mkdir()
        return target

    def test_max_two_profile_is_installed_from_numeric_selection(self) -> None:
        for selection, model in (("3", "gpt-6-astra"), ("4", "gpt-6-luna")):
            with self.subTest(selection=selection):
                with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
                    target = self.make_target(directory)
                    result = self.run_installer(target, [selection, "y", "y", "y"])

                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertTrue((target / ".codex" / "config.toml").is_file())
                    self.assertTrue((target / ".agents" / "skills" / "codex-orchestrator" / "SKILL.md").is_file())
                    config = (target / ".codex" / "config.toml").read_text()
                    self.assertIn("max_concurrent_threads_per_session = 2", config)
                    self.assertIn(f'model = "{model}"', config)

    def test_all_profiles_install_complete_profile_output(self) -> None:
        selections = {
            "1": "pro",
            "2": "plus",
            "3": "pro-max-2-subagents",
            "4": "plus-max-2-subagents",
        }
        for selection, profile_name in selections.items():
            with self.subTest(profile=profile_name):
                with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
                    target = self.make_target(directory)
                    result = self.run_installer(target, [selection, "y", "y", "y"])

                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    profile = ROOT / "profiles" / profile_name
                    for component, source_component in ((".codex", "codex"), (".agents", "agents")):
                        expected_files = {
                            path.relative_to(profile / source_component)
                            for path in (profile / source_component).rglob("*")
                            if path.is_file()
                        }
                        installed_files = {
                            path.relative_to(target / component)
                            for path in (target / component).rglob("*")
                            if path.is_file()
                        }
                        self.assertEqual(installed_files, expected_files)
                        for relative_path in expected_files:
                            self.assertEqual(
                                (target / component / relative_path).read_bytes(),
                                (profile / source_component / relative_path).read_bytes(),
                            )
                    self.assertIn(MANAGED_BEGIN, (target / "AGENTS.md").read_text())
                    self.assertIn(MANAGED_END, (target / "AGENTS.md").read_text())

    def test_upgrade_from_old_pinned_model_preserves_unrelated_files(self) -> None:
        for selection, profile_name in (("2", "plus"), ("1", "pro")):
            with self.subTest(profile=profile_name):
                with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
                    target = self.make_target(directory)
                    codex = target / ".codex"
                    agents = target / ".agents"
                    shutil.copytree(ROOT / "profiles" / "plus" / "codex", codex)
                    shutil.copytree(ROOT / "profiles" / "plus" / "agents", agents)
                    for path in codex.rglob("*.toml"):
                        content = path.read_text()
                        content = content.replace("gpt-6-luna", "gpt-5.6-luna")
                        content = content.replace('model_reasoning_effort = "high"', 'model_reasoning_effort = "medium"')
                        path.write_text(content)
                    legacy_skill_dir = agents / "skills" / "codex-orchestrator"
                    legacy_skill_dir.rename(agents / "skills" / "astra-orchestrator")
                    (agents / "skills" / "astra-orchestrator" / "SKILL.md").write_text("custom legacy skill\n")
                    (codex / "user-owned.toml").write_text("user-owned codex\n")
                    (agents / "user-owned.txt").write_text("user-owned agents\n")
                    (target / "keep.txt").write_text("keep\n")

                    agents_file = target / "AGENTS.md"
                    shutil.copy(ROOT / "AGENTS.md", agents_file)
                    legacy_instructions = (
                        agents_file.read_text()
                        .replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                        .replace(MANAGED_END, LEGACY_MANAGED_END)
                        .replace("codex-orchestrator", "astra-orchestrator")
                    )
                    agents_file.write_bytes(legacy_instructions.replace("\n", "\r\n").encode())

                    result = self.run_installer(target, [selection, "y", "y", "y", "y", "y", "y"])
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

                    profile = ROOT / "profiles" / profile_name
                    for component, source_component in ((codex, "codex"), (agents, "agents")):
                        expected_files = {
                            path.relative_to(profile / source_component)
                            for path in (profile / source_component).rglob("*")
                            if path.is_file()
                        }
                        for relative_path in expected_files:
                            self.assertEqual(
                                (component / relative_path).read_bytes(),
                                (profile / source_component / relative_path).read_bytes(),
                            )
                    self.assertEqual((codex / "user-owned.toml").read_text(), "user-owned codex\n")
                    self.assertEqual((agents / "user-owned.txt").read_text(), "user-owned agents\n")
                    archived = agents / "migration-backups" / "astra-orchestrator" / "SKILL.md"
                    self.assertEqual(archived.read_text(), "custom legacy skill\n")
                    self.assertFalse((agents / "skills" / "astra-orchestrator").exists())
                    migrated_agents = agents_file.read_bytes()
                    self.assertIn(MANAGED_BEGIN.encode(), migrated_agents)
                    self.assertNotIn(b"\n", migrated_agents.replace(b"\r\n", b""))
                    repeated = self.run_installer(target, [selection, "n", "n", "y"])
                    self.assertEqual(repeated.returncode, 0, repeated.stderr + repeated.stdout)
                    self.assertEqual(agents_file.read_bytes(), migrated_agents)
                    self.assertEqual((target / "keep.txt").read_text(), "keep\n")

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

    def test_legacy_skill_migration_and_instruction_update_can_be_declined_independently(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents_dir = target / ".agents"
            shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
            (agents_dir / "skills" / "codex-orchestrator").rename(
                agents_dir / "skills" / "astra-orchestrator"
            )
            legacy_skill = agents_dir / "skills" / "astra-orchestrator" / "SKILL.md"
            legacy_skill.write_text("custom legacy skill\n")
            agents_file = target / "AGENTS.md"
            agents_file.write_text(
                (ROOT / "AGENTS.md").read_text()
                .replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                .replace(MANAGED_END, LEGACY_MANAGED_END)
                .replace("codex-orchestrator", "astra-orchestrator")
            )
            original_agents = agents_file.read_bytes()
            original_skill = legacy_skill.read_bytes()

            result = self.run_installer(target, ["1", "n", "y", "n", "y", "n"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(agents_file.read_bytes(), original_agents)
            self.assertEqual(legacy_skill.read_bytes(), original_skill)
            self.assertFalse((agents_dir / "migration-backups").exists())
            self.assertFalse((agents_dir / "skills" / "codex-orchestrator").exists())

    def test_skill_archive_collision_uses_numeric_suffix_and_warns_if_agents_declined(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents_dir = target / ".agents"
            shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
            (agents_dir / "skills" / "codex-orchestrator").rename(
                agents_dir / "skills" / "astra-orchestrator"
            )
            legacy_skill = agents_dir / "skills" / "astra-orchestrator" / "SKILL.md"
            legacy_skill.write_text("custom legacy skill\n")
            occupied_archive = agents_dir / "migration-backups" / "astra-orchestrator"
            occupied_archive.mkdir(parents=True)
            (occupied_archive / "keep.txt").write_text("existing archive\n")
            agents_file = target / "AGENTS.md"
            agents_file.write_text(
                (ROOT / "AGENTS.md").read_text()
                .replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                .replace(MANAGED_END, LEGACY_MANAGED_END)
                .replace("codex-orchestrator", "astra-orchestrator")
            )

            result = self.run_installer(target, ["1", "n", "y", "y", "y", "n"])
            output = result.stdout + result.stderr

            self.assertEqual(result.returncode, 0, output)
            archived = agents_dir / "migration-backups" / "astra-orchestrator.1" / "SKILL.md"
            self.assertEqual(archived.read_text(), "custom legacy skill\n")
            self.assertEqual((occupied_archive / "keep.txt").read_text(), "existing archive\n")
            self.assertFalse((agents_dir / "skills" / "astra-orchestrator").exists())
            self.assertIn("legacy", output.lower())
            self.assertIn("AGENTS.md", output)
            self.assertIn("astra-orchestrator.1", output)

    def test_agents_can_migrate_while_declined_skill_update_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents_dir = target / ".agents"
            shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
            (agents_dir / "skills" / "codex-orchestrator").rename(
                agents_dir / "skills" / "astra-orchestrator"
            )
            agents_file = target / "AGENTS.md"
            agents_file.write_text(
                (ROOT / "AGENTS.md").read_text()
                .replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                .replace(MANAGED_END, LEGACY_MANAGED_END)
                .replace("codex-orchestrator", "astra-orchestrator")
            )

            result = self.run_installer(target, ["1", "n", "n", "y", "y"])
            output = result.stdout + result.stderr

            self.assertEqual(result.returncode, 0, output)
            self.assertIn(MANAGED_BEGIN, agents_file.read_text())
            self.assertTrue((agents_dir / "skills" / "astra-orchestrator" / "SKILL.md").is_file())
            self.assertFalse((agents_dir / "skills" / "codex-orchestrator").exists())
            self.assertIn("skill", output.lower())
            self.assertIn(".agents", output)

    def test_malformed_legacy_and_mixed_marker_pairs_fail_atomically(self) -> None:
        malformed_contents = {
            "mixed": f"{LEGACY_MANAGED_BEGIN}\nlegacy\n{MANAGED_END}\n",
            "duplicate": (
                f"{LEGACY_MANAGED_BEGIN}\none\n{LEGACY_MANAGED_END}\n"
                f"{LEGACY_MANAGED_BEGIN}\ntwo\n{LEGACY_MANAGED_END}\n"
            ),
            "reversed": f"{LEGACY_MANAGED_END}\nlegacy\n{LEGACY_MANAGED_BEGIN}\n",
        }
        for case, original in malformed_contents.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
                target = self.make_target(directory)
                agents_dir = target / ".agents"
                shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
                (agents_dir / "skills" / "codex-orchestrator").rename(
                    agents_dir / "skills" / "astra-orchestrator"
                )
                legacy_skill = agents_dir / "skills" / "astra-orchestrator" / "SKILL.md"
                legacy_skill.write_text("legacy skill\n")
                agents_file = target / "AGENTS.md"
                agents_file.write_text(original)

                result = self.run_installer(target, ["1", "n", "y", "y", "y"])

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(agents_file.read_text(), original)
                self.assertEqual(legacy_skill.read_text(), "legacy skill\n")
                self.assertFalse((agents_dir / "migration-backups").exists())
                self.assertFalse((agents_dir / "skills" / "codex-orchestrator").exists())

    def test_failed_agents_update_rolls_back_archived_legacy_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex installer ") as directory:
            target = self.make_target(directory)
            agents_dir = target / ".agents"
            shutil.copytree(ROOT / "profiles" / "pro" / "agents", agents_dir)
            (agents_dir / "skills" / "codex-orchestrator").rename(
                agents_dir / "skills" / "astra-orchestrator"
            )
            legacy_skill = agents_dir / "skills" / "astra-orchestrator" / "SKILL.md"
            legacy_skill.write_text("custom legacy skill\n")
            original_agents = (ROOT / "AGENTS.md").read_text()
            (target / "AGENTS.md").write_text(
                original_agents
                .replace(MANAGED_BEGIN, LEGACY_MANAGED_BEGIN)
                .replace(MANAGED_END, LEGACY_MANAGED_END)
                .replace("codex-orchestrator", "astra-orchestrator")
            )
            original_agents = (target / "AGENTS.md").read_bytes()
            original_tree = {
                path.relative_to(agents_dir): path.read_bytes()
                for path in agents_dir.rglob("*")
                if path.is_file()
            }
            result = self.run_installer(target, ["1", "n", "y", "y", "y"])

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "AGENTS.md").read_bytes(), original_agents)
            restored_tree = {
                path.relative_to(agents_dir): path.read_bytes()
                for path in agents_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(restored_tree, original_tree)
            self.assertFalse((agents_dir / "migration-backups").exists())

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
                self.assertTrue((profile / "agents" / "skills" / "codex-orchestrator" / "SKILL.md").is_file())

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
                    (limited / "agents" / "skills" / "codex-orchestrator" / "SKILL.md").read_bytes(),
                    (base / "agents" / "skills" / "codex-orchestrator" / "SKILL.md").read_bytes(),
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

if __name__ == "__main__":
    unittest.main()
