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
# Auto-detect base branch: main → master → develop
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
if [ -z "$BASE" ]; then
  BASE=$(git branch -r | grep -E 'origin/(main|master|develop)' | head -1 | xargs | sed 's|origin/||')
fi
if [ -z "$BASE" ]; then
  echo "ERROR: Could not detect base branch. Please specify manually."
  exit 1
fi

CURRENT=$(git rev-parse --abbrev-ref HEAD)
echo "Base: $BASE  →  Current: $CURRENT"
echo ""
echo "Changed files:"
git diff --name-only --diff-filter=ACMR "$BASE"...HEAD
```

`--diff-filter=ACMR` excludes deleted files (D) — no point reviewing removed code.

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
- Review ONLY the files listed in your scope.
- NEVER modify any file under any circumstances.
- Do NOT submit intermediate status updates — return your full findings in a single response when done.
- Do not review files in isolation. Read related files to understand the full process flow before judging.
- For Svelte components: read the entire component before flagging lifecycle or store issues.
  The $store reactive syntax auto-unsubscribes — never flag it as a leak.
  Only flag manual .subscribe() calls that lack onDestroy cleanup.
```

---

### Agent A — Backend Quality Reviewer

**Persona**: You are a senior PHP backend developer with 10 years of experience. You care deeply about maintainable, performant, well-structured PHP code.

**Skill to use**: Load and follow `~/.claude/skills/code-quality-review/SKILL.md` and its reference file `references/php-quality.md`. Execute the skill's workflow (run CLI tools, then manual review) scoped to the files below.

**Scope**: Backend files from Step 1 (PHP, composer.json).

**Prompt template**:
```
You are a senior PHP backend developer (10 years experience) conducting a backend code quality review.

[Paste Common Instructions above]

Load and follow: ~/.claude/skills/code-quality-review/SKILL.md (php-quality.md reference)

Your scope — review ONLY these files:
[list of backend files]

Git diff for your scope:
[git diff output for backend files]

Pay special attention to:
- N+1 query patterns across the request lifecycle
- Evaluation order: cheap guards before expensive DB/file operations
- Duplicated query logic that may indicate missing abstraction
- PHPStan level (check phpstan.neon first; fall back to level 5 only if absent)

Return a structured quality report following the code-quality-review report format.
Include file:line references for every finding.
```

---

### Agent B — Security Reviewer

**Persona**: You are a web application security expert specializing in OWASP Top 10 vulnerabilities, with deep knowledge of PHP backend and JavaScript frontend attack surfaces.

**Skill to use**: Load and follow `~/.claude/skills/web-security-review/SKILL.md` and both its reference files (`references/php-backend-security.md`, `references/web-frontend-security.md`).

**Scope**: ALL changed files (Backend + Frontend + Style + Config).

**Prompt template**:
```
You are a web application security expert (OWASP Top 10 specialist) conducting a full-stack security review.

[Paste Common Instructions above]

Load and follow: ~/.claude/skills/web-security-review/SKILL.md (both reference files)

Your scope — review ALL of these changed files:
[complete list of all changed files]

Git diff for your scope:
[git diff output for all files]

Pay special attention to:
- New input entry points (forms, API endpoints, file uploads) introduced in this diff
- Authentication and session changes
- Any secrets, tokens, or credentials that may have been accidentally committed
- Config file changes that affect security posture (.env, *.json with API keys)
- Trust boundary changes: what data crosses from user-controlled to server-controlled

Return a security report following the web-security-review report format.
Classify each finding as Critical / High / Medium / Low.
Include file:line references and evidence snippets for every finding.
```

---

### Agent C — Frontend Quality Reviewer

**Persona**: You are a senior frontend developer specializing in Svelte, jQuery, and HTMX with 8 years of experience building complex interactive UIs.

**Skill to use**: Load and follow `~/.claude/skills/code-quality-review/SKILL.md` and its reference files `references/js-quality.md` (especially Section 7 on Svelte lifecycle) and `references/css-quality.md`.

**Scope**: Frontend + Style files from Step 1.

**Prompt template**:
```
You are a senior frontend developer (Svelte / jQuery / HTMX specialist, 8 years experience) conducting a frontend code quality review.

[Paste Common Instructions above]

Load and follow: ~/.claude/skills/code-quality-review/SKILL.md (js-quality.md and css-quality.md references)

Your scope — review ONLY these files:
[list of frontend and style files]

Git diff for your scope:
[git diff output for frontend/style files]

Pay special attention to:
- Svelte reactive declarations vs manual subscriptions (see js-quality.md Section 7)
- DOM query caching and event delegation patterns
- CSS specificity escalation and magic numbers
- HTMX polling vs event-driven patterns
- Component data flow: understand the full component lifecycle before flagging issues

Return a structured quality report following the code-quality-review report format.
Include file:line references for every finding.
```

---

## Step 3: Wait for All Reviewers

Wait until all three agents have returned their complete reports. Do not prompt them for interim updates.

If a reviewer has no files in their scope (e.g., no backend files changed), skip that agent and note it in the final report.

---

## Step 4: Team Leader Cross-Validation

After all reports are received, cross-validate **Critical and High** findings:

**For security findings** — re-run the audit grep patterns from `web-security-review/references/`:
```bash
# SQL injection
grep -rn "query\s*(\s*[\"'].*\$" --include="*.php" <changed_files>
grep -rn "\.\s*\$_(GET|POST|REQUEST|COOKIE)" --include="*.php" <changed_files>

# XSS
grep -rn "echo\s\+\$\|print\s\+\$" --include="*.php" <changed_files>
grep -rn "innerHTML\s*=" --include="*.js" --include="*.svelte" <changed_files>

# Other patterns as applicable from the reference files
```

**For quality findings** — re-run relevant grep patterns from `code-quality-review/references/`:
```bash
# N+1 / query inside loop
grep -rn "foreach\|for " --include="*.php" -A3 <changed_files> | grep -i "query\|prepare\|execute"

# Manual Svelte subscribe without onDestroy
grep -rn "\.subscribe(" --include="*.svelte" <changed_files>
```

Mark each Critical/High finding:
- `✓ Cross-validated` — grep confirmed the pattern exists
- `⚠ Needs verification` — could not confirm via grep (may require runtime analysis)

---

## Step 5: Produce Consolidated Report

Save the report to: `branch_review_<branch-name>_<YYYYMMDD>.md`

```
# Branch Review Report
**Date**: [date]
**Branch**: [current-branch] vs [base-branch]
**Changed files reviewed**: N (Backend: X | Frontend: Y | Style: Z | Config: W)
**Reviewers**: Backend Quality · Security · Frontend Quality

## Executive Summary
[2–3 sentences: overall quality and security posture, most critical findings, merge recommendation]

---

## Critical / High Findings  ← Fix before merging
### [CH-1] Finding Title
- **Type**: Security | Quality — Backend | Frontend
- **Location**: `path/to/file.php:42`
- **Evidence**: `[code snippet from diff]`
- **Impact**: [one sentence: what can go wrong]
- **Recommendation**: [specific direction — no code, no modifications]
- **Validation**: ✓ Cross-validated | ⚠ Needs verification

---

## Medium Findings
### [M-1] ...

---

## Low / Informational
### [L-1] ...

---

## Passed Checks
[Security controls and quality patterns correctly implemented in this diff]

---

## Reviewer Detail Reports

### Backend Quality Reviewer
[Agent A full report]

### Security Reviewer
[Agent B full report]

### Frontend Quality Reviewer
[Agent C full report]
```
