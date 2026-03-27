---
name: web-security-review
description: "Perform security review for PHP backend + vanilla JS/jQuery/Svelte/HTMX frontend web applications. Use when: (1) user explicitly requests a security review or audit, (2) a new web feature is complete and needs security sign-off, (3) writing new authentication, file upload, form handling, or API endpoint code and want secure-by-default patterns. Produces severity-classified findings report."
---

# Web Security Review

Security review skill for PHP backend + vanilla JS / jQuery / Svelte / HTMX frontend stack.

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
5. **Write report**: Save to `security_review_report.md` (or user-specified location). Write in the same language the user used when requesting the review.
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

## Overrides

If the codebase intentionally bypasses a best practice for a documented reason, do not report it as a finding. Suggest adding a code comment explaining the exception.

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
