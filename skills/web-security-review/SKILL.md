---
name: web-security-review
description: "Perform security review for application backends and frontends — PHP, Python, and Node.js (HTTP services, CLIs, daemons, libraries) plus the browser surface (vanilla JS, jQuery, Svelte, HTMX). Use when: (1) user explicitly requests a security review or audit, (2) a new web feature is complete and needs security sign-off, (3) writing new authentication, file upload, form handling, API endpoint, CLI, or child-process code and want secure-by-default patterns. A language with no reference here is reported as unreviewed rather than checked against another language's rules. Produces severity-classified findings report. Do not use for a pre-merge review of a whole branch or PR (use branch-merge-review, which dispatches this skill as its security reviewer) or for a non-security quality review (use code-quality-review)."
---

# Web Security Review

Security review skill for web application backends and frontends. References are split by
**language** (PHP, Node) and by **surface** (HTTP server, browser, native) — load one of each
that applies.

## Platform command selection

Use `rg` for audit searches on both POSIX and Windows whenever available. If it is missing, use the documented `grep` expressions on POSIX and translate them to `Get-ChildItem -Recurse -Filter <pattern> | Select-String -Pattern <regex>` on Windows PowerShell. Do not require Bash for a Windows-native review.

> **Read-only mode (priority rule).** If the user asked to review **without changing anything** ("수정하지 말고", "read-only", or a read-only sandbox), do not write to the workspace: **do not install** any tooling, **do not modify code**, and **do not change worktree or Git state**. No file may be written, report files included — inline output is the default anyway (Workflow steps 5–6), and under this constraint it is the only option even if the user asks for a file; say that a report file needs write permission.

## Reference Files

References are organised on **two axes**. Load the language axis for the backend in scope, plus
**every surface** that backend actually exposes — a package that serves HTTP and installs a CLI
needs both surface files.

| Axis | File | Covers |
|---|---|---|
| Language | `references/php-backend-security.md` | PHP language rules **and** its HTTP surface (see the exception below) |
| Language | `references/node-security.md` | Node runtime APIs, deserialization, prototype pollution, dependencies, secrets |
| Language | `references/python-security.md` | Python runtime, deserialization, SQL, templates, crypto, dependencies, secrets |
| Surface | `references/http-server-security.md` | Auth, session, CSRF, authorization, upload, headers, CORS, response exposure |
| Surface | `references/browser-security.md` | DOM sinks, CSP, client storage, framework-specific XSS |
| Surface | `references/native-security.md` | CLI/daemon: invocation trust, filesystem, temp files, child processes, privilege |

**PHP is a deliberate exception.** `php-backend-security.md` predates this split and carries its
language rules and HTTP-surface rules together. For a PHP change load that file and **not**
`http-server-security.md` — loading both double-reports the same findings. Splitting PHP is
scheduled work, not a precondition: the main stack should not be the first to try an unproven
structure.

### Selecting references from the surface

`branch-merge-review` Step 1 decides the surface per workspace (`browser` / `http-server` /
`native`) and passes it in. When this skill runs standalone, infer it the same way — from the
manifest and the entry points — and say which surfaces you assumed.

**The language axis is always loaded** — even for a change that touches only browser code, the
package manifest and lockfile belong to the language, and that is where supply-chain findings
live. Load **one language-axis file per changed language**, not one in total: a branch touching
PHP and Node loads both. Then add one surface file per surface in scope.

