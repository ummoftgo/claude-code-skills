---
name: branch-merge-review
description: "Review all changes between the current branch and main/master before merging. Trigger when user says '브랜치 리뷰해줘', '머지 전에 리뷰해줘', 'PR 리뷰해줘', 'branch review', 'merge review', or similar. Spawns 3 parallel reviewers — backend quality, full-stack security, and frontend quality — each using the appropriate installed skill (code-quality-review or web-security-review). The team leader waits for all reviewers to finish, then cross-validates Critical/High findings using grep audit patterns before producing a consolidated report. Reviewers NEVER modify code — findings only."
---

# Branch Merge Review

Review all diff changes against main/master using a 3-person parallel reviewer team. Produces a consolidated report with cross-validated findings.

---

## Step 1: Collect Changed Files

Run the following to detect the base branch and list changed files:

```bash
# Auto-detect base branch: explicit priority — main → master → develop
BASE=""
for candidate in origin/main origin/master origin/develop main master develop; do
  if git show-ref --verify --quiet "refs/remotes/${candidate}" 2>/dev/null || \
     git show-ref --verify --quiet "refs/heads/${candidate}" 2>/dev/null; then
    BASE="${candidate#origin/}"
    break
  fi
done
if [ -z "$BASE" ]; then
  echo "ERROR: Could not detect base branch. Please specify manually (e.g., 'review against staging')."
  exit 1
fi

CURRENT=$(git rev-parse --abbrev-ref HEAD)
echo "Base: $BASE  →  Current: $CURRENT"

# Changed files for quality reviewers (exclude deleted — no point reviewing removed code)
CHANGED_QA=$(git diff --name-only --diff-filter=ACMR "$BASE"...HEAD)
# Changed files for security reviewer (include deleted — removed guards/checks are findings too)
CHANGED_SEC=$(git diff --name-only --diff-filter=ACMRD "$BASE"...HEAD)

echo ""
echo "Changed files (quality scope): $CHANGED_QA"
echo "Changed files (security scope): $CHANGED_SEC"

# Early exit if nothing to review
if [ -z "$CHANGED_SEC" ]; then
  echo "No changed files detected. Nothing to review."
  exit 0
fi
```

- Quality reviewers (A/C) receive `CHANGED_QA` — excludes deleted files (nothing to check in removed code).
- Security reviewer (B) receives `CHANGED_SEC` — includes deleted (`D`): a removed CSRF check, auth guard, or sanitizer is itself a security finding.

Categorize the file list:

| Category | Extensions / Filenames |
|----------|------------------------|
| **Backend** | `*.php`, `composer.json`, `composer.lock` |
| **Frontend** | `*.js`, `*.ts`, `*.svelte`, `*.html` |
| **Style** | `*.css`, `*.scss`, `*.sass` |
| **Config** | `*.json`, `*.yaml`, `*.yml`, `*.env*`, `*.ini` |

If no files match a category, skip the corresponding reviewer's scope (but the Security reviewer always reviews everything).

---

## Step 2: Dispatch 3 Reviewers in Parallel

Dispatch all three agents **in a single message** (parallel Agent tool calls). Do not wait for one before starting the others.

Supply each agent with:
- Their specific file list (from Step 1 categorization)
- Their persona and skill instructions
- The git diff content for their files: `git diff "$BASE"...HEAD -- <file_list>`

### Common Instructions (embed in every agent prompt)

```
You are conducting a READ-ONLY code review. Your constraints are absolute:
- NEVER modify any file under any circumstances.
- Do NOT write any report file to disk.
- Do NOT offer or apply fixes — findings and recommendations only.
- Do NOT submit intermediate status updates — return your full findings in a single response when done.
- You may read files outside your scope to understand context and process flow.
  However, report ONLY findings whose primary location is within your scoped files.
- For Svelte components: read the entire component before flagging lifecycle or store issues.
  The $store reactive syntax auto-unsubscribes — never flag it as a leak.
  Only flag manual .subscribe() calls that lack onDestroy cleanup.
```

