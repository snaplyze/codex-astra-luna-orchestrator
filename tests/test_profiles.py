import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "pro": {
        "root": ("gpt-6-astra", "medium"),
        "default": ("gpt-6-luna", "high"),
        "roles": {
            "explorer": ("gpt-6-luna", "high", "read-only"),
            "researcher": ("gpt-6-luna", "high", "read-only"),
            "worker": ("gpt-6-sol", "medium", "workspace-write"),
            "tester": ("gpt-6-sol", "medium", "workspace-write"),
            "reviewer": ("gpt-6-astra", "low", "read-only"),
        },
    },
    "plus": {
        "root": ("gpt-6-luna", "max"),
        "default": ("gpt-6-luna", "high"),
        "roles": {
            "explorer": ("gpt-6-luna", "high", "read-only"),
            "researcher": ("gpt-6-luna", "high", "read-only"),
            "worker": ("gpt-6-luna", "high", "workspace-write"),
            "tester": ("gpt-6-luna", "high", "workspace-write"),
            "reviewer": ("gpt-6-astra", "low", "read-only"),
        },
    },
}


class ProfileTopologyTests(unittest.TestCase):
    def test_profiles_share_the_same_orchestration_policy(self) -> None:
        reference = (ROOT / "profiles/pro/agents/skills/codex-orchestrator/SKILL.md").read_bytes()
        for profile in (ROOT / "profiles").iterdir():
            with self.subTest(profile=profile.name):
                self.assertEqual(
                    (profile / "agents/skills/codex-orchestrator/SKILL.md").read_bytes(),
                    reference,
                    "Shared routing policy must stay consistent across profiles",
                )

    def test_profiles_ship_one_skill_with_matching_identity(self) -> None:
        for profile in (ROOT / "profiles").iterdir():
            with self.subTest(profile=profile.name):
                skills = profile / "agents" / "skills"
                skill_files = list(skills.glob("*/SKILL.md"))
                self.assertEqual(
                    [path.parent.name for path in skill_files],
                    ["codex-orchestrator"],
                )
                frontmatter = skill_files[0].read_text().split("---", 2)[1]
                self.assertIn("name: codex-orchestrator", frontmatter.splitlines())

    def test_all_role_files_have_exact_topology(self) -> None:
        for base_name, expected in EXPECTED.items():
            for profile_name in (base_name, f"{base_name}-max-2-subagents"):
                with self.subTest(profile=profile_name):
                    profile = ROOT / "profiles" / profile_name
                    config = tomllib.loads((profile / "codex" / "config.toml").read_text())
                    self.assertEqual(
                        (config["model"], config["model_reasoning_effort"]),
                        expected["root"],
                    )
                    self.assertTrue(config["agents"]["enabled"])
                    self.assertEqual(config["approval_policy"], "on-request")
                    self.assertEqual(config["sandbox_mode"], "workspace-write")
                    self.assertEqual(
                        (
                            config["agents"]["default_subagent_model"],
                            config["agents"]["default_subagent_reasoning_effort"],
                        ),
                        expected["default"],
                    )

                    role_files = sorted((profile / "codex" / "agents").glob("*.toml"))
                    self.assertEqual({path.stem for path in role_files}, set(expected["roles"]))
                    for role_file in role_files:
                        role = role_file.stem
                        data = tomllib.loads(role_file.read_text())
                        self.assertEqual(data["name"], role)
                        self.assertEqual(
                            (data["model"], data["model_reasoning_effort"], data["sandbox_mode"]),
                            expected["roles"][role],
                        )

    def test_max_two_profiles_differ_only_in_concurrency(self) -> None:
        for base_name in EXPECTED:
            with self.subTest(profile_pair=base_name):
                base = ROOT / "profiles" / base_name
                limited = ROOT / "profiles" / f"{base_name}-max-2-subagents"
                base_config = tomllib.loads((base / "codex" / "config.toml").read_text())
                limited_config = tomllib.loads((limited / "codex" / "config.toml").read_text())
                self.assertEqual(
                    {key: value for key, value in limited_config.items() if key != "agents"},
                    {key: value for key, value in base_config.items() if key != "agents"},
                )
                limited_agents = dict(limited_config["agents"])
                base_agents = dict(base_config["agents"])
                limited_agents.pop("max_concurrent_threads_per_session")
                base_agents.pop("max_concurrent_threads_per_session")
                self.assertEqual(limited_agents, base_agents)
                for role in EXPECTED[base_name]["roles"]:
                    self.assertEqual(
                        (limited / "codex" / "agents" / f"{role}.toml").read_bytes(),
                        (base / "codex" / "agents" / f"{role}.toml").read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main()
