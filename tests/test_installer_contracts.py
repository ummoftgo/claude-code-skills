import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "components.json"
CATALOG_TOOL = ROOT / "scripts" / "catalog.py"
MANIFEST_TOOL = ROOT / "scripts" / "manifest.py"


class ComponentCatalogTest(unittest.TestCase):
    def test_catalog_matches_repository_components(self) -> None:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        components = data["components"]

        catalog_skills = {item["name"] for item in components if item["kind"] == "skill"}
        catalog_agents = {item["name"] for item in components if item["kind"] == "agent"}
        repository_skills = {path.name for path in (ROOT / "skills").iterdir() if path.is_dir()}
        repository_agents = {path.name for path in (ROOT / "agents").iterdir() if path.is_dir()}

        self.assertEqual(catalog_skills, repository_skills)
        self.assertEqual(catalog_agents, repository_agents)
        self.assertEqual(
            [item["name"] for item in components if item["kind"] == "hook"],
            ["workflow-reminder"],
        )

    def test_every_component_declares_four_support_cells(self) -> None:
        components = json.loads(CATALOG.read_text(encoding="utf-8"))["components"]
        for component in components:
            with self.subTest(component=component["name"]):
                self.assertEqual(set(component["support"]), {"claude", "codex"})
                for client in ("claude", "codex"):
                    self.assertEqual(
                        set(component["support"][client]), {"posix", "windows"}
                    )
                    self.assertTrue(
                        all(
                            isinstance(value, bool)
                            for value in component["support"][client].values()
                        )
                    )

    def test_all_installers_consume_the_catalog(self) -> None:
        for relative in ("install.sh", "uninstall.sh", "install.ps1", "uninstall.ps1"):
            with self.subTest(installer=relative):
                self.assertIn("components.json", (ROOT / relative).read_text(encoding="utf-8"))

    def test_codex_delegate_is_claude_only(self) -> None:
        components = json.loads(CATALOG.read_text(encoding="utf-8"))["components"]
        component = next(item for item in components if item["name"] == "codex-delegate")
        self.assertEqual(component["support"]["codex"], {"posix": False, "windows": False})

    def test_catalog_names_are_unique_and_every_source_exists(self) -> None:
        components = json.loads(CATALOG.read_text(encoding="utf-8"))["components"]
        keys = [(item["kind"], item["name"]) for item in components]
        self.assertEqual(len(keys), len(set(keys)))
        for component in components:
            source = component["source"]
            paths = [source] if isinstance(source, str) else list(source.values())
            for relative in paths:
                with self.subTest(component=component["name"], source=relative):
                    self.assertTrue((ROOT / relative).exists())

    def test_catalog_query_matches_every_support_cell(self) -> None:
        components = json.loads(CATALOG.read_text(encoding="utf-8"))["components"]
        for client in ("claude", "codex"):
            for platform in ("posix", "windows"):
                for kind in ("skill", "agent", "hook"):
                    expected = {
                        item["name"] for item in components
                        if item["kind"] == kind and item["support"][client][platform]
                    }
                    result = subprocess.run(
                        [sys.executable, str(CATALOG_TOOL), str(CATALOG),
                         "--kind", kind, "--client", client, "--platform", platform],
                        text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(set(result.stdout.splitlines()), expected)


class ManifestV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.manifest = self.root / "manifest.json"

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MANIFEST_TOOL), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_record_lookup_and_prune_round_trip(self) -> None:
        target = self.root / "target"
        result = self.run_tool(
            "record",
            "--manifest", str(self.manifest),
            "--platform", "windows",
            "--scope", "global",
            "--client", "claude",
            "--kind", "skill",
            "--component", "plan-and-build",
            "--target", str(target),
            "--method", "copy",
            "--source", str(ROOT / "skills" / "plan-and-build"),
            "--hash", "abc",
            "--config-before", "false",
            "--config-after", "true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["entries"][0]["platform"], "windows")
        self.assertEqual(data["entries"][0]["configuration"]["before"], False)

        lookup = self.run_tool("lookup", "--manifest", str(self.manifest), "--target", str(target))
        self.assertEqual(lookup.returncode, 0, lookup.stderr)
        self.assertEqual(json.loads(lookup.stdout)["component"], "plan-and-build")

        pruned = self.run_tool("prune", "--manifest", str(self.manifest), "--target", str(target))
        self.assertEqual(pruned.returncode, 0, pruned.stderr)
        self.assertFalse(self.manifest.exists())

    def test_v1_rows_are_imported_as_safe_posix_entries(self) -> None:
        target = self.root / "legacy skill"
        legacy = self.root / "manifest.tsv"
        legacy.write_text(
            "#claude-code-skills-manifest v1\n"
            f"codex-skill\t{target}\tcopy\t/repo/skills/example\tabc123\t2026-01-01T00:00:00Z\n",
            encoding="utf-8",
        )

        result = self.run_tool(
            "import-v1",
            "--manifest", str(self.manifest),
            "--legacy", str(legacy),
            "--scope", "global",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(self.manifest.read_text(encoding="utf-8"))["entries"][0]
        self.assertEqual(entry["platform"], "posix")
        self.assertEqual(entry["client"], "codex")
        self.assertEqual(entry["kind"], "skill")
        self.assertEqual(entry["method"], "copy")
        self.assertEqual(entry["hash"], "abc123")

    def test_record_replaces_only_same_target(self) -> None:
        targets = [self.root / "first", self.root / "second"]
        for target in targets:
            result = self.run_tool(
                "record", "--manifest", str(self.manifest),
                "--platform", "posix", "--scope", "project",
                "--client", "claude", "--kind", "skill",
                "--component", target.name, "--target", str(target),
                "--method", "copy", "--source", "/repo/source", "--hash", "one",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        result = self.run_tool(
            "record", "--manifest", str(self.manifest),
            "--platform", "posix", "--scope", "project",
            "--client", "claude", "--kind", "skill",
            "--component", "first", "--target", str(targets[0]),
            "--method", "copy", "--source", "/repo/source", "--hash", "two",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(self.manifest.read_text(encoding="utf-8"))["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(next(e for e in entries if e["target"] == str(targets[0]))["hash"], "two")


class PosixMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)

    def run_bash(self, body: str) -> subprocess.CompletedProcess[str]:
        command = f"""
source {ROOT / 'install.sh'}
HOME={self.home!s}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.home!s}
CODEX_SKILLS_DIR={self.home / '.agents' / 'skills'}
{body}
"""
        return subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)

    def test_owned_v1_copy_migrates_to_agents_skills(self) -> None:
        result = self.run_bash(
            r'''
old="$HOME/.codex/skills/local/plan-and-build"
mkdir -p "$old" "$HOME/.claude-code-skills"
printf 'legacy\n' > "$old/SKILL.md"
h="$(content_hash "$old")"
printf '#claude-code-skills-manifest v1\n' > "$HOME/.claude-code-skills/manifest.tsv"
printf 'codex-skill\t%s\tcopy\t%s\t%s\t2026-01-01T00:00:00Z\n' "$old" "$SKILLS_DIR/plan-and-build" "$h" >> "$HOME/.claude-code-skills/manifest.tsv"
set_manifest_path
migrate_legacy_codex_skills
test ! -e "$old"
test -f "$CODEX_SKILLS_DIR/plan-and-build/SKILL.md"
python3 "$MANIFEST_TOOL" lookup --manifest "$MANIFEST_FILE" --target "$CODEX_SKILLS_DIR/plan-and-build" >/dev/null
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_manifest_failure_preserves_legacy_and_removes_partial_copy(self) -> None:
        result = self.run_bash(
            r'''
old="$HOME/.codex/skills/local/plan-and-build"
mkdir -p "$old" "$HOME/.claude-code-skills"
printf 'legacy\n' > "$old/SKILL.md"
h="$(content_hash "$old")"
printf '#claude-code-skills-manifest v1\n' > "$HOME/.claude-code-skills/manifest.tsv"
printf 'codex-skill\t%s\tcopy\t%s\t%s\t2026-01-01T00:00:00Z\n' "$old" "$SKILLS_DIR/plan-and-build" "$h" >> "$HOME/.claude-code-skills/manifest.tsv"
set_manifest_path
manifest_record_required() { return 1; }
migrate_legacy_codex_skills
test -f "$old/SKILL.md"
test ! -e "$CODEX_SKILLS_DIR/plan-and-build"
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_copy_failure_preserves_legacy_and_removes_partial_copy(self) -> None:
        result = self.run_bash(
            r'''
old="$HOME/.codex/skills/local/plan-and-build"
mkdir -p "$old" "$HOME/.claude-code-skills"
printf 'legacy\n' > "$old/SKILL.md"
h="$(content_hash "$old")"
printf '#claude-code-skills-manifest v1\n' > "$HOME/.claude-code-skills/manifest.tsv"
printf 'codex-skill\t%s\tcopy\t%s\t%s\t2026-01-01T00:00:00Z\n' "$old" "$SKILLS_DIR/plan-and-build" "$h" >> "$HOME/.claude-code-skills/manifest.tsv"
set_manifest_path
cp() {
    local destination="${@: -1}"
    mkdir -p "$destination"
    printf 'partial\n' > "$destination/PARTIAL"
    return 1
}
set +e
migrate_legacy_codex_skills
set -e
test -f "$old/SKILL.md"
test ! -e "$CODEX_SKILLS_DIR/plan-and-build"
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


class PosixOwnershipBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.home = self.root

    def run_bash(self, body: str) -> subprocess.CompletedProcess[str]:
        command = f"""
source {ROOT / 'install.sh'}
HOME={self.home!s}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.home!s}
CODEX_SKILLS_DIR={self.home / '.agents' / 'skills'}
{body}
"""
        return subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)

    def test_install_never_overwrites_unverified_skill_even_after_yes_answers(self) -> None:
        target = self.root / ".claude" / "skills" / "plan-and-build"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("foreign\n", encoding="utf-8")
        command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.root}
CLAUDE_SKILLS_DIR={self.root / '.claude' / 'skills'}
SKILL_INSTALL_MODE=copy
set_manifest_path
ask_yn_default_no() {{ return 0; }}
install_skill plan-and-build "$CLAUDE_SKILLS_DIR"
test "$(cat {target / 'SKILL.md'})" = foreign
"""
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_uninstall_never_deletes_unverified_skill_even_after_yes_answers(self) -> None:
        target = self.root / ".claude" / "skills" / "plan-and-build"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("foreign\n", encoding="utf-8")
        command = f"""
source {ROOT / 'uninstall.sh'}
UNINSTALL_SCOPE=global
INSTALL_BASE_DIR={self.root}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 0; }}
remove_skill plan-and-build {target.parent}
test -f {target / 'SKILL.md'}
"""
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_install_preserves_foreign_regular_file_in_both_modes(self) -> None:
        for mode in ("copy", "symlink"):
            with self.subTest(mode=mode):
                target_root = self.root / mode / ".claude" / "skills"
                target_root.mkdir(parents=True)
                target = target_root / "plan-and-build"
                target.write_text("foreign\n", encoding="utf-8")
                command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.root / mode}
CLAUDE_SKILLS_DIR={target_root}
SKILL_INSTALL_MODE={mode}
set_manifest_path
install_skill plan-and-build "$CLAUDE_SKILLS_DIR"
test "$(cat {target})" = foreign
"""
                result = subprocess.run(
                    ["bash", "-c", command], text=True, capture_output=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_owned_reinstall_copy_failure_restores_previous_skill(self) -> None:
        target_root = self.root / ".claude" / "skills"
        target = target_root / "plan-and-build"
        command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.root}
CLAUDE_SKILLS_DIR={target_root}
SKILL_INSTALL_MODE=copy
mkdir -p "$CLAUDE_SKILLS_DIR"
set_manifest_path
install_skill plan-and-build "$CLAUDE_SKILLS_DIR"
old_hash="$(content_hash {target})"
cp() {{
    local destination="${{@: -1}}"
    mkdir -p "$destination"
    printf 'partial\n' > "$destination/PARTIAL"
    return 1
}}
set +e
install_skill plan-and-build "$CLAUDE_SKILLS_DIR"
set -e
test -f {target / 'SKILL.md'}
test ! -e {target / 'PARTIAL'}
test "$(content_hash {target})" = "$old_hash"
test "$(manifest_hash {target})" = "$old_hash"
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_owned_agent_copy_failure_restores_previous_file(self) -> None:
        target = self.root / ".claude" / "agents" / "security-auditor.md"
        command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=global
INSTALL_BASE_DIR={self.root}
set_manifest_path
src="$AGENTS_DIR/security-auditor/claude.md"
dst={target}
install_staged_component "$src" "$dst" copy claude-agent
old_hash="$(content_hash "$dst")"
cp() {{
    local destination="${{@: -1}}"
    printf 'partial\n' > "$destination"
    return 1
}}
set +e
install_staged_component "$src" "$dst" copy claude-agent
set -e
test -f "$dst"
test "$(content_hash "$dst")" = "$old_hash"
test "$(manifest_hash "$dst")" = "$old_hash"
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_modified_v1_copy_is_preserved(self) -> None:
        result = self.run_bash(
            r'''
old="$HOME/.codex/skills/local/plan-and-build"
mkdir -p "$old" "$HOME/.claude-code-skills"
printf 'modified\n' > "$old/SKILL.md"
printf '#claude-code-skills-manifest v1\n' > "$HOME/.claude-code-skills/manifest.tsv"
printf 'codex-skill\t%s\tcopy\t%s\twrong-hash\t2026-01-01T00:00:00Z\n' "$old" "$SKILLS_DIR/plan-and-build" >> "$HOME/.claude-code-skills/manifest.tsv"
set_manifest_path
migrate_legacy_codex_skills
test -f "$old/SKILL.md"
test ! -e "$CODEX_SKILLS_DIR/plan-and-build"
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_new_target_collision_preserves_legacy_item(self) -> None:
        result = self.run_bash(
            r'''
old="$HOME/.codex/skills/local/plan-and-build"
new="$CODEX_SKILLS_DIR/plan-and-build"
mkdir -p "$old" "$new"
printf 'legacy\n' > "$old/SKILL.md"
printf 'new\n' > "$new/SKILL.md"
set_manifest_path
migrate_legacy_codex_skills
test -f "$old/SKILL.md"
test "$(cat "$new/SKILL.md")" = new
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


class WindowsInstallerStaticContractTest(unittest.TestCase):
    def test_windows_paths_and_hook_commands_are_declared(self) -> None:
        common = (ROOT / "scripts" / "Installer.Common.psm1").read_text(encoding="utf-8")
        self.assertIn(".agents\\skills", common)
        self.assertIn("commandWindows", common)
        self.assertIn("powershell.exe", common)
        self.assertIn('"windows": "hooks/workflow-reminder.ps1"', CATALOG.read_text(encoding="utf-8"))

    def test_windows_powershell_51_hook_has_utf8_bom_and_console_encoding(self) -> None:
        hook_path = ROOT / "hooks" / "workflow-reminder.ps1"
        self.assertTrue(hook_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        hook = hook_path.read_text(encoding="utf-8-sig")
        self.assertIn("[Console]::InputEncoding", hook)
        self.assertIn("[Console]::OutputEncoding", hook)

    def test_windows_integration_runner_has_utf8_bom(self) -> None:
        runner = ROOT / "tests" / "windows" / "run-installer-tests.ps1"
        self.assertTrue(runner.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_windows_scripts_have_no_unattended_parameters(self) -> None:
        for relative in ("install.ps1", "uninstall.ps1"):
            script = (ROOT / relative).read_text(encoding="utf-8")
            executable = "\n".join(
                line for line in script.splitlines() if line.strip() and not line.lstrip().startswith("#")
            )
            self.assertNotRegex(executable, r"(?i)^\s*param\s*\(")

    def test_windows_project_paths_and_scope_match_contract(self) -> None:
        common = (ROOT / "scripts" / "Installer.Common.psm1").read_text(encoding="utf-8")
        install = (ROOT / "install.ps1").read_text(encoding="utf-8")
        for path in (".claude\\skills", ".claude\\agents", ".agents\\skills", ".codex\\agents"):
            self.assertIn(path, common)
        self.assertIn("Project scope installs skills and agents only", install)

    def test_installers_do_not_call_external_install_flows(self) -> None:
        install = (ROOT / "install.sh").read_text(encoding="utf-8")
        for function in (
            "install_php_tools",
            "install_ctx7",
            "install_codex",
            "install_codex_cc_plugin",
            "setup_context7_mcp",
            "install_agent_browser",
            "copy_cdp_script_to_desktop",
        ):
            self.assertNotIn(f"{function}() {{", install)
        windows = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("Show-DependencyDiagnostics", windows)

    def test_restart_and_hook_trust_guidance_are_state_driven(self) -> None:
        posix = (ROOT / "install.sh").read_text(encoding="utf-8")
        windows = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertNotIn('info "Claude Code를 재시작하면 스킬, 훅, 에이전트가 활성화됩니다."', posix)
        self.assertIn("CLAUDE_DIRECTORY_CREATED", posix)
        self.assertIn("$codexHookInstalled", windows)
        self.assertIn("if ($codexHookInstalled)", windows)

    def test_windows_integration_matrix_when_runtime_is_available(self) -> None:
        executable = shutil.which("powershell.exe") or shutil.which("pwsh")
        if executable is None:
            self.skipTest("Windows PowerShell runtime is not available")
        result = subprocess.run(
            [
                executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "tests" / "windows" / "run-installer-tests.ps1"),
            ],
            capture_output=True, check=False,
        )
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, output)


if __name__ == "__main__":
    unittest.main()
