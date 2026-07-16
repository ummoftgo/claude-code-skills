import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "workflow-reminder.py"


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
    def assert_reminds(self, prompt: str) -> None:
        result = run_hook(prompt)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"],
            "UserPromptSubmit",
        )
        self.assertIn(
            "plan-and-build",
            output["hookSpecificOutput"]["additionalContext"],
        )
        self.assertIn(
            "explicit user approval",
            output["hookSpecificOutput"]["additionalContext"],
        )
        self.assertIn(
            "design approval",
            output["hookSpecificOutput"]["additionalContext"],
        )

    def assert_silent(self, prompt: str) -> None:
        result = run_hook(prompt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_reminds_for_new_feature(self) -> None:
        self.assert_reminds("새 사용자 인증 기능을 구현해줘")

    def test_reminds_for_codex_prompt_field(self) -> None:
        result = run_hook("새 사용자 인증 기능을 구현해줘", prompt_field="prompt")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn(
            "plan-and-build",
            output["hookSpecificOutput"]["additionalContext"],
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

    def test_skips_read_only_review_report_writing(self) -> None:
        self.assert_silent("새 기능을 읽기 전용으로 검토하고 리뷰 보고서를 작성해줘")

    def test_skips_english_read_only_implementation_review(self) -> None:
        self.assert_silent(
            "Review how to implement a new authentication feature without changing any code."
        )

    def test_reminds_when_review_also_requests_new_implementation(self) -> None:
        self.assert_reminds("현재 구조를 검토하고 새 인증 기능을 구현해줘")

    def test_reminds_when_english_review_requests_follow_up_implementation(self) -> None:
        self.assert_reminds(
            "Review the current structure, then implement a new authentication feature."
        )

    def test_skips_small_localized_edit(self) -> None:
        self.assert_silent("버튼 문구의 오타 한 글자만 수정해줘")

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


if __name__ == "__main__":
    unittest.main()
