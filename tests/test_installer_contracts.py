import hashlib
import importlib.util
import json
import os
import shlex
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


class GlobalConfigPathTest(unittest.TestCase):
    def test_posix_entrypoints_reject_custom_roots_before_any_mutation(self) -> None:
        for script in ("install.sh", "uninstall.sh"):
            for variable in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
                with self.subTest(script=script, variable=variable), tempfile.TemporaryDirectory() as tmp:
                    home = Path(tmp)
                    marker = home / "mutation"
                    scope_function = "ask_install_scope" if script == "install.sh" else "ask_uninstall_scope"
                    scope_variable = "INSTALL_SCOPE" if script == "install.sh" else "UNINSTALL_SCOPE"
                    # The real main must reject before even importing a legacy manifest.
                    body = f"""
source {shlex.quote(str(ROOT / script))}
{scope_function}() {{ {scope_variable}=global; }}
set_manifest_path() {{ touch {shlex.quote(str(marker))}; exit 0; }}
main
"""
                    env = {**os.environ, "HOME": tmp, "CODEX_HOME": "", "CLAUDE_CONFIG_DIR": "", variable: str(home / "custom")}
                    done = subprocess.run(["bash", "-c", body], env=env, capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(done.returncode, 0)
                    self.assertIn(variable, done.stderr)
                    self.assertFalse(marker.exists(), "path guard ran after a mutation")

    def test_default_and_project_roots_reach_manifest_processing(self) -> None:
        for script in ("install.sh", "uninstall.sh"):
            for scope, mode in (("global", "unset"), ("global", "empty"), ("global", "default"), ("project", "custom")):
                with self.subTest(script=script, scope=scope, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    home = Path(tmp)
                    marker = home / "reached"
                    scope_function = "ask_install_scope" if script == "install.sh" else "ask_uninstall_scope"
                    scope_variable = "INSTALL_SCOPE" if script == "install.sh" else "UNINSTALL_SCOPE"
                    body = f"""
source {shlex.quote(str(ROOT / script))}
{scope_function}() {{ {scope_variable}={scope}; }}
set_manifest_path() {{ touch {shlex.quote(str(marker))}; exit 0; }}
main
"""
                    env = dict(os.environ, HOME=tmp)
                    for variable, directory in (("CODEX_HOME", ".codex"), ("CLAUDE_CONFIG_DIR", ".claude")):
                        env.pop(variable, None)
                        if mode == "empty":
                            env[variable] = ""
                        elif mode != "unset":
                            env[variable] = str(home / (directory if mode == "default" else "custom")) + "/"
                    done = subprocess.run(["bash", "-c", body], env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertTrue(marker.exists())


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
            [(item["name"], item["source"]) for item in components if item["kind"] == "rule"],
            [("code-writing", "rules/code-writing.md")],
        )
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
                for kind in ("skill", "agent", "hook", "rule"):
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


class PosixRuleTest(unittest.TestCase):
    start = b"<!-- claude-code-skills:code-writing -->\n"
    end = b"<!-- /claude-code-skills:code-writing -->\n"

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="rules home ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.agents = self.home / ".codex" / "AGENTS.md"
        self.claude = self.home / ".claude" / "rules" / "code-writing.md"
        self.manifest = self.home / ".claude-code-skills" / "manifest.json"
        self.env = dict(os.environ, HOME=str(self.home), CODEX_HOME="", CLAUDE_CONFIG_DIR="")

    def run_rules(self, action: str, scope: str = "global", answer: int = 0) -> subprocess.CompletedProcess[str]:
        installing = action == "install"
        body = f"""
source {shlex.quote(str(ROOT / ('install.sh' if installing else 'uninstall.sh')))}
{'INSTALL_SCOPE' if installing else 'UNINSTALL_SCOPE'}={scope}
set_manifest_path
ask_yn() {{ return {answer}; }}
ask_yn_default_no() {{ return {answer}; }}
{'install_rules' if installing else 'remove_rules'}
"""
        result = subprocess.run(["bash", "-c", body], env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def seed(self, content: bytes) -> None:
        self.agents.parent.mkdir(parents=True, exist_ok=True)
        self.agents.write_bytes(content)

    def test_install_reinstall_remove_preserves_outside_bytes(self) -> None:
        for original in (b"", b"user without newline", b"user\n", b"user\n\n", b"user\r\n\r\n",
                         "사용자\r\n<!-- context7 -->\r\nkeep\r\n<!-- /context7 -->\r\n".encode()):
            with self.subTest(original=original):
                self.seed(original)
                self.run_rules("install")
                source = (ROOT / "rules" / "code-writing.md").read_bytes()
                self.assertEqual(self.claude.read_bytes(), source)
                installed = self.agents.read_bytes()
                self.assertTrue(installed.startswith(original))
                newline = b"\r\n" if b"\r\n" in original else b"\n"
                separator = b""
                if original and not original.endswith((b"\n\n", b"\n\r\n")):
                    separator = newline * (1 if original.endswith(b"\n") else 2)
                self.assertEqual(installed[:installed.index(self.start)], original + separator)
                content = installed.split(self.start)[1].split(self.end)[0]
                self.assertEqual(content, source if source.endswith(b"\n") else source + b"\n")
                entries = json.loads(self.manifest.read_text())["entries"]
                for entry in entries:
                    self.assertEqual(entry["kind"], "rule")
                    self.assertEqual(entry["component"], "code-writing")
                    expected = content if entry["client"] == "codex" else source
                    self.assertEqual(entry["hash"], hashlib.sha256(expected).hexdigest())
                self.run_rules("install")
                self.assertEqual(self.agents.read_bytes(), installed)
                self.assertEqual(installed.count(self.start), 1)
                self.run_rules("remove")
                self.assertEqual(self.agents.read_bytes(), original)
                self.assertFalse(self.claude.exists())
                self.assertFalse(self.manifest.exists())

    def test_absent_file_is_created_and_left_empty_after_removal(self) -> None:
        self.run_rules("install")
        self.assertTrue(self.agents.exists())
        self.run_rules("remove")
        self.assertEqual(self.agents.read_bytes(), b"")

    def test_user_edits_to_both_rules_are_preserved_with_warning(self) -> None:
        self.run_rules("install")
        changed = self.agents.read_bytes().replace(self.start, self.start + b"user change\n")
        self.agents.write_bytes(changed)
        self.claude.write_bytes(b"user rule\n")
        manifest_before = self.manifest.read_bytes()
        for action in ("install", "remove"):
            result = self.run_rules(action)
            self.assertIn("[WARN]", result.stdout)
            self.assertEqual(self.agents.read_bytes(), changed)
            self.assertEqual(self.claude.read_bytes(), b"user rule\n")
            self.assertEqual(self.manifest.read_bytes(), manifest_before)

    def test_outside_edits_do_not_prevent_owned_block_removal(self) -> None:
        self.seed(b"original\r\n")
        self.run_rules("install")
        self.agents.write_bytes(b"new prefix\r\n" + self.agents.read_bytes() + b"new suffix\r\n")
        self.run_rules("install")
        self.run_rules("remove")
        self.assertEqual(self.agents.read_bytes(), b"new prefix\r\noriginal\r\nnew suffix\r\n")

    def test_source_update_replaces_only_block_content(self) -> None:
        self.seed(b"user\r\n<!-- context7 -->\r\nkeep\r\n<!-- /context7 -->\r\n")
        self.run_rules("install")
        source = (ROOT / "rules" / "code-writing.md").read_bytes()
        replacement = source + b"\nupdated source\n"
        changed_source = self.home / "updated-rule.md"
        changed_source.write_bytes(replacement)
        installed = self.agents.read_bytes().replace(self.start, self.start.replace(b"\n", b"\r\n"))
        self.agents.write_bytes(installed)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "rule_block.py"), "install", "--target", str(self.agents),
             "--manifest", str(self.manifest), "--name", "code-writing", "--source", str(changed_source)],
            env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        old_content = source if source.endswith(b"\n") else source + b"\n"
        self.assertEqual(self.agents.read_bytes(), installed.replace(old_content, replacement, 1))

    def test_unowned_missing_duplicate_and_malformed_blocks_are_preserved(self) -> None:
        self.run_rules("install")
        owned = self.agents.read_bytes()
        for changed in (owned + owned, owned.replace(self.end, b"broken closing marker\n"), b"user removed block\n"):
            with self.subTest(changed=changed):
                self.agents.write_bytes(changed)
                for action in ("install", "remove"):
                    self.assertIn("[WARN]", self.run_rules(action).stdout)
                    self.assertEqual(self.agents.read_bytes(), changed)
        self.manifest.unlink()
        self.agents.write_bytes(owned)
        for action in ("install", "remove"):
            self.assertIn("[WARN]", self.run_rules(action).stdout)
            self.assertEqual(self.agents.read_bytes(), owned)

    def test_project_scope_and_declined_prompts_do_not_install_rules(self) -> None:
        self.assertIn("rule은 전역 범위에서만 설치", self.run_rules("install", scope="project").stdout)
        self.run_rules("remove", scope="project")
        self.run_rules("install", answer=1)
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.agents.exists())

    def test_rule_manifest_failure_restores_target_and_record(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("rule_block", ROOT / "scripts" / "rule_block.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.seed(b"original\r\n")
        args = type("Args", (), dict(action="install", target=self.agents, manifest=self.manifest,
                                    source=ROOT / "rules" / "code-writing.md", name="code-writing"))()
        from unittest.mock import patch
        with patch.object(module.manifest, "_write", side_effect=OSError("injected manifest write failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                module.update(args)
        self.assertEqual(self.agents.read_bytes(), b"original\r\n")
        self.assertFalse(self.manifest.exists())
        self.run_rules("install")
        args.action = "remove"
        before = self.agents.read_bytes(), self.manifest.read_bytes()
        with patch.object(module.manifest, "prune", side_effect=OSError("injected manifest prune failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                module.update(args)
        self.assertEqual((self.agents.read_bytes(), self.manifest.read_bytes()), before)

    def test_posix_main_dispatches_rules_after_existing_questions(self) -> None:
        for action in ("install", "uninstall"):
            functions = ("ask_skill_install_mode create_skill_links setup_workflow_hook install_codex_skills install_agents show_dependency_diagnostics"
                         if action == "install" else "remove_claude_skills remove_workflow_hook remove_codex_skills remove_agents")
            stubs = "\n".join(f"{name}() {{ :; }}" for name in functions.split())
            body = f"""
source {shlex.quote(str(ROOT / (action + '.sh')))}
ask_{action}_scope() {{ :; }}
{stubs}
main
"""
            done = subprocess.run(["bash", "-c", body], input="\n\n" if action == "install" else "y\ny\n",
                                  env=self.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(self.claude.exists(), action == "install")


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