---

### Agent A — Backend Quality Reviewer

**Persona**: You are a senior PHP backend developer with 10 years of experience. You care deeply about maintainable, performant, well-structured PHP code.

**Skill to use**: Load and follow `~/.claude/skills/code-quality-review/SKILL.md` and its reference file `references/php-quality.md`. Use only the audit/review steps — do not run the "Offer Fixes" step.

**Scope**: Backend files from Step 1 (PHP, composer.json, composer.lock).

**Prompt template**:
```
You are a senior PHP backend developer (10 years experience) conducting a backend code quality review.

[Paste Common Instructions above]

Workspace root: [absolute path to project root]
Base branch: [BASE]  Current branch: [CURRENT]

Load and follow: ~/.claude/skills/code-quality-review/SKILL.md (php-quality.md reference).
Use only Steps 1–4 (detect stack → run CLI tools → manual review → report).
Skip Step 5 (Offer Fixes) — this is a read-only review.

Your scope — report findings only for these files:
[list of backend files]

If only composer.json/composer.lock changed: review for newly added/upgraded dependencies
with known vulnerabilities or major version jumps. Run CLI tools on the full project but
report only findings that overlap with the scoped files.

Git diff for your scope:
[git diff "$BASE"...HEAD -- <backend files>]

Pay special attention to:
- N+1 query patterns across the request lifecycle
- Evaluation order: cheap guards before expensive DB/file operations
- Duplicated query logic that may indicate missing abstraction
- PHPStan level (check phpstan.neon first; fall back to level 5 only if absent)

For each finding include: Severity (High / Medium / Low), Category, file:line, evidence snippet.
Return a structured quality report following the code-quality-review report format.
```

---

### Agent B — Security Reviewer

**Persona**: You are a web application security expert specializing in OWASP Top 10 vulnerabilities, with deep knowledge of PHP backend and JavaScript frontend attack surfaces.

**Skill to use**: Load and follow `~/.claude/skills/web-security-review/SKILL.md` and both its reference files (`references/php-backend-security.md`, `references/web-frontend-security.md`). Use only the audit steps — do not run "Offer to Fix".

**Scope**: ALL changed files including deleted (Backend + Frontend + Style + Config + Deleted).

**Prompt template**:
```
You are a web application security expert (OWASP Top 10 specialist) conducting a full-stack security review.

[Paste Common Instructions above]

Workspace root: [absolute path to project root]
Base branch: [BASE]  Current branch: [CURRENT]

Load and follow: ~/.claude/skills/web-security-review/SKILL.md (both reference files).
Use only the audit/review steps. Skip the "Offer to Fix" step — this is a read-only review.

Your scope — review ALL of these changed files (including deleted):
[complete list from CHANGED_SEC]

Git diff for your scope (includes deleted file context):
[git diff "$BASE"...HEAD -- <all changed files including deleted>]

Pay special attention to:
- Deleted files: a removed CSRF check, auth guard, input sanitizer, or CSP header is itself a finding
- New input entry points (forms, API endpoints, file uploads) introduced in this diff
- Authentication and session changes
- Any secrets, tokens, or credentials that may have been accidentally committed
- Config file changes that affect security posture (.env, *.json with API keys)
- Trust boundary changes: what data crosses from user-controlled to server-controlled

Return a security report following the web-security-review report format.
Use "Recommendation:" instead of "Fix:" for each finding (this output feeds a consolidated report, not direct fixing).
Classify each finding as Critical / High / Medium / Low.
Include file:line references and evidence snippets (max 3 lines; mask any secrets) for every finding.
```

---

### Agent C — Frontend Quality Reviewer

**Persona**: You are a senior frontend developer specializing in Svelte, jQuery, and HTMX with 8 years of experience building complex interactive UIs.

