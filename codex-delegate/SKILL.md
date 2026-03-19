---
name: codex-delegate
description: "Delegate code review or implementation tasks to Codex CLI sub-agents. Trigger when user says '코덱스에게 검토해', '코덱스에게 구현시켜', 'codex로 리뷰해', 'codex로 만들어줘' or similar. For review: spawns 4 parallel sub-agents (2 code quality + 2 security). For implementation: splits work by frontend/backend or screen/function into parallel sub-agents. Always creates a context MD file in .agent-works/ to pass project context to Codex sessions that have no prior knowledge."
---

# Codex Delegate

Delegate code review or implementation to Codex CLI sub-agents. Because each Codex session starts fresh with no conversation history, always prepare a context file first.

## Step 0: Create Context File

Before dispatching any Codex agent, create a context MD file in the project's `.agent-works/` directory.

**Filename rule**: `YYYYMMDD-HHMMSS-{type}-{slug}.md` — timestamp + type + content description.
Use unique names to avoid conflicts when multiple tasks run concurrently or files are locked.

```
.agent-works/
  20260319-143022-review-user-login.md
  20260319-143055-implement-file-upload-api.md
  20260319-143055-implement-file-upload-frontend.md  ← parallel agents get separate files
```

**Context file template**:

```markdown
# Task: [review|implement] — [feature name]
**Date**: [YYYY-MM-DD HH:MM]
**Type**: [검토 / 구현]

## Project Overview
[Project description and tech stack: PHP + JS/Svelte/HTMX/jQuery, DB type, auth approach]

## Current State
[Summary of work done so far; list of recently changed files]

## Task Description
[Specific task for Codex: what to review OR what to implement]

## Relevant Files
[List of file paths that are in scope — be explicit]

## Constraints
[Coding conventions, files NOT to touch, naming rules, etc.]

## Tech Stack Details
- Backend: PHP (PDO, sessions, file uploads, ...)
- Frontend: [vanilla JS / jQuery / Svelte / HTMX — whichever applies]
- DB: [MySQL / MariaDB / ...]
- API response format: {"success": bool, "data": ..., "error": "..."}
```

Create one file per agent when dispatching parallel sub-agents.

---

## Mode 1: Review (검토)

Dispatch 4 Codex CLI sub-agents in parallel — 2 for code quality, 2 for security.

| Agent | Focus | Codex prompt |
|---|---|---|
| Quality-1 | Readability, structure, duplication | `"코드 품질 검토 (가독성·구조·중복): .agent-works/[file] 참조"` |
| Quality-2 | Performance, maintainability | `"코드 품질 검토 (성능·유지보수성): .agent-works/[file] 참조"` |
| Security-1 | PHP backend security | `"PHP 백엔드 보안 검토 (SQL injection·CSRF·세션·파일업로드): .agent-works/[file] 참조"` |
| Security-2 | Frontend JS/DOM security | `"프론트엔드 보안 검토 (XSS·DOM·토큰 노출): .agent-works/[file] 참조"` |

After all agents return, aggregate findings into a single review summary for the user. Group by severity: Critical → High → Medium → Low.

---

## Mode 2: Implement (구현)

Analyze the task scope and choose a split strategy:

| Split | When | Agents |
|---|---|---|
| Backend + Frontend | API spec confirmed, both sides independent | 2 agents |
| Layout + Logic | Single page, UI markup and JS are separable | 2 agents |
| Single | Simple task or cannot be split cleanly | 1 agent |

Each agent receives:
- Its own context file (separate file per agent)
- Explicit scope: which files to create/edit
- Hard constraint: "Do NOT touch files outside your scope"

After agents return, verify no file conflicts, then integrate.

---

## Codex CLI Invocation

```bash
# Non-interactive, auto-approve — suitable for sub-agent dispatch
codex --approval-mode full-auto "task description. Context: .agent-works/FILENAME.md"

# Interactive — suitable for review where output needs inspection
codex "task description. Context: .agent-works/FILENAME.md"
```

Pass the context filename explicitly in the prompt so Codex reads it at the start of its session.
