import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_plan_and_build_requires_proportional_design_approval(self) -> None:
        skill = self.read("skills/plan-and-build/SKILL.md")
        self.assertIn("Design approval checkpoint", skill)
        self.assertIn("wait for explicit user approval", skill)
        self.assertIn("does not need to be asked again", skill)

    def test_web_parallel_dispatch_requires_approval_before_workers(self) -> None:
        skill = self.read("skills/web-parallel-dispatch/SKILL.md")
        approval = skill.index("wait for explicit user approval")
        dispatch = skill.index("Dispatch in parallel")
        self.assertLess(approval, dispatch)

    def test_systematic_debugging_has_no_template_placeholders(self) -> None:
        skill = self.read("skills/systematic-debugging/SKILL.md")
        self.assertNotIn("TODO", skill)
        self.assertIn("do not edit production code until", skill)
        self.assertIn("Confirm the root cause", skill)
        self.assertIn("Add regression protection", skill)

    def test_systematic_debugging_is_registered_for_install_and_uninstall(self) -> None:
        catalog = self.read("components.json")
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")
        self.assertIn('"name": "systematic-debugging"', catalog)
        self.assertIn("catalog_names skill claude", install)
        self.assertIn("catalog_names skill codex", install)
        self.assertIn("catalog_names skill claude", uninstall)
        self.assertIn("catalog_names skill codex", uninstall)

    def test_windows_supported_complex_skills_include_concrete_powershell(self) -> None:
        branch_review = self.read("skills/branch-merge-review/SKILL.md")
        codex_delegate = self.read("skills/codex-delegate/SKILL.md")
        for expected in (
            "```powershell", "try {", "finally {", "Select-String",
            "SqlInjection", "Csrf", "Secrets", "BackendQuality",
        ):
            self.assertIn(expected, branch_review)
        for expected in (
            "```powershell", "$env:TEMP", "Start-Process", "Wait-Process",
            "try {", "finally {", "[version]$numericPrefix",
        ):
            self.assertIn(expected, codex_delegate)

    def test_evidence_first_review_defines_modes_and_read_only_contract(self) -> None:
        skill = self.read("skills/evidence-first-review/SKILL.md")
        for mode in ("initial", "recheck", "final-approval"):
            self.assertIn(f"`{mode}`", skill)
        for status in ("resolved", "partially resolved", "unresolved", "regressed"):
            self.assertIn(f"`{status}`", skill)
        self.assertIn("branch-merge-review", skill)
        self.assertIn("Do not create or modify files", skill)
        self.assertIn("Do not install tools", skill)
        self.assertIn("Do not create checkouts or worktrees", skill)
        self.assertIn("Do not stage changes", skill)
        self.assertIn("message only", skill)

    def test_safe_checkpoint_requires_explicit_write_authority(self) -> None:
        skill = self.read("skills/safe-checkpoint/SKILL.md")
        self.assertIn("Do not infer write authority", skill)
        self.assertIn("Create or update a handoff document", skill)
        self.assertIn("Stage and commit", skill)
        self.assertIn("Push to a remote", skill)
        self.assertIn("failed WIP checkpoint", skill)
        self.assertIn("`wip:`", skill)
        self.assertIn(".tasks/handoffs/YYYY-MM-DD-{slug}.md", skill)
        self.assertIn("runtime manifests", skill)
        self.assertIn("upstream synchronization", skill)

    def test_new_skills_have_only_the_approved_files(self) -> None:
        expected = {
            "evidence-first-review": {
                "SKILL.md",
                "agents/openai.yaml",
                "references/report-format.md",
            },
            "safe-checkpoint": {
                "SKILL.md",
                "agents/openai.yaml",
                "references/handoff-template.md",
            },
        }
        for skill_name, expected_files in expected.items():
            with self.subTest(skill_name=skill_name):
                skill_dir = ROOT / "skills" / skill_name
                actual_files = {
                    str(path.relative_to(skill_dir))
                    for path in skill_dir.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(actual_files, expected_files)

    def test_new_skills_have_direct_default_prompts(self) -> None:
        for skill_name in ("evidence-first-review", "safe-checkpoint"):
            with self.subTest(skill_name=skill_name):
                metadata = self.read(f"skills/{skill_name}/agents/openai.yaml")
                self.assertIn(f"${skill_name}", metadata)

    def test_new_skills_are_registered_symmetrically(self) -> None:
        catalog = json.loads(self.read("components.json"))
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")

        for skill_name in ("evidence-first-review", "safe-checkpoint"):
            with self.subTest(skill_name=skill_name):
                matches = [
                    component
                    for component in catalog["components"]
                    if component["kind"] == "skill"
                    and component["name"] == skill_name
                ]
                self.assertEqual(len(matches), 1)
                component = matches[0]
                self.assertEqual(
                    component["source"],
                    f"skills/{skill_name}",
                )
                for client in ("claude", "codex"):
                    self.assertEqual(
                        component["support"][client],
                        {"posix": True, "windows": True},
                    )

        for script in (install, uninstall):
            self.assertIn("catalog_names skill claude", script)
            self.assertIn("catalog_names skill codex", script)


if __name__ == "__main__":
    unittest.main()
