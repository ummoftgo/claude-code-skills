# Web Parallel Dispatch — Pattern Reference

Full agent prompt templates and guidance for each dispatch pattern.

## Table of Contents
1. [API First Pattern](#1-api-first-pattern)
2. [Frontend Split Pattern](#2-frontend-split-pattern)
3. [Multi-Page Pattern](#3-multi-page-pattern)
4. [Full-Stack 3-Way Pattern](#4-full-stack-3-way-pattern)
5. [Shared Context Templates](#5-shared-context-templates)
6. [Common Mistakes](#6-common-mistakes)

---

## 1. API First Pattern

**When**: API specification (endpoints, request/response shapes) is complete. PHP backend and frontend can now implement their sides independently.

**Prerequisite**: Written API spec must exist before dispatching. If it doesn't, write it first.

**Agents**: Agent A (PHP backend) + Agent B (frontend) — dispatch in parallel.

### Agent A Prompt Template (PHP Backend)

> Before writing this prompt, if the `use-context7` skill is installed, invoke it to query relevant PHP/PDO docs.

```
Implement the PHP backend API endpoints described below.

## API Spec
[Paste full API spec — endpoints, HTTP methods, request params, response JSON shapes, error codes]

## Database Schema
[Paste relevant table definitions]

## Your scope
- Directory: api/[feature]/
- Do NOT touch frontend files (js/, svelte/, htmx templates, pages/)

## Requirements
- Use PDO prepared statements for all queries
- Return JSON: {"success": true, "data": {...}} on success, {"success": false, "error": "..."} on failure
- Validate all inputs server-side (type, length, format)
- Check CSRF token for POST/PUT/DELETE: hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'] ?? '')

## Deliverable
Return a summary listing:
1. Each endpoint file created
2. Any DB queries written
3. Any assumptions made about the spec
```

### Agent B Prompt Template (Frontend)

> Before writing this prompt, if the `use-context7` skill is installed, invoke it to query the relevant frontend framework docs (Svelte runes, HTMX attributes, jQuery patterns — whichever applies).

```
Implement the frontend UI for the feature below. The PHP backend API is being built in parallel — code against the spec, do not wait for it.

## API Spec
[Same spec as Agent A — identical copy]

## Your scope
- Files: [specify: e.g., js/feature.js + templates/feature.php for HTMX, or src/Feature.svelte]
- Do NOT touch PHP backend files (api/)

## Frontend stack for this feature: [Svelte / HTMX / jQuery / vanilla JS]

## Requirements
- Handle loading states and error responses from the API
- Include CSRF token in POST/PUT/DELETE requests:
  Read from <meta name="csrf-token"> → send as X-CSRF-Token header
- Use .text() / textContent for user-generated content — avoid .html() / innerHTML

## Deliverable
Return a summary listing:
1. Files created/modified
2. Any assumptions made about the API spec
3. UI states handled (loading, error, empty)
```

---

## 2. Frontend Split Pattern

**When**: A single page has substantial work in both HTML/CSS layout and JS behavior, and the two are clearly separable.

**Agents**: Agent A (layout) + Agent B (logic) — dispatch in parallel.

> Before writing Agent B's prompt, if the `use-context7` skill is installed, invoke it to query the frontend framework docs.

### Agent A Prompt Template (Layout)

```
Build the HTML/CSS layout for [feature name].

## Design requirements
[Describe the UI: sections, components, visual hierarchy, any existing CSS classes to follow]

## Your scope
- File: templates/[feature].php (or .svelte / .html)
- Produce semantic HTML with placeholder content (no real data needed yet)
- Add id and data-* attributes that Agent B (JS logic) will hook into:
  [List required hook points explicitly, e.g.:]
    - id="user-table-body" — tbody where rows will be injected
    - id="search-form" — form Agent B will attach submit handler to
    - data-user-id on each row — for click handlers
- Do NOT write JavaScript

## Deliverable
Return: file path, list of hook points created, any layout decisions made
```

### Agent B Prompt Template (Logic)

```
Implement the JavaScript logic for [feature name]. The HTML layout is being built in parallel — code against the hook points listed below.

## Hook points provided by layout agent
[List exact IDs and data-* attributes: id="user-table-body", id="search-form", data-user-id, etc.]

## API endpoints to call
[List endpoints, methods, request/response shapes]

## Your scope
- File: js/[feature].js (or inline script block in template)
- Do NOT modify the HTML structure

## Requirements
- Attach event listeners using the hook point IDs above
- Handle: loading state, API errors (4xx/5xx), empty results
- CSRF token:
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  // send as X-CSRF-Token header on mutations

## Deliverable
Return: file created, event handlers implemented, API calls made
```

---

## 3. Multi-Page Pattern

**When**: 2 or more independent pages/features need to be built. They share the DB schema and auth system but have no runtime dependency on each other.

**Rule**: One agent per page. Keep parallel agent count to 4–5 maximum.

> Before dispatching, if the `use-context7` skill is installed, invoke it once for each distinct framework used across the pages (e.g., once for Svelte if multiple pages use Svelte components).

### Shared Context Block (include in every agent prompt)

```
## Shared project context
- DB connection: require_once '../db.php'; // provides $pdo (PDO instance)
- Auth check: require_once '../auth.php'; // redirects to /login if not authenticated
- DB schema: [paste relevant tables]
- JSON response format: {"success": bool, "data": any} or {"success": false, "error": "string"}
- CSRF: validate with hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'] ?? '')
- Frontend stack: [Svelte / HTMX / jQuery / vanilla JS]
```

### Per-Page Agent Prompt Template

```
Implement the [Page Name] page.

[Paste shared context block above]

## Page-specific requirements
[Describe what this page does, what data it shows, what actions it supports]

## Files to create
- pages/[page-name].php — main page template
- api/[page-name]/ — API endpoints for this page (if needed)
- js/[page-name].js — frontend logic (if needed)

## Do NOT touch
- Other pages under pages/
- Shared files: db.php, auth.php, layout.php, header.php

## Deliverable
Summary of files created and any schema assumptions made.
```

---

## 4. Full-Stack 3-Way Pattern

**When**: Building a brand-new feature from scratch where the DB schema is not yet finalized.

> Before Phase 2, if the `use-context7` skill is installed, invoke it to query both backend (PDO/PHP) and frontend framework docs — Phase 2 agents implement against these APIs.

**Structure**:
```
Phase 1 (sequential): DB Agent designs and outputs schema
Phase 2 (parallel):   API Agent + Frontend Agent implement against the schema
```

Phase 2 agents CANNOT start until Phase 1 is complete. Dispatch Phase 2 only after reading Phase 1 output.

### Phase 1: DB Agent Prompt

```
Design the database schema for [feature name].

## Feature description
[Describe the feature and the data it needs to store]

## Existing tables (do not modify)
[List existing tables with key columns]

## Deliverable
1. SQL CREATE TABLE statements with appropriate indexes
2. Foreign key relationships
3. Sample data (3–5 rows per table) for testing
4. Brief rationale for key design decisions

Output the complete schema as a fenced SQL block.
```

### Phase 2a: API Agent Prompt (starts after Phase 1)

```
Implement PHP API endpoints for [feature name].

## DB Schema (finalized — from Phase 1)
[Paste Phase 1 SQL output here]

[Paste shared context block]

## Endpoints to implement
[List from API spec: method, path, request body, response shape]

## Your scope: api/[feature]/ directory only

## Deliverable: list of files created, endpoints implemented, edge cases handled
```

### Phase 2b: Frontend Agent Prompt (starts after Phase 1)

```
Implement the frontend for [feature name].

## DB Schema (for field name reference)
[Paste Phase 1 SQL output — helps agent match variable names to column names]

## API Spec
[List endpoints, request/response shapes]

[Paste shared context block]

## Your scope: templates/[feature].php, js/[feature].js

## Deliverable: files created, UI states handled (loading, error, empty, success)
```

---

## 5. Shared Context Templates

### Minimal shared context
```
DB: require '../db.php' → $pdo (PDO, emulate_prepares=false)
Auth: require '../auth.php' → redirects if unauthenticated
CSRF: $_SESSION['csrf_token'], validate with hash_equals()
JSON response: {"success": bool, "data": any, "error": string}
Frontend stack: [specify]
```

### Full shared context (complex projects)
```
## Architecture overview
[2–3 sentences describing the app]

## File layout
src/
├── api/          PHP API endpoints (one folder per resource)
├── pages/        PHP page templates
├── js/           Frontend JS (one file per page)
├── svelte/       Svelte components (if applicable)
├── db.php        PDO connection ($pdo)
├── auth.php      Auth guard (redirects to /login if unauthenticated)
└── helpers.php   Utility functions

## Conventions
- API: validate input → query DB → return JSON
- SQL: always prepared statements (PDO)
- HTML output: always htmlspecialchars($val, ENT_QUOTES, 'UTF-8')
- JS mutations: fetch with X-CSRF-Token header
```

---

## 6. Common Mistakes

**Agents editing the same file**: Most common with `layout.php`, `header.php`. Add explicit "Do NOT touch" lists for shared files in every agent prompt.

**API spec mismatch**: Backend names endpoint `/api/users/list`, frontend calls `/api/user/all`. Fix: write the spec before dispatching and paste the **identical** spec into both prompts.

**DB column name drift**: Frontend uses `userId`, API returns `user_id`, DB column is `id`. Fix: include the DB schema in all agent prompts so all agents see the actual column names.

**Missing error handling**: Agents implement happy path only. Fix: explicitly require in every prompt — "Handle: loading state, 4xx/5xx responses, empty results."

**Phase 2 started before Phase 1 finishes**: In the Full-Stack 3-Way pattern, always read Phase 1 output before dispatching Phase 2. Do not pre-dispatch them together.
