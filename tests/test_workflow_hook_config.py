import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hooks import workflow_hook_config


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# This repository supports Python 3.10, where `import tomllib` fails and
# workflow_hook_config falls back to line scanning. Anything that needs the
# structural parser (the authoritative inline-hook answer, and enable_hooks,
# which refuses to rewrite config.toml without a parser) is skipped there
# instead of failing; the fallback behaviour is asserted separately against its
# own expectations, so the suite reports the same verdicts on 3.10 and 3.12.
HAS_TOMLLIB = workflow_hook_config.tomllib is not None
# The real parser, captured once so a test can cross-check its own inputs against
# tomllib (are they really valid/invalid TOML?) even while it patches the module
# attribute away to force the fallback. None on Python 3.10, where those
# cross-checks are skipped.
TOMLLIB = workflow_hook_config.tomllib
NEEDS_TOMLLIB = unittest.skipIf(
    not HAS_TOMLLIB,
    "requires tomllib (Python 3.11+); the 3.10 fallback path is covered separately",
)
# Forces the Python 3.10 code path on any interpreter: import the module, drop
# tomllib, then run the same CLI entry point install.sh calls.
FALLBACK_CLI_SHIM = (
    "import sys;"
    f"sys.path.insert(0, {str(ROOT)!r});"
    "from hooks import workflow_hook_config as module;"
    "module.tomllib = None;"
    "sys.argv = ['workflow_hook_config.py'] + sys.argv[1:];"
    "raise SystemExit(module.main())"
)


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

    def assert_inline_hooks(self, content: str, expected: bool) -> None:
        """Both the tomllib path and the Python 3.10 fallback must agree."""
        config = self.root / "config.toml"
        config.write_text(content, encoding="utf-8")

        with self.subTest(path="tomllib"):
            self.assertEqual(workflow_hook_config.has_inline_hooks(config), expected)
        with self.subTest(path="fallback"):
            with mock.patch.object(workflow_hook_config, "tomllib", None):
                self.assertEqual(
                    workflow_hook_config.has_inline_hooks(config), expected
                )

    def test_codex_inline_session_end_table_is_detected(self) -> None:
        self.assert_inline_hooks(
            "[[hooks.SessionEnd]]\ncommand = [\"true\"]\n",
            True,
        )

    def test_codex_inline_unknown_future_event_is_detected(self) -> None:
        self.assert_inline_hooks(
            "[[hooks.SomeFutureEvent]]\ncommand = [\"true\"]\n",
            True,
        )

    def test_codex_root_inline_hooks_table_is_detected(self) -> None:
        self.assert_inline_hooks(
            "hooks = { UserPromptSubmit = [] }\n",
            True,
        )

    def test_codex_event_table_with_whitespace_around_dots_is_detected(self) -> None:
        """TOML allows whitespace around key dots; both paths must still detect it."""
        self.assert_inline_hooks(
            "[[ hooks . SessionEnd ]]\ncommand = [\"true\"]\n",
            True,
        )

    def test_codex_dotted_assignment_hook_is_detected(self) -> None:
        """A dotted assignment is equivalent to [[hooks.SessionEnd]], value shape aside."""
        self.assert_inline_hooks(
            'hooks.SessionEnd = [{ command = "x" }]\n',
            True,
        )
        self.assert_inline_hooks(
            'hooks . SessionEnd = [{ command = "x" }]\n',
            True,
        )
        self.assert_inline_hooks(
            'hooks.SessionEnd.command = "x"\n',
            True,
        )

    def test_codex_state_table_with_whitespace_around_dots_is_exempt(self) -> None:
        self.assert_inline_hooks("[hooks . state]\nenabled = true\n", False)
        self.assert_inline_hooks("hooks . state = { trusted = true }\n", False)
        self.assert_inline_hooks(
            'hooks.state."/home/user/.codex/hooks.json:x:0:0" = { enabled = true }\n',
            False,
        )

    def test_codex_hook_feature_flag_is_not_treated_as_inline_hooks(self) -> None:
        """The widened dotted-assignment rule must not swallow [features] hooks = true."""
        self.assert_inline_hooks("[features]\nhooks = true\n", False)
        self.assert_inline_hooks("[features]\nhooks = false\n", False)
        self.assert_inline_hooks("[features]\nhooks = true  # enable hooks\n", False)
        self.assert_inline_hooks("features.hooks = true\n", False)

    def test_codex_basic_string_key_escapes_are_decoded(self) -> None:
        """TOML decodes escapes in a basic-string key, so the detectors must too.

        Both directions are load-bearing: an escaped root key is a real hook
        declaration the installer must not miss, and an escaped `state` key is
        Codex's trust store, where a false positive blocks a working install.
        """
        self.assert_inline_hooks('"\\u0068ooks".SessionEnd = []\n', True)
        self.assert_inline_hooks('"\\U00000068ooks".UserPromptSubmit = []\n', True)
        self.assert_inline_hooks('hooks."Session\\u0045nd" = []\n', True)
        self.assert_inline_hooks('hooks."\\u0073tate" = { trusted = true }\n', False)
        self.assert_inline_hooks('[hooks."\\u0073tate"]\nenabled = true\n', False)
        # Decoding stays case sensitive: \u0048 is H and \u0053 is S.
        self.assert_inline_hooks('"\\u0048ooks".SessionEnd = []\n', False)
        self.assert_inline_hooks('hooks."\\u0053tate" = { x = 1 }\n', True)
        # An escaped backslash is not the start of an escape.
        self.assert_inline_hooks('"\\\\u0068ooks".SessionEnd = []\n', False)

    def test_codex_literal_string_key_escapes_are_not_decoded(self) -> None:
        """A literal string interprets no escapes: `'\\u0073tate'` is not `state`."""
        self.assert_inline_hooks("'\\u0068ooks'.SessionEnd = []\n", False)
        self.assert_inline_hooks("hooks.'\\u0073tate' = { trusted = true }\n", True)
        self.assert_inline_hooks("[hooks.'\\u0073tate']\nenabled = true\n", True)

    def test_codex_unhandled_key_escapes_cannot_change_the_verdict(self) -> None:
        """Pin the documented limit of the line-based decoders as a no-op.

        `\\n`, `\\t`, `\\r`, `\\f` and `\\b` are left as written rather than
        embedding a TOML string decoder in a line scanner. That cannot change an
        answer, because the only names compared against are `hooks` and `state`
        and no escape but `\\u`/`\\U` can produce lowercase ASCII.
        """
        for escape in ("\\n", "\\t", "\\r", "\\f", "\\b"):
            for template in (
                '"{key}".SessionEnd = []\n',
                "hooks.\"{key}\" = {{ trusted = true }}\n",
                '[[hooks."{key}"]]\ncommand = ["true"]\n',
            ):
                for name in ("hooks", "state", ""):
                    for position in range(len(name) + 1):
                        key = f"{name[:position]}{escape}{name[position:]}"
                        content = template.format(key=key)
                        with self.subTest(content=content):
                            # `expected` is whatever tomllib says; the point is
                            # that the fallback never disagrees with it.
                            config = self.root / "config.toml"
                            config.write_text(content, encoding="utf-8")
                            expected = workflow_hook_config.has_inline_hooks(config)
                            self.assert_inline_hooks(content, expected)

    def test_normalized_toml_key_leaves_invalid_escapes_alone(self) -> None:
        """Escapes TOML itself would reject stay verbatim, never a decoded key.

        These spellings cannot be reached through a valid config, so they are
        checked directly rather than through has_inline_hooks.
        """
        self.assertEqual(workflow_hook_config._normalized_toml_key('"\\ud800"'), "\\ud800")
        self.assertEqual(
            workflow_hook_config._normalized_toml_key('"\\Uffffffff"'), "\\Uffffffff"
        )
        self.assertEqual(workflow_hook_config._normalized_toml_key('"\\uZZZZ"'), "\\uZZZZ")
        self.assertEqual(workflow_hook_config._normalized_toml_key('"\\u007"'), "\\u007")
        self.assertEqual(workflow_hook_config._normalized_toml_key('"a\\\\"'), "a\\")
        self.assertEqual(workflow_hook_config._normalized_toml_key("state"), "state")
        self.assertIsNone(workflow_hook_config._normalized_toml_key(None))

    def test_codex_dotted_assignment_outside_root_table_is_not_a_declaration(self) -> None:
        """A dotted key is relative to its table: `[other]` + `hooks.X` is other.hooks.X.

        Same family as the `[features] hooks = true` false positive, which the
        `= {` restriction alone does not cover.
        """
        self.assert_inline_hooks("[other]\nhooks.SessionEnd = []\n", False)
        self.assert_inline_hooks("[other]\nhooks = { UserPromptSubmit = [] }\n", False)
        self.assert_inline_hooks('[other]\n"hooks".SessionEnd = []\n', False)
        self.assert_inline_hooks("[hooks.state]\nhooks.SessionEnd = []\n", False)
        # ...but the root table itself, and only it, still counts.
        self.assert_inline_hooks("hooks.SessionEnd = []\n[other]\nx = 1\n", True)
        # A `[...]` line inside an unclosed array is an element, not a header,
        # so it must not end the root context early.
        self.assert_inline_hooks('args = [\n  ["a"]\n]\nhooks.SessionEnd = []\n', True)

    def test_codex_state_only_table_is_not_treated_as_inline_hooks(self) -> None:
        self.assert_inline_hooks(
            "[hooks.state]\n"
            '"/home/user/.codex/hooks.json:user_prompt_submit:0:0" = { enabled = true }\n',
            False,
        )

    def test_codex_hook_shapes_in_comments_are_not_detected(self) -> None:
        self.assert_inline_hooks(
            "# [[hooks.PreToolUse]]\n"
            "# hooks = { UserPromptSubmit = [] }\n"
            "[features]\n"
            "hooks = true\n",
            False,
        )

    def test_codex_hook_shapes_in_multiline_strings_are_not_detected(self) -> None:
        self.assert_inline_hooks(
            'notes = """\n'
            "[[hooks.PreToolUse]]\n"
            "hooks = { UserPromptSubmit = [] }\n"
            '"""\n',
            False,
        )
        self.assert_inline_hooks(
            "notes = '''\n"
            "[[hooks.PreToolUse]]\n"
            "hooks = { UserPromptSubmit = [] }\n"
            "'''\n",
            False,
        )

    def test_codex_invalid_toml_does_not_silently_hide_inline_hooks(self) -> None:
        config = self.root / "config.toml"
        config.write_text("[hooks.UserPromptSubmit\n", encoding="utf-8")

        with self.assertRaises(workflow_hook_config.ConfigError):
            workflow_hook_config.has_inline_hooks(config)

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

    @NEEDS_TOMLLIB
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

    @NEEDS_TOMLLIB
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

    @NEEDS_TOMLLIB
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

    @NEEDS_TOMLLIB
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