**Skill to use**: Load and follow `~/.claude/skills/code-quality-review/SKILL.md` and its reference files `references/js-quality.md` (especially Section 7 on Svelte lifecycle) and `references/css-quality.md`. Use only the audit/review steps — do not run "Offer Fixes".

**Scope**: Frontend + Style files from Step 1 (JS, TS, Svelte, HTML, CSS, SCSS, SASS).

**Prompt template**:
```
You are a senior frontend developer (Svelte / jQuery / HTMX specialist, 8 years experience) conducting a frontend code quality review.

[Paste Common Instructions above]

Workspace root: [absolute path to project root]
Base branch: [BASE]  Current branch: [CURRENT]

Load and follow: ~/.claude/skills/code-quality-review/SKILL.md (js-quality.md and css-quality.md references).
Use only Steps 1–4 (detect stack → run CLI tools → manual review → report).
Skip Step 5 (Offer Fixes) — this is a read-only review.

Your scope — report findings only for these files:
[list of frontend and style files]

Git diff for your scope:
[git diff "$BASE"...HEAD -- <frontend/style files>]

Pay special attention to:
- Svelte reactive declarations vs manual subscriptions (js-quality.md Section 7)
  — read the entire component before flagging; $store syntax auto-unsubscribes
- TypeScript and plain HTML changes: type safety, DOM attribute correctness, HTMX attribute safety
- DOM query caching and event delegation patterns
- CSS specificity escalation and magic numbers
- HTMX polling vs event-driven patterns

For each finding include: Severity (High / Medium / Low), Category, file:line, evidence snippet.
Return a structured quality report following the code-quality-review report format.
```

---

## Step 2.5: Scope Decision Table

Before dispatching, decide which agents to spawn:

| Condition | Action |
|-----------|--------|
| Backend files == 0 | Skip Agent A; note "No backend changes" in report |
| Frontend + Style files == 0 | Skip Agent C; note "No frontend changes" in report |
| All changed files == 0 | Abort: "No changed files to review" |
| Agent B (Security) | Always spawn — reviews all changed files including deleted |

---

## Step 3: Wait for All Reviewers

Wait until all spawned agents have returned their complete reports. Do not prompt them for interim updates.

**Failure handling**:
- If an agent does not respond within a reasonable time, note it as `⚠ Reviewer did not complete` in the final report and proceed with partial findings.
- If an agent returns an error, retry once. If it fails again, mark that reviewer as unavailable.
- Never block the entire report waiting for one reviewer indefinitely.

---

## Step 4: Team Leader Cross-Validation

After all reports are received:

**4a. Normalize quality finding severity** — Agent A/C reports use category-based format, not severity grades. Before cross-validating, assign each quality finding a severity:
- **High**: N+1 queries, broken auth logic, data corruption risk
- **Medium**: Eval-order issues, non-trivial duplication, performance anti-patterns in hot paths
- **Low**: Style inconsistencies, dead code, redundant comments

**4b. Cross-validate Critical and High findings** — run grep against the implicated file(s) only (not the whole project). For each finding, select the matching pattern family:

**Security patterns** (from `web-security-review/references/`):
```bash
# SQL injection
grep -rn "query\s*(\s*[\"'].*\$" --include="*.php" <implicated_files>
grep -rn "\.\s*\$_(GET|POST|REQUEST|COOKIE)" --include="*.php" <implicated_files>

# XSS
grep -rn "echo \$_(GET|POST|REQUEST|COOKIE|SERVER)" --include="*.php" <implicated_files>
grep -rn "innerHTML\s*=" --include="*.js" --include="*.svelte" <implicated_files>

# CSRF — check for missing token validation on state-changing endpoints
grep -rn "\$_POST\[" --include="*.php" <implicated_files> | grep -v "csrf"

# Session security
grep -rn "session_start" --include="*.php" <implicated_files>
grep -rn "session_regenerate_id" --include="*.php" <implicated_files>

# File upload
grep -rn "move_uploaded_file\|\$_FILES" --include="*.php" <implicated_files>

# Hardcoded secrets
grep -rn "password\s*=\s*['\"][^'\"]\+['\"]" --include="*.php" --include="*.js" <implicated_files>
grep -rn "api_key\|secret_key\|access_token" --include="*.env*" --include="*.json" <implicated_files>

# Frontend sinks
grep -rn "\.html(\|\.append(\|\.prepend(" --include="*.js" <implicated_files>
grep -rn "{@html" --include="*.svelte" <implicated_files>
grep -rn "localStorage\|sessionStorage" --include="*.js" --include="*.svelte" <implicated_files>
```

