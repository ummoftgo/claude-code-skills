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


if __name__ == "__main__":
    unittest.main()
