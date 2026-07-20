import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "workflow-reminder.py"
POWERSHELL_HOOK = ROOT / "hooks" / "workflow-reminder.ps1"


def run_hook(
    prompt: str,
    *,
    prompt_field: str = "user_prompt",
    raw_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = raw_input if raw_input is not None else json.dumps({prompt_field: prompt})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


class WorkflowReminderTest(unittest.TestCase):
    def reminder_context(self, prompt: str, *, prompt_field: str = "user_prompt") -> str:
        result = run_hook(prompt, prompt_field=prompt_field)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"],
            "UserPromptSubmit",
        )
        return output["hookSpecificOutput"]["additionalContext"]

    def assert_reminds(self, prompt: str) -> None:
        context = self.reminder_context(prompt)
        self.assertIn(
            "plan-and-build",
            context,
        )
        self.assertIn(
            "explicit user approval",
            context,
        )
        self.assertIn(
            "design approval",
            context,
        )

    def assert_silent(self, prompt: str) -> None:
        result = run_hook(prompt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def assert_only_workflow(self, prompt: str, expected: str) -> str:
        context = self.reminder_context(prompt)
        for workflow in (
            "plan-and-build",
            "evidence-first-review",
            "safe-checkpoint",
        ):
            if workflow == expected:
                self.assertIn(workflow, context)
            else:
                self.assertNotIn(workflow, context)
        return context

    def test_reminds_for_new_feature(self) -> None:
        self.assert_reminds("새 사용자 인증 기능을 구현해줘")

    def test_reminds_for_codex_prompt_field(self) -> None:
        context = self.reminder_context(
            "새 사용자 인증 기능을 구현해줘",
            prompt_field="prompt",
        )
        self.assertIn(
            "plan-and-build",
            context,
        )

    def test_reminds_for_new_project_with_multiple_scopes(self) -> None:
        self.assert_reminds("새 프로젝트를 만들고 API와 프론트엔드를 구현해줘")

    def test_reminds_when_new_project_wording_places_new_after_project(self) -> None:
        self.assert_reminds("프로젝트를 새로 작성해줘")

    def test_reminds_for_new_code_in_existing_tdd_project(self) -> None:
        self.assert_reminds("기존 TDD 프로젝트에 결제 기능 코드를 작성해줘")

    def test_reminds_for_multiple_independent_pages(self) -> None:
        self.assert_reminds("독립적인 페이지 3개를 각각 작성해줘")

    def test_skips_read_only_explanation(self) -> None:
        self.assert_silent("이 함수가 어떻게 동작하는지 설명해줘")

    def test_skips_review_of_an_existing_implementation(self) -> None:
        self.assert_silent("기존 인증 기능 구현을 검토해줘")

    def test_skips_ordinary_security_and_branch_reviews(self) -> None:
        for prompt in ("보안 검토해줘", "브랜치 리뷰해줘", "Review this pull request."):
            with self.subTest(prompt=prompt):
                self.assert_silent(prompt)

    def test_reminds_for_korean_explicit_read_only_review(self) -> None:
        context = self.assert_only_workflow(
            "컨텍스트 문서를 먼저 읽고 현재 파일과 원본 JSON을 읽기 전용으로 "
            "검토해줘. 수정하지 말고 반례도 확인해줘.",
            "evidence-first-review",
        )
        self.assertIn("do not modify", context)

    def test_reminds_for_english_explicit_read_only_review(self) -> None:
        context = self.assert_only_workflow(
            "Review how to implement a new authentication feature in read-only mode "
            "with no changes to any files.",
            "evidence-first-review",
        )
        self.assertIn("raw data", context)

    def test_reminds_for_english_without_changing_code_constraint(self) -> None:
        self.assert_only_workflow(
            "Review this implementation without changing any code.",
            "evidence-first-review",
        )

    def test_explicit_read_only_constraint_suppresses_plan_and_build(self) -> None:
        self.assert_only_workflow(
            "새 인증 기능 구현 계획을 검토해줘. 파일 수정 금지.",
            "evidence-first-review",
        )

    def test_reminds_when_review_also_requests_new_implementation(self) -> None:
        self.assert_reminds("현재 구조를 검토하고 새 인증 기능을 구현해줘")

    def test_reminds_when_english_review_requests_follow_up_implementation(self) -> None:
        self.assert_reminds(
            "Review the current structure, then implement a new authentication feature."
        )

    def test_skips_small_localized_edit(self) -> None:
        self.assert_silent("버튼 문구의 오타 한 글자만 수정해줘")

    def test_reminds_for_selective_commit_and_push(self) -> None:
        context = self.assert_only_workflow(
            "이번 요청에 해당하는 변경만 커밋하고 푸시해줘.",
            "safe-checkpoint",
        )
        self.assertIn("authorization", context)

    def test_reminds_for_natural_selective_commit_variants(self) -> None:
        for prompt in (
            "이 변경만 커밋해줘.",
            "src/a.py만 커밋해줘.",
            "Commit these changes only.",
            "Commit only src/a.py.",
        ):
            with self.subTest(prompt=prompt):
                self.assert_only_workflow(prompt, "safe-checkpoint")

    def test_skips_plain_commit_request_without_checkpoint_intent(self) -> None:
        self.assert_silent("변경사항을 커밋해줘.")

    def test_reminds_for_handoff_and_resume_request(self) -> None:
        self.assert_only_workflow(
            "퇴근 전 체크포인트를 남기고 집에서 이어서 할 수 있도록 "
            "인수인계 문서를 갱신해줘.",
            "safe-checkpoint",
        )

    def test_reminds_for_english_checkpoint_request(self) -> None:
        self.assert_only_workflow(
            "Create a safe checkpoint and handoff so I can resume this work tomorrow.",
            "safe-checkpoint",
        )

    def test_skips_simple_leaving_message(self) -> None:
        self.assert_silent("오늘은 퇴근합니다.")

    def test_skips_checkpoint_and_handoff_explanations(self) -> None:
        for prompt in (
            "체크포인트가 무엇인지 설명해줘.",
            "인수인계 문서의 의미를 설명해줘.",
            "How does a checkpoint work? Just explain it.",
            "What does handoff mean?",
        ):
            with self.subTest(prompt=prompt):
                self.assert_silent(prompt)

    def test_combines_implementation_then_checkpoint_in_execution_order(self) -> None:
        context = self.reminder_context(
            "새 인증 기능을 구현하고 검증한 다음 해당 변경만 커밋하고 "
            "집에서 이어서 할 인수인계를 남겨줘."
        )
        plan = context.index("plan-and-build")
        checkpoint = context.index("safe-checkpoint")
        self.assertLess(plan, checkpoint)
        self.assertNotIn("evidence-first-review", context)

    def test_malformed_input_is_non_blocking(self) -> None:
        result = run_hook("", raw_input="not-json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_non_object_json_inputs_are_non_blocking(self) -> None:
        for raw_input in ("[]", '"prompt"', "null"):
            with self.subTest(raw_input=raw_input):
                result = run_hook("", raw_input=raw_input)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_non_string_prompts_are_non_blocking(self) -> None:
        for prompt in ([], {}, 42, True):
            with self.subTest(prompt=prompt):
                result = run_hook(
                    "",
                    raw_input=json.dumps({"user_prompt": prompt}),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_powershell_hook_matches_python_fixtures_when_available(self) -> None:
        executable = shutil.which("pwsh") or shutil.which("powershell.exe")
        if executable is None:
            self.skipTest("PowerShell runtime is not available in this environment")

        fixtures = (
            {"user_prompt": "새 사용자 인증 기능을 구현해줘"},
            {"prompt": "Review the existing implementation without changing code."},
            {"user_prompt": "이 변경만 커밋해줘."},
            {
                "user_prompt": "새 인증 기능을 구현하고 해당 변경만 커밋할 "
                "체크포인트를 남겨줘."
            },
            {"user_prompt": "버튼 문구의 오타 한 글자만 수정해줘"},
            {"user_prompt": "체크포인트가 무엇인지 설명해줘."},
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                payload = json.dumps(fixture, ensure_ascii=False)
                python_result = subprocess.run(
                    [sys.executable, str(HOOK)], input=payload, text=True,
                    capture_output=True, check=False,
                )
                powershell_result = subprocess.run(
                    [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(POWERSHELL_HOOK)],
                    input=payload, text=True, capture_output=True, check=False,
                )
                self.assertEqual(powershell_result.returncode, 0, powershell_result.stderr)
                self.assertEqual(
                    json.loads(powershell_result.stdout) if powershell_result.stdout else None,
                    json.loads(python_result.stdout) if python_result.stdout else None,
                )


if __name__ == "__main__":
    unittest.main()