**Quality patterns** (from `code-quality-review/references/`):
```bash
# N+1 / query inside loop (use as signal; confirm manually — 3-line window misses service calls)
grep -rn "foreach\|for " --include="*.php" -A3 <implicated_files> | grep -i "query\|prepare\|execute"
grep -rn "for.*count(" --include="*.php" <implicated_files>
grep -rn "SELECT \*" --include="*.php" <implicated_files>

# Manual Svelte subscribe without cleanup
grep -rn "\.subscribe(" --include="*.svelte" <implicated_files>

# CSS issues
grep -rn "!important" --include="*.css" --include="*.scss" <implicated_files>
```

**4c. Mark each Critical/High finding**:
- `✓ Pattern corroborated` — grep confirmed the suspicious pattern in the file
- `✓ Manually confirmed` — reviewed in context; vulnerability/bug confirmed
- `⚠ Needs runtime/architectural verification` — grep inconclusive or pattern is absence-based (e.g., missing CSRF check); cannot confirm via static analysis alone

---

## Step 5: Produce Consolidated Report

Save the report to: `branch_review_<branch-name>_<YYYYMMDD>.md`

```
# Branch Review Report
**Date**: [date]
**Branch**: [current-branch] vs [base-branch]
**Changed files reviewed**: N (Backend: X | Frontend: Y | Style: Z | Config: W | Deleted: D)
**Reviewers**: [Backend Quality ·] Security [· Frontend Quality]  ← omit skipped reviewers

## Executive Summary
[2–3 sentences: overall quality and security posture, most critical findings]

**Recommendation**: Block merge | Merge after fixes | Ready to merge
**Blocking items**: [CH-1, H-2, ...] | None
**Findings**: Critical: N · High: N · Medium: N · Low: N  |  Validated: N · Needs verification: N

## Review Coverage
- Files reviewed: [list or count by category]
- Skipped reviewers: [e.g., "Agent A — no backend files changed"]
- Excluded from quality scope: [deleted files, if any]

---

## Critical / High Findings  ← Fix before merging
### [CH-1] Finding Title
- **Type**: Security | Quality — Backend | Frontend
- **Location**: `path/to/file.php:42`
- **Evidence**: `[1–3 lines from diff; mask any secrets]`
- **Impact**: [one sentence: what can go wrong]
- **Recommendation**: [specific direction — no code, no modifications]
- **Validation**: ✓ Pattern corroborated | ✓ Manually confirmed | ⚠ Needs runtime/architectural verification

---

## Medium Findings
### [M-1] ...

---

## Low / Informational
### [L-1] ...
(Omit this section if empty)

---

## Passed Checks
[Up to 5 security controls or quality patterns correctly implemented in this diff that increase merge confidence]

---

## Open Questions / Follow-up
[For each ⚠ Needs verification finding: one line describing what to verify and how]

---

## Appendix: Raw Reviewer Reports
> The consolidated sections above are authoritative. These are the unedited reviewer outputs for reference.

### Backend Quality Reviewer
[Agent A full report — or "Skipped: no backend files changed"]

### Security Reviewer
[Agent B full report]

### Frontend Quality Reviewer
[Agent C full report — or "Skipped: no frontend files changed"]
```