| Change | Language axis | Surface axis |
|---|---|---|
| PHP server-rendered app | `php-backend-security.md` | `browser-security.md` (it emits HTML) |
| PHP API, no HTML | `php-backend-security.md` | — |
| Node HTTP service | `node-security.md` | `http-server-security.md` |
| Node CLI or daemon | `node-security.md` | `native-security.md` |
| Node library with no surface evidence | `node-security.md` | **all three** — the consumer decides the surface and is not in this diff |
| Node service + CLI | `node-security.md` | `http-server-security.md` + `native-security.md` |
| Node static build (bundler, prerender) | `node-security.md` | `browser-security.md` + `native-security.md` — the build script itself runs in CI with repository write access |
| Node runtime SSR | `node-security.md` | `http-server-security.md` + `browser-security.md` |
| Node service that also serves a UI | `node-security.md` | `http-server-security.md` + `browser-security.md` |
| Node service + CLI + UI | `node-security.md` | all three |
| Python HTTP service (Django, FastAPI, Flask) | `python-security.md` | `http-server-security.md` |
| Python server-rendered app (templates) | `python-security.md` | `http-server-security.md` + `browser-security.md` |
| Python CLI, job, or daemon | `python-security.md` | `native-security.md` |
| Python library with no surface evidence | `python-security.md` | **all three** — the consumer decides the surface and is not in this diff |
| Browser assets only, no manifest change | — | `browser-security.md` |

**A build is code that runs.** A bundler or prerender config is not just a description of the output — it executes on a developer machine and in CI, reads the working directory, and
can run arbitrary plugins, so it carries the `native` surface alongside the browser output it produces. `native-security.md` is written for exactly that: build scripts and anything else that trusts its own working directory.

The last row is the only one without a language axis, and it is narrow on purpose: the moment a
`package.json`, lockfile, or build script is in the diff, `node-security.md` comes back.

**`php-backend-security.md` already covers the HTTP surface** — never pair it with
`http-server-security.md`. Every other language pairs its language file with surface files.

**If a changed file's language has no language-axis reference, report that language as
unreviewed and name the paths.** Do not substitute another language's rules — a PHP checklist
applied to Go produces confident findings about code it does not understand. Review the
languages that are covered and let the report show the gap.

## Operating Modes

### 1. Secure-by-default generation (passive)
While writing new backend or frontend code, follow all MUST requirements from the loaded reference files without being asked. Flag if a requested implementation would violate a critical rule.

### 2. Passive review (always on)
While editing existing code, notice and mention critical or high-severity violations in touched or nearby code.

### 3. Active audit (explicit request)
When the user asks for a security review, scan, or audit:
1. Determine the language and the surfaces in scope, then load **every reference the selection
   table above names for them** — one language axis file plus one file per surface. Two files is
   the common case, not the rule; a Node service that also ships a CLI and a UI loads four.
2. Systematically check each category against the codebase
3. Produce a full written report (see Report Format below), naming which references were loaded
   and any language reported as unreviewed

## Workflow for Active Audit

1. **Identify scope**: What files/features are in scope? Ask if unclear.
2. **Read references**: Load the language-axis file for each language in scope plus one file per surface, per the selection table above. Record which files you loaded — the report names them.
3. **Scan codebase**: Search for patterns listed in the reference files. Use Grep for sinks, dangerous functions, and missing protections.
4. **Classify findings**: Assign severity (Critical / High / Medium / Low) per the reference file guidance.
5. **Produce the report**: Follow the Report Format below. Write in the same language the user used when requesting the review. **When running as a subagent** (e.g., dispatched by branch-merge-review), the invoking prompt's `OUTPUT LANGUAGE` directive takes precedence over the prompt's own language — an English dispatch prompt does NOT mean the report should be in English. Keep code identifiers, file paths, and evidence snippets as-is; write all prose in the designated language.
6. **Deliver — inline by default**: Emit the report in your response. Do **not** create `.tasks/reports/` and do not write a report file: a review request must not change the working tree or add commit candidates. Then offer to fix.

**Writing a file requires an explicit request** — "리포트로 만들어줘", "보고서로 출력해줘", "리포트 파일로 저장해줘", "output as a report", or an equivalent explicit ask. In that case do not choose a path or write the file here — **delegate to the `report-output` skill** and pass the finished report body plus:

- **slug**: short kebab-case identifier from the user's request or target scope with the `-security` suffix — e.g. `file-upload-security`, `user-login-security`;
- **recommended format**: Markdown (mention HTML as an option only if the user asks).

`report-output` owns path selection, name-collision avoidance, and atomic publishing — this skill never writes under `.tasks/reports/` itself. If `report-output` is not installed, say so and keep the report inline rather than improvising a path.

## Report Format

Write the report in Markdown with this structure:

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