class CodexInlineHookFixtureTest(unittest.TestCase):
    """Pin the cross-implementation inline-hook contract to shared fixture data.

    tests/fixtures/codex_inline_hooks.json is plain JSON so the PowerShell suite
    (tests/windows/run-installer-tests.ps1) can feed the same cases to
    Test-CodexInlineHooks via ConvertFrom-Json. Each case carries two expected
    values: `expected` for the authoritative structural answer (tomllib) and
    `lineBased` for the line-oriented detectors that have no TOML parser -- the
    Python 3.10 fallback and PowerShell 5.1. Cases where the two differ are
    marked knownDivergence and must stay documented, never silent.

    Every check here names the path it exercises, because this repository
    supports both: the structural assertions are skipped when the interpreter
    has no tomllib, and each line-based assertion forces the fallback (in
    process by patching the module attribute, in the CLI through
    FALLBACK_CLI_SHIM). Running the suite under Python 3.10 must therefore
    produce the same verdicts as under 3.12 rather than reporting the
    documented divergences as failures.
    """

    fixture_path = FIXTURES / "codex_inline_hooks.json"

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(cls.fixture_path.read_text(encoding="utf-8"))
        cls.cases = cls.fixture["cases"]
        cls.invalid = cls.fixture["invalidToml"]

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def write_case(self, case: dict) -> Path:
        config = self.root / f"{case['name']}.toml"
        config.write_text(case["toml"], encoding="utf-8")
        return config

    def inline_status(self, config: Path, *, force_fallback: bool) -> subprocess.CompletedProcess:
        command = (
            [sys.executable, "-c", FALLBACK_CLI_SHIM]
            if force_fallback
            else [sys.executable, str(ROOT / "hooks" / "workflow_hook_config.py")]
        )
        return subprocess.run(
            [*command, "inline-status", str(config)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_fixture_shape_is_usable_by_both_implementations(self) -> None:
        self.assertTrue(self.cases, "fixture must define at least one case")
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)), "case names must be unique")
        for case in self.cases:
            with self.subTest(case=case["name"]):
                self.assertIsInstance(case["toml"], str)
                self.assertIsInstance(case["expected"], bool)
                self.assertIsInstance(case["lineBased"], bool)
                self.assertIsInstance(case["knownDivergence"], bool)
                diverges = case["expected"] != case["lineBased"]
                self.assertEqual(
                    case["knownDivergence"],
                    diverges,
                    "knownDivergence must flag exactly the documented mismatches",
                )
                if diverges:
                    self.assertIn("note", case)
                    self.assertTrue(
                        case["lineBased"],
                        "a line-based divergence may only over-detect (fail-safe)",
                    )
        self.assertTrue(
            any(case["expected"] for case in self.cases)
            and any(not case["expected"] for case in self.cases),
            "fixture must cover both detected and undetected outcomes",
        )

    def test_invalid_toml_section_shape(self) -> None:
        detected = self.invalid["detectedByLineBased"]
        missed = self.invalid["missedByLineBased"]
        self.assertTrue(detected, "the recognisable structure errors must stay listed")
        self.assertTrue(missed, "the gap the fallback cannot close must stay listed")
        names = [case["name"] for case in (*detected, *missed)]
        self.assertEqual(len(names), len(set(names)), "case names must be unique")
        for case in (*detected, *missed):
            with self.subTest(case=case["name"]):
                self.assertIsInstance(case["toml"], str)
                self.assertIn("note", case)
        for case in missed:
            with self.subTest(case=case["name"]):
                self.assertIsInstance(
                    case["lineBased"],
                    bool,
                    "a missed error still has to pin the bool the fallback returns",
                )

    @NEEDS_TOMLLIB
    def test_structural_detection_matches_fixture(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                self.assertEqual(
                    workflow_hook_config.has_inline_hooks(config),
                    case["expected"],
                )

    def test_line_based_fallback_matches_fixture(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    self.assertEqual(
                        workflow_hook_config.has_inline_hooks(config),
                        case["lineBased"],
                    )

    @NEEDS_TOMLLIB
    def test_inline_status_exit_codes_match_fixture(self) -> None:
        expected_codes = self.fixture["exitCodes"]
        for case in self.cases:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                result = self.inline_status(config, force_fallback=False)
                self.assertEqual(
                    result.returncode,
                    expected_codes["detected"]
                    if case["expected"]
                    else expected_codes["notDetected"],
                    result.stdout + result.stderr,
                )

    def test_inline_status_exit_codes_match_fixture_on_fallback(self) -> None:
        expected_codes = self.fixture["exitCodes"]
        for case in self.cases:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                result = self.inline_status(config, force_fallback=True)
                self.assertEqual(
                    result.returncode,
                    expected_codes["detected"]
                    if case["lineBased"]
                    else expected_codes["notDetected"],
                    result.stdout + result.stderr,
                )

    @NEEDS_TOMLLIB
    def test_structural_path_reports_every_invalid_toml(self) -> None:
        error_code = self.fixture["exitCodes"]["error"]
        for case in (
            *self.invalid["detectedByLineBased"],
            *self.invalid["missedByLineBased"],
        ):
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                with self.assertRaises(workflow_hook_config.ConfigError):
                    workflow_hook_config.has_inline_hooks(config)
                result = self.inline_status(config, force_fallback=False)
                self.assertEqual(
                    result.returncode,
                    error_code,
                    result.stdout + result.stderr,
                )

    def test_fallback_reports_recognisable_invalid_toml(self) -> None:
        error_code = self.fixture["exitCodes"]["error"]
        for case in self.invalid["detectedByLineBased"]:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    with self.assertRaises(workflow_hook_config.ConfigError):
                        workflow_hook_config.has_inline_hooks(config)
                result = self.inline_status(config, force_fallback=True)
                self.assertEqual(
                    result.returncode,
                    error_code,
                    result.stdout + result.stderr,
                )

    def test_fallback_answers_bool_for_unrecognisable_invalid_toml(self) -> None:
        """Pin the gap: value-level damage still gets a bool, never an error."""
        codes = self.fixture["exitCodes"]
        for case in self.invalid["missedByLineBased"]:
            with self.subTest(case=case["name"]):
                config = self.write_case(case)
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    self.assertEqual(
                        workflow_hook_config.has_inline_hooks(config),
                        case["lineBased"],
                    )
                result = self.inline_status(config, force_fallback=True)
                self.assertEqual(
                    result.returncode,
                    codes["detected"] if case["lineBased"] else codes["notDetected"],
                    result.stdout + result.stderr,
                )

    def test_fallback_validates_before_answering(self) -> None:
        """A hook-shaped line before the damage must not win over the error."""
        config = self.root / "hook-then-broken.toml"
        config.write_text(
            '[[hooks.SessionEnd]]\ncommand = ["true"]\n[oops\n', encoding="utf-8"
        )
        with mock.patch.object(workflow_hook_config, "tomllib", None):
            with self.assertRaises(workflow_hook_config.ConfigError):
                workflow_hook_config.has_inline_hooks(config)

    def test_multiline_closing_delimiter_is_the_last_three_of_a_quote_run(self) -> None:
        """TOML allows 1-2 quotes just inside the closing delimiter.

        `mlb-quotes = 1*2quotation-mark` / `mll-quotes = 1*2apostrophe`
        (https://toml.io/en/v1.0.0#string), so a run of adjacent quotes is
        consumed whole and only its last three close the string. Taking the first
        three instead hid the rest of the line inside the string and turned valid
        TOML into a spurious ConfigError, which stops the 3.10 installer.
        """
        for run_length in (3, 4, 5):
            for delimiter in ('"""', "'''"):
                quote = delimiter[0]
                # The run_length - 3 quotes beyond the delimiter belong to the body.
                body = f"a{quote * (run_length - 3)}"
                with self.subTest(delimiter=delimiter, run=run_length):
                    text = f"x = [{delimiter}a{quote * run_length}, 1]\n"
                    self.assertEqual(
                        workflow_hook_config._toml_code_lines(text),
                        ["x = [, 1]"],
                        "the whole string must be stripped, leaving the array intact",
                    )
                    if TOMLLIB is not None:
                        self.assertEqual(
                            TOMLLIB.loads(text)["x"],
                            [body, 1],
                            "the run rule must match what tomllib itself accepts",
                        )

    def test_fallback_accepts_valid_multiline_string_with_extra_closing_quotes(self) -> None:
        """REGRESSION: rejecting valid TOML blocks the install, so it is worse than a warning."""
        for name, text in (
            ("four-quote-close", 'x = ["""a"""", 1]\n'),
            ("five-quote-close", 'x = ["""a""""", 1]\n'),
            ("spec-str7", 'str7 = """"This," she said, "is just a pointless statement.""""\n'),
            ("literal-four-apostrophe", "str = ''''That,' she said, 'is still pointless.''''\n"),
        ):
            with self.subTest(case=name):
                if TOMLLIB is not None:
                    TOMLLIB.loads(text)  # the input really is valid TOML
                config = self.root / f"{name}.toml"
                config.write_text(text, encoding="utf-8")
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    self.assertFalse(workflow_hook_config.has_inline_hooks(config))

    def test_fallback_reports_impossible_quote_run_as_invalid_toml(self) -> None:
        """Fixing the run rule must not let six-plus quotes answer a confident bool.

        A body character is never an unescaped quote and the runs around the
        delimiter are capped at two, so six adjacent quotes cannot occur: it is
        provable damage, and a hook-shaped line after it must not win.
        """
        for name, text in (
            ("six-quotes", 'x = ["""a"""""", 1]\n'),
            ("six-apostrophes", "x = ['''a'''''', 1]\n"),
            ("nine-quotes", 'x = ["""a"""""""""", 1]\n'),
            ("hook-after-run", 'x = """a""""""\nhooks.SessionEnd = []\n'),
            ("run-on-continuation-line", 'x = """\na""""""\n"""\n'),
        ):
            with self.subTest(case=name):
                if TOMLLIB is not None:
                    with self.assertRaises(TOMLLIB.TOMLDecodeError):
                        TOMLLIB.loads(text)
                config = self.root / f"{name}.toml"
                config.write_text(text, encoding="utf-8")
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    with self.assertRaises(workflow_hook_config.ConfigError):
                        workflow_hook_config.has_inline_hooks(config)

    def test_fallback_does_not_read_array_elements_as_table_headers(self) -> None:
        """REGRESSION: `["hooks"]` inside a multi-line array is an element, not `[hooks]`.

        The depth test has to gate the table-header regex as well, not only the
        branch that ends the root-table context. Over-detecting here makes the
        installer warn about inline hooks and default to skipping its own hook.
        """
        for name, text, expected in (
            ("nested-array-quoting-hooks", 'values = [\n  ["hooks"]\n]\n', False),
            ("inside-another-table", '[t]\nv = [\n  ["hooks"]\n]\n', False),
            ("element-then-feature-flag", 'v = [\n  ["hooks"]\n]\n[features]\nhooks = true\n', False),
            ("real-declaration-still-found", 'v = [\n  ["hooks"]\n]\nhooks.SessionEnd = []\n', True),
        ):
            with self.subTest(case=name):
                config = self.root / f"{name}.toml"
                config.write_text(text, encoding="utf-8")
                with mock.patch.object(workflow_hook_config, "tomllib", None):
                    self.assertEqual(workflow_hook_config.has_inline_hooks(config), expected)
                if HAS_TOMLLIB:
                    self.assertEqual(workflow_hook_config.has_inline_hooks(config), expected)

    def test_fallback_accepts_multiline_arrays_and_quoted_brackets(self) -> None:
        """The structure check must not turn valid TOML into a spurious error."""
        config = self.root / "nested.toml"
        config.write_text(
            "[mcp_servers.demo]\n"
            'args = [\n  ["a", "b"],  # a nested element line starting with [\n  "]",\n]\n'
            'label = "a \\" [ quoted bracket"\n'
            "[features]\nhooks = true\n",
            encoding="utf-8",
        )
        with mock.patch.object(workflow_hook_config, "tomllib", None):
            self.assertFalse(workflow_hook_config.has_inline_hooks(config))
        if HAS_TOMLLIB:
            self.assertFalse(workflow_hook_config.has_inline_hooks(config))


if __name__ == "__main__":
    unittest.main()
