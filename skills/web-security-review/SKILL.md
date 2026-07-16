---
name: web-security-review
description: "Perform security review for PHP backend + vanilla JS/jQuery/Svelte/HTMX frontend web applications. Use when: (1) user explicitly requests a security review or audit, (2) a new web feature is complete and needs security sign-off, (3) writing new authentication, file upload, form handling, or API endpoint code and want secure-by-default patterns. Produces severity-classified findings report."
---

# Web Security Review

Security review skill for PHP backend + vanilla JS / jQuery / Svelte / HTMX frontend stack.

> **Read-only mode (priority rule).** If the user asked to review **without changing anything** ("수정하지 말고", "read-only", or a read-only sandbox), do not write to the workspace: **do not create the report file** under `.tasks/reports/` and **do not install** any tooling. Emit the full report **inline** in your response instead. Write files only when the user has not restricted writes.

## Reference Files

Load these before proceeding:
- `references/php-backend-security.md` — PHP backend vulnerability checklist and secure patterns
- `references/web-frontend-security.md` — Frontend (vanilla JS, jQuery, Svelte, HTMX) security checklist

Read **both** files when reviewing a full-stack feature. Read only the relevant file when reviewing backend-only or frontend-only code.

## Operating Modes

### 1. Secure-by-default generation (passive)
While writing new PHP or frontend code, follow all MUST requirements from the reference files without being asked. Flag if a requested implementation would violate a critical rule.

### 2. Passive review (always on)
While editing existing code, notice and mention critical or high-severity violations in touched or nearby code.

### 3. Active audit (explicit request)
When the user asks for a security review, scan, or audit:
1. Load both reference files
2. Systematically check each category against the codebase
3. Produce a full written report (see Report Format below)

## Workflow for Active Audit

1. **Identify scope**: What files/features are in scope? Ask if unclear.
2. **Read references**: Load `references/php-backend-security.md` and/or `references/web-frontend-security.md`.
3. **Scan codebase**: Search for patterns listed in the reference files. Use Grep for sinks, dangerous functions, and missing protections.
4. **Classify findings**: Assign severity (Critical / High / Medium / Low) per the reference file guidance.
5. **Write report**: Save to `.tasks/reports/{yyyy-mm-dd}-{hh-mm}-{slug}-security.md`. Create `.tasks/reports/` if it does not exist. Slug is a short kebab-case identifier from the user's request or target scope (e.g., `file-upload`, `user-login`). Write in the same language the user used when requesting the review. **When running as a subagent** (e.g., dispatched by branch-merge-review), the invoking prompt's `OUTPUT LANGUAGE` directive takes precedence over the prompt's own language — an English dispatch prompt does NOT mean the report should be in English. Keep code identifiers, file paths, and evidence snippets as-is; write all prose in the designated language. **(Read-only mode: skip writing the file — emit the report inline instead.)**
6. **Summarize**: Report findings to the user inline in the same language, offer to fix.

## Report Format

Write the report as a Markdown file with this structure:

```
# Security Review Report
**Date**: [date]
**Scope**: [files/features reviewed]

## Executive Summary
[2-3 sentence overview of overall security posture and most critical findings]

## Critical Findings
### [C-1] Finding Title
- **Location**: `path/to/file.php:42`
- **Evidence**: `[code snippet]`
- **Impact**: [one sentence: what an attacker can do]
- **Fix**: [specific code change]

## High Findings
### [H-1] ...

## Medium Findings
### [M-1] ...

## Low / Informational
### [L-1] ...

## Passed Checks
[Brief list of security controls that are correctly implemented]
```

## Overrides — Documented Intent

If a comment at the flagged line or on the enclosing function explicitly acknowledges the flagged behavior as intentional (states the why — e.g., `// 의도적으로 캐시 미적용: 실시간성 필요`, `// Security: rate-limited at nginx level`), do **not** report it at normal severity. **Downgrade it to Low / Informational**, keep it in the report, and cite the comment as the reason (mark it `문서화된 의도` / documented intent). Do not silently drop it — the reader should still see it once.

**Non-downgradable classes** — report at full severity even when a comment claims the behavior is intentional:
- Injection of any kind (SQL, command, LDAP, template, header)
- XSS, CSRF, SSRF, path traversal / file inclusion
- Secrets or internal-information exposure (hardcoded keys/credentials, internal data returned to clients, verbose errors leaking internals)
- Authentication/authorization bypass, privilege escalation, tenant-isolation breaks
- Remote code execution, unsafe deserialization, exploitable file upload
- Data loss/corruption or irreversible destructive operations (including race/idempotency defects with irreversible effects)

For these, note the comment's existence in the finding ("주석으로 의도가 명시되어 있으나 위험도가 높아 심각도 유지") but keep the original severity.

**Comment relevance**: the comment must address the specific flagged risk or behavior. A generic or unrelated nearby comment does not qualify. If behavior looks intentional but has no comment, report at normal severity and recommend adding an explanatory comment.

## Fixes

After the user reads the report, offer to fix findings one at a time. Start with Critical, then High. When fixing:
- Keep changes minimal — fix the vulnerability without refactoring unrelated code
- Add a short comment: `// Security: [reason] per security review`
- Run any configured tests after each fix
- Do not bundle unrelated findings into one commit

**After each fix, verify the patch was applied correctly:**
1. Re-run the grep pattern from the reference file for that specific vulnerability (e.g., the SQL injection audit pattern).
2. Confirm the vulnerable pattern no longer appears in the fixed file(s).
3. If any instance remains, fix before moving to the next finding.
