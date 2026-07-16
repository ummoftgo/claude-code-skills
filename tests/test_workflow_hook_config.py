import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hooks import workflow_hook_config


ROOT = Path(__file__).resolve().parents[1]


def hook_entry(command: str, *, matcher: str | None = None) -> dict:
    entry = {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
            }
        ]
    }
    if matcher is not None:
        entry["matcher"] = matcher
    return entry


class WorkflowHookConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.settings = self.root / "hooks.json"
        self.managed_hook = self.root / "hooks" / "claude-code-skills-workflow.py"
        self.foreign_command = "python3 /opt/team/claude-code-skills-workflow.py"

    def write_settings(self, entries: list[dict]) -> None:
        self.settings.write_text(
            json.dumps({"hooks": {"UserPromptSubmit": entries}}, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_entries(self) -> list[dict]:
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        return data["hooks"]["UserPromptSubmit"]

    def test_install_preserves_foreign_hook_with_same_basename(self) -> None:
        self.write_settings([hook_entry(self.foreign_command)])

        workflow_hook_config.install_hook(
            self.settings,
            self.managed_hook,
        )

        entries = self.read_entries()
        commands = [entry["hooks"][0]["command"] for entry in entries]
        self.assertIn(self.foreign_command, commands)
        self.assertIn(
            workflow_hook_config.managed_command(self.managed_hook),
            commands,
        )
        managed_entry = next(
            entry
            for entry in entries
            if entry["hooks"][0]["command"]
            == workflow_hook_config.managed_command(self.managed_hook)
        )
        self.assertNotIn("matcher", managed_entry)

    def test_remove_deletes_only_exact_managed_hook(self) -> None:
        managed = workflow_hook_config.managed_command(self.managed_hook)
        self.write_settings(
            [
                hook_entry(self.foreign_command),
                hook_entry(managed, matcher="*"),
            ]
        )

        changed = workflow_hook_config.remove_hook(self.settings, self.managed_hook)

        self.assertTrue(changed)
        commands = [entry["hooks"][0]["command"] for entry in self.read_entries()]
        self.assertEqual(commands, [self.foreign_command])

    def test_invalid_json_is_not_rewritten(self) -> None:
        original = "{ invalid json\n"
        self.settings.write_text(original, encoding="utf-8")

        with self.assertRaises(workflow_hook_config.ConfigError):
            workflow_hook_config.install_hook(self.settings, self.managed_hook)

        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)

    def test_install_updates_settings_symlink_target_without_replacing_link(self) -> None:
        real_settings = self.root / "dotfiles" / "settings.json"
        real_settings.parent.mkdir()
        real_settings.write_text("{}\n", encoding="utf-8")
        self.settings.symlink_to(real_settings)

        workflow_hook_config.install_hook(self.settings, self.managed_hook)

        self.assertTrue(self.settings.is_symlink())
        data = json.loads(real_settings.read_text(encoding="utf-8"))
        command = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertEqual(
            command,
            workflow_hook_config.managed_command(self.managed_hook),
        )

    def test_install_rejects_dangling_settings_symlink(self) -> None:
        self.settings.symlink_to(self.root / "missing-settings.json")

        with self.assertRaises(workflow_hook_config.ConfigError):
            workflow_hook_config.install_hook(self.settings, self.managed_hook)

        self.assertTrue(self.settings.is_symlink())

    def test_install_rejects_settings_symlink_outside_allowed_root(self) -> None:
        project_root = self.root / "project"
        project_root.mkdir()
        settings = project_root / "hooks.json"
        outside_settings = self.root / "outside-hooks.json"
        outside_settings.write_text("{}\n", encoding="utf-8")
        settings.symlink_to(outside_settings)

        with self.assertRaises(workflow_hook_config.OutsideRootError):
            workflow_hook_config.install_hook(
                settings,
                self.managed_hook,
                allowed_root=project_root,
            )

        self.assertEqual(outside_settings.read_text(encoding="utf-8"), "{}\n")

    def test_install_allows_outside_settings_target_only_with_override(self) -> None:
        project_root = self.root / "project"
        project_root.mkdir()
        settings = project_root / "hooks.json"
        outside_settings = self.root / "outside-hooks.json"
        outside_settings.write_text("{}\n", encoding="utf-8")
        settings.symlink_to(outside_settings)

        workflow_hook_config.install_hook(
            settings,
            self.managed_hook,
            allowed_root=project_root,
            allow_outside_root=True,
        )

        self.assertTrue(settings.is_symlink())
        self.assertIn(
            "UserPromptSubmit",
            json.loads(outside_settings.read_text(encoding="utf-8"))["hooks"],
        )

    def test_install_rejects_escape_through_settings_parent_symlink(self) -> None:
        project_root = self.root / "project"
        project_root.mkdir()
        outside_dir = self.root / "outside-codex"
        outside_dir.mkdir()
        outside_settings = outside_dir / "hooks.json"
        outside_settings.write_text("{}\n", encoding="utf-8")
        (project_root / ".codex").symlink_to(outside_dir, target_is_directory=True)
        settings = project_root / ".codex" / "hooks.json"

        with self.assertRaises(workflow_hook_config.OutsideRootError):
            workflow_hook_config.install_hook(
                settings,
                self.managed_hook,
                allowed_root=project_root,
            )

        self.assertEqual(outside_settings.read_text(encoding="utf-8"), "{}\n")

    def test_remove_rejects_dangling_settings_symlink(self) -> None:
        self.settings.symlink_to(self.root / "missing-settings.json")

        with self.assertRaises(workflow_hook_config.ConfigError):
            workflow_hook_config.remove_hook(self.settings, self.managed_hook)

        self.assertTrue(self.settings.is_symlink())

    def test_remove_updates_settings_symlink_target_without_replacing_link(self) -> None:
        real_settings = self.root / "dotfiles" / "settings.json"
        real_settings.parent.mkdir()
        command = workflow_hook_config.managed_command(self.managed_hook)
        real_settings.write_text(
            json.dumps(
                {"hooks": {"UserPromptSubmit": [hook_entry(command)]}},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.settings.symlink_to(real_settings)

        changed = workflow_hook_config.remove_hook(self.settings, self.managed_hook)

        self.assertTrue(changed)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(json.loads(real_settings.read_text(encoding="utf-8")), {})

    def test_install_preserves_unrelated_empty_hook_group(self) -> None:
        empty_group = {"matcher": "reserved", "hooks": []}
        self.write_settings([empty_group])

        workflow_hook_config.install_hook(self.settings, self.managed_hook)

        self.assertIn(empty_group, self.read_entries())

    def test_remove_preserves_unrelated_empty_hook_group(self) -> None:
        empty_group = {"matcher": "reserved", "hooks": []}
        managed = workflow_hook_config.managed_command(self.managed_hook)
        self.write_settings([empty_group, hook_entry(managed)])

        changed = workflow_hook_config.remove_hook(self.settings, self.managed_hook)

        self.assertTrue(changed)
        self.assertEqual(self.read_entries(), [empty_group])

    def test_codex_trust_state_is_not_treated_as_inline_hooks(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            '[hooks.state."/home/user/.codex/hooks.json:user_prompt_submit:0:0"]\n'
            'enabled = true\n',
            encoding="utf-8",
        )

        self.assertFalse(workflow_hook_config.has_inline_hooks(config))

    def test_codex_inline_event_table_is_detected(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[[hooks.UserPromptSubmit]]\n"
            "hooks = []\n",
            encoding="utf-8",
        )

        self.assertTrue(workflow_hook_config.has_inline_hooks(config))

    def test_codex_disabled_hooks_are_detected(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[features]\n"
            "hooks = false\n",
            encoding="utf-8",
        )

        self.assertTrue(workflow_hook_config.has_disabled_hooks(config))

    def test_codex_deprecated_disabled_hooks_are_detected(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[features]\n"
            "codex_hooks = false\n",
            encoding="utf-8",
        )

        self.assertEqual(
            workflow_hook_config.disabled_hook_reason(config),
            "[features] codex_hooks = false",
        )

    def test_codex_managed_only_key_in_config_is_not_treated_as_effective(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "allow_managed_hooks_only = true\n",
            encoding="utf-8",
        )

        self.assertIsNone(workflow_hook_config.disabled_hook_reason(config))

    def test_project_codex_config_inherits_user_disabled_hook_feature(self) -> None:
        user_config = self.root / "user-config.toml"
        project_config = self.root / "project-config.toml"
        user_config.write_text("[features]\nhooks = false\n", encoding="utf-8")

        self.assertEqual(
            workflow_hook_config.disabled_hook_reason(
                project_config,
                base_config_path=user_config,
            ),
            "[features] hooks = false (inherited from user config)",
        )

    def test_project_codex_hook_feature_overrides_user_setting(self) -> None:
        user_config = self.root / "user-config.toml"
        project_config = self.root / "project-config.toml"
        user_config.write_text("[features]\nhooks = false\n", encoding="utf-8")
        project_config.write_text("[features]\nhooks = true\n", encoding="utf-8")

        self.assertIsNone(
            workflow_hook_config.disabled_hook_reason(
                project_config,
                base_config_path=user_config,
            )
        )

    def test_python_310_fallback_detects_dotted_feature_keys(self) -> None:
        config = self.root / "config.toml"
        for key in ("features.hooks", "features.codex_hooks"):
            with self.subTest(key=key):
                config.write_text(f"{key} = false\n", encoding="utf-8")
                self.assertIsNotNone(
                    workflow_hook_config._fallback_disabled_hook_reason(config)
                )

    def test_codex_canonical_hook_flag_overrides_deprecated_alias(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[features]\n"
            "hooks = true\n"
            "codex_hooks = false\n",
            encoding="utf-8",
        )

        self.assertIsNone(workflow_hook_config.disabled_hook_reason(config))

    def test_codex_enabled_or_unspecified_hooks_are_not_disabled(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[features]\n"
            "hooks = true\n",
            encoding="utf-8",
        )
        self.assertFalse(workflow_hook_config.has_disabled_hooks(config))
        self.assertFalse(
            workflow_hook_config.has_disabled_hooks(self.root / "missing.toml")
        )

    def test_enable_hooks_preserves_unrelated_toml_and_comments(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "# personal config\n"
            "[features]\n"
            "other_feature = true\n"
            "hooks = false # enable during workflow install\n",
            encoding="utf-8",
        )

        workflow_hook_config.enable_hooks(config)

        updated = config.read_text(encoding="utf-8")
        self.assertIn("# personal config", updated)
        self.assertIn("other_feature = true", updated)
        self.assertIn("hooks = true # enable during workflow install", updated)

    def test_enable_hooks_normalizes_deprecated_alias(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            "[features]\n"
            "codex_hooks = false # legacy\n",
            encoding="utf-8",
        )

        workflow_hook_config.enable_hooks(config)

        updated = config.read_text(encoding="utf-8")
        self.assertIn("hooks = true # legacy", updated)
        self.assertNotIn("codex_hooks", updated)

    def test_enable_project_hooks_overrides_user_config_without_modifying_it(self) -> None:
        user_config = self.root / "user-config.toml"
        project_config = self.root / "project" / ".codex" / "config.toml"
        user_original = "[features]\nhooks = false\n"
        user_config.write_text(user_original, encoding="utf-8")

        workflow_hook_config.enable_hooks(project_config)

        self.assertEqual(user_config.read_text(encoding="utf-8"), user_original)
        self.assertIn("hooks = true", project_config.read_text(encoding="utf-8"))
        self.assertIsNone(
            workflow_hook_config.disabled_hook_reason(
                project_config,
                base_config_path=user_config,
            )
        )

    def test_enable_hooks_updates_symlink_target_without_replacing_link(self) -> None:
        real_config = self.root / "dotfiles" / "config.toml"
        real_config.parent.mkdir()
        real_config.write_text("[features]\nhooks = false\n", encoding="utf-8")
        config = self.root / "config.toml"
        config.symlink_to(real_config)

        workflow_hook_config.enable_hooks(config)

        self.assertTrue(config.is_symlink())
        self.assertIn("hooks = true", real_config.read_text(encoding="utf-8"))

    def test_enable_hooks_does_not_rewrite_invalid_toml(self) -> None:
        config = self.root / "config.toml"
        original = "[features\nhooks = false\n"
        config.write_text(original, encoding="utf-8")

        with self.assertRaises(workflow_hook_config.ConfigError):
            workflow_hook_config.enable_hooks(config)

        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_enable_hooks_requires_tomllib_for_safe_update(self) -> None:
        config = self.root / "config.toml"
        original = "[features]\nhooks = false\n"
        config.write_text(original, encoding="utf-8")

        with mock.patch.object(workflow_hook_config, "tomllib", None):
            with self.assertRaises(workflow_hook_config.ConfigError):
                workflow_hook_config.enable_hooks(config)

        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_install_script_does_not_leave_partial_hook_on_invalid_json(self) -> None:
        hooks_dir = self.root / ".claude" / "hooks"
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{ invalid json\n", encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
set_manifest_path
ask_yn() {{ return 0; }}
setup_workflow_hook "Claude Code" {hooks_dir} {settings} claude-hook
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse((self.root / ".claude-code-skills" / "manifest.tsv").exists())

    def test_install_script_rolls_back_hook_and_settings_on_manifest_failure(self) -> None:
        hooks_dir = self.root / ".claude" / "hooks"
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        original = json.dumps({"keep": {"value": True}}, indent=2) + "\n"
        settings.write_text(original, encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
manifest_record_required() {{ return 1; }}
setup_workflow_hook "Claude Code" {hooks_dir} {settings} claude-hook
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertEqual(settings.read_text(encoding="utf-8"), original)

    def test_manifest_rollback_preserves_snapshot_when_settings_restore_fails(self) -> None:
        hooks_dir = self.root / ".claude" / "hooks"
        settings = self.root / ".claude" / "settings.json"
        temporary = self.root / "tmp"
        settings.parent.mkdir(parents=True)
        temporary.mkdir()
        settings.write_text('{"keep": true}\n', encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
TMPDIR={temporary}
set_manifest_path
ask_yn() {{ return 0; }}
manifest_record_required() {{ return 1; }}
cp() {{
    if [[ "$2" == "$TMPDIR"/workflow-settings.*/settings ]]; then
        return 1
    fi
    command cp "$@"
}}
set +e
setup_workflow_hook "Claude Code" {hooks_dir} {settings} claude-hook
set -e
find "$TMPDIR" -path '*/workflow-settings.*/settings' -type f | grep -q .
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("스냅샷을 보존합니다", result.stdout)

    def test_shell_install_uninstall_round_trip_preserves_foreign_hook(self) -> None:
        hooks_dir = self.root / ".codex" / "hooks"
        settings = self.root / ".codex" / "hooks.json"
        settings.parent.mkdir(parents=True)
        self.write_settings([hook_entry(self.foreign_command)])
        self.settings.replace(settings)

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {self.root / '.codex' / 'config.toml'}

source {ROOT / 'uninstall.sh'}
INSTALL_BASE_DIR={self.root}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
remove_workflow_hook "Codex" {hooks_dir} {settings}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        data = json.loads(settings.read_text(encoding="utf-8"))
        commands = [
            entry["hooks"][0]["command"]
            for entry in data["hooks"]["UserPromptSubmit"]
        ]
        self.assertEqual(commands, [self.foreign_command])

    def test_codex_install_defaults_to_skip_when_inline_hooks_exist(self) -> None:
        hooks_dir = self.root / ".codex" / "hooks"
        settings = self.root / ".codex" / "hooks.json"
        config = self.root / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[[hooks.UserPromptSubmit]]\nhooks = []\n", encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {config}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse(settings.exists())

    def test_codex_install_defaults_to_skip_when_hooks_are_disabled(self) -> None:
        hooks_dir = self.root / ".codex" / "hooks"
        settings = self.root / ".codex" / "hooks.json"
        config = self.root / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[features]\nhooks = false\n", encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {config}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("자동 변경하지 않습니다", result.stdout)
        self.assertIn("hooks = false", config.read_text(encoding="utf-8"))
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse(settings.exists())

    def test_posix_codex_install_never_changes_disabled_hooks(self) -> None:
        hooks_dir = self.root / ".codex" / "hooks"
        settings = self.root / ".codex" / "hooks.json"
        config = self.root / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[features]\nhooks = false\n", encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 0; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {config}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("자동 변경하지 않습니다", result.stdout)
        self.assertIn("hooks = false", config.read_text(encoding="utf-8"))
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse(settings.exists())

    def test_project_codex_install_inherits_user_disabled_hooks(self) -> None:
        project_root = self.root / "project"
        project_root.mkdir()
        hooks_dir = project_root / ".codex" / "hooks"
        settings = project_root / ".codex" / "hooks.json"
        project_config = project_root / ".codex" / "config.toml"
        user_config = self.root / "user-config.toml"
        user_config.write_text("[features]\nhooks = false\n", encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=project
INSTALL_BASE_DIR={project_root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {project_config} {user_config}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("inherited from user config", result.stdout)
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse(settings.exists())

    def test_posix_project_codex_install_preserves_inherited_disabled_hooks(self) -> None:
        project_root = self.root / "project"
        project_root.mkdir()
        hooks_dir = project_root / ".codex" / "hooks"
        settings = project_root / ".codex" / "hooks.json"
        project_config = project_root / ".codex" / "config.toml"
        user_config = self.root / "user-config.toml"
        user_original = "[features]\nhooks = false\n"
        user_config.write_text(user_original, encoding="utf-8")

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_SCOPE=project
INSTALL_BASE_DIR={project_root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 0; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {project_config} {user_config}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(user_config.read_text(encoding="utf-8"), user_original)
        self.assertFalse(project_config.exists())
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())

    def test_install_defaults_to_skip_for_outside_scope_hook_directory(self) -> None:
        project_root = self.root / "project"
        codex_dir = project_root / ".codex"
        outside_hooks_dir = self.root / "outside-hooks"
        codex_dir.mkdir(parents=True)
        outside_hooks_dir.mkdir()
        hooks_dir = codex_dir / "hooks"
        hooks_dir.symlink_to(outside_hooks_dir, target_is_directory=True)
        settings = codex_dir / "hooks.json"

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={project_root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {codex_dir / 'config.toml'}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("훅 파일 대상이 선택한 설치 범위 밖", result.stdout + result.stderr)
        self.assertFalse((outside_hooks_dir / "claude-code-skills-workflow.py").exists())
        self.assertFalse(settings.exists())

    def test_install_defaults_to_skip_for_outside_scope_settings_symlink(self) -> None:
        project_root = self.root / "project"
        hooks_dir = project_root / ".codex" / "hooks"
        settings = project_root / ".codex" / "hooks.json"
        settings.parent.mkdir(parents=True)
        outside_settings = self.root / "outside-hooks.json"
        outside_settings.write_text("{}\n", encoding="utf-8")
        settings.symlink_to(outside_settings)

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={project_root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {project_root / '.codex' / 'config.toml'}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("설치 범위 밖", result.stdout + result.stderr)
        self.assertEqual(outside_settings.read_text(encoding="utf-8"), "{}\n")
        self.assertFalse((hooks_dir / "claude-code-skills-workflow.py").exists())

    def test_uninstall_stops_when_settings_symlink_is_dangling(self) -> None:
        hooks_dir = self.root / ".codex" / "hooks"
        settings = self.root / ".codex" / "hooks.json"

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={self.root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {self.root / '.codex' / 'config.toml'}
rm {settings}
ln -s {self.root / 'missing-hooks.json'} {settings}

source {ROOT / 'uninstall.sh'}
INSTALL_BASE_DIR={self.root}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
remove_workflow_hook "Codex" {hooks_dir} {settings}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(settings.is_symlink())
        self.assertTrue((hooks_dir / "claude-code-skills-workflow.py").exists())

    def test_uninstall_defaults_to_preserve_outside_scope_hook_file(self) -> None:
        project_root = self.root / "project"
        codex_dir = project_root / ".codex"
        outside_hooks_dir = self.root / "outside-hooks"
        codex_dir.mkdir(parents=True)
        outside_hooks_dir.mkdir()
        hooks_dir = codex_dir / "hooks"
        hooks_dir.symlink_to(outside_hooks_dir, target_is_directory=True)
        settings = codex_dir / "hooks.json"

        command = f"""
source {ROOT / 'install.sh'}
INSTALL_BASE_DIR={project_root}
HOOKS_DIR={ROOT / 'hooks'}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 0; }}
setup_workflow_hook "Codex" {hooks_dir} {settings} codex-hook {codex_dir / 'config.toml'}

source {ROOT / 'uninstall.sh'}
INSTALL_BASE_DIR={project_root}
HOOK_CONFIG_TOOL={ROOT / 'hooks' / 'workflow_hook_config.py'}
set_manifest_path
ask_yn() {{ return 0; }}
ask_yn_default_no() {{ return 1; }}
remove_workflow_hook "Codex" {hooks_dir} {settings}
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("훅 파일 대상이 선택한 제거 범위 밖", result.stdout + result.stderr)
        self.assertTrue((outside_hooks_dir / "claude-code-skills-workflow.py").exists())


if __name__ == "__main__":
    unittest.main()
