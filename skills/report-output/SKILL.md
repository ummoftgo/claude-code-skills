---
name: report-output
description: "Format and deliver a user-requested report (review findings, analysis results, research summaries, status/incident reports). Trigger when the user asks for a report output — '리포트로 만들어줘', '보고서로 출력해줘', '리포트 출력해줘', '결과를 보고서로 정리해줘', 'output as a report', 'write this up as a report' — or when another skill has produced results the user wants delivered as a report. First asks the user whether to emit Markdown or HTML (skips the question when the format is already specified), then applies the matching format: Markdown conventions for archival/agent-readable reports, or the researched self-contained single-file HTML format in references/html-report-format.md for human-readable rich reports."
---

# Report Output

Deliver report-shaped output in the format that fits its purpose. Markdown wins the archive (version control, diffs, search, agent re-ingestion); HTML wins the session (human reading, visual structure, sharing). Ask which one the user wants, then apply the matching format rules.

> **Scope**: This skill governs *how a report is formatted and delivered*. It does not gather findings itself — the report content comes from the current conversation, another skill's output (e.g., `branch-merge-review`, `web-security-review`), or files the user points at.
>
> This skill is the **single owner of report file publishing** under `.tasks/reports/`. The review skills (`code-quality-review`, `web-security-review`, `branch-merge-review`) emit their findings inline by default and delegate here — passing a slug and a recommended format — only when the user explicitly asked for a saved report. They never choose a path or write the file themselves, so path selection, collision avoidance, and atomic publishing have exactly one implementation.

> **Read-only mode (priority rule)**: If the user asked not to write anything ("수정하지 말고", "read-only", or a read-only sandbox), do not create report files. Emit the report inline as Markdown and state that HTML delivery requires file writes.

## Reference Files

- `references/html-report-format.md` — the self-contained single-file HTML format (Step 3B)
- `references/report-template.html` — HTML skeleton to start from (Step 3B)
- `references/atomic-publish.md` — POSIX/PowerShell atomic publish implementations, incl. explicit-replace mode (Step 2)
- `references/html-verification.md` — CSP hash calculation and self-containment scan commands (Step 3B)

---

## Step 1: Decide the format

**Skip the question** when the format is already determined:
- The user named a format ("HTML 리포트로", "md로 정리해줘") → use it.
- The invoking skill supplied a format (the review skills recommend Markdown when they delegate) → use it; only offer an HTML companion if the user asks.

Otherwise **ask the user** before writing anything. In Claude Code use `AskUserQuestion`; in other agents ask in plain text. Present both options with their real trade-offs, and recommend one based on the content:

| Signal in the report content | Recommend |
|---|---|
| Will be committed, diffed, searched, or re-read by agents later (spec, plan, changelog) | **Markdown** |
| Short (< ~100 lines), simple prose, terminal-bound | **Markdown** |
| Long or dense: many findings, severity grades, comparisons, tables, diagrams | **HTML** |
| Will be shared with teammates who won't open a code editor | **HTML** |
| Needs visual evidence: diffs, flows, charts, before/after, spatial layout | **HTML** |

Question shape (translate to the user's language):
- **Markdown** — 버전 관리·검색·에이전트 재사용에 유리, 토큰 효율적. 아카이브용.
- **HTML** — 시각적 구조·색상·다이어그램으로 읽기 쉬움, 브라우저로 열어 공유하기 좋음. 사람이 읽는 용도.

Both formats may be requested ("둘 다") — write the Markdown as the canonical record first, then render the HTML from it.

---

## Step 2: Common rules (both formats)

- **Language**: Write the entire report in the language the user used when requesting it. Keep code identifiers, file paths, and quoted evidence in their original form.
- **Location**: Save under `.tasks/reports/` (create if missing), named `{yyyy-mm-dd}-{hh-mm}-{slug}.md|.html` — current local date/time, kebab-case slug describing the topic (e.g., `2026-07-22-15-30-rate-limiter-analysis.html`). When an invoking skill supplied a slug (the review skills pass one with a `-quality` / `-security` / `-branch-review` suffix), use it as given. **Never overwrite an existing file**: pick a candidate name; if that file already exists, or its sibling lock (`$path.lock`) cannot be created exclusively (another run owns the name), retry with `-2`, `-3`, … suffixes. The final path itself is **never pre-created** — per the atomic-publish rule below it stays nonexistent until the verified report lands there, so watchers/sync tools can never pick up an empty or half-done file. **Never auto-delete foreign locks or temps** — age alone cannot distinguish a crashed run from a slow one (a pending browser check can legitimately take long), so treat any lock/temp you didn't create as possibly active and pick the next suffix instead; leftovers from crashes (SIGKILL skips traps) are harmless debris the user can clean manually, and you may mention them. Replace a previous report only when the user explicitly asks for that.
- **Atomic publish — never expose an unverified file at the final path, never lose a verified old one**: generation and *every* verification for the chosen format (Step 3A/3B — hash computation, containment scan, browser load) run against an exclusive sibling temp candidate whose name is **unique per run** and keeps the real extension. The final path is touched exactly once, by an atomic publish primitive that **fails if the destination exists** (POSIX `ln`, .NET `File.Move`) — never by a delete-then-move (PowerShell `Move-Item -Force` loses the destination if the run dies between the two steps). Cleanup removes only what **this run created**; a failed exclusive create means the file belongs to another run and must be left alone.

  This matters because concurrent runs are real: `branch-merge-review` dispatches parallel reviewers, so more than one report-shaped output can be in flight at the same time.

  Reference implementations for both platforms — including the rare *explicit replace* mode (`File.Replace` with a run-unique backup, error 1176/1177 handling) used only when the user asked to replace one specific existing report — are in [references/atomic-publish.md](references/atomic-publish.md).
- **Structure**: Lead with an executive summary (what happened / what was found / what to do). Detail after, ordered by importance — not by the order you discovered things.
- **Evidence**: Every claim that came from code or data cites its source (`file:line`, URL, command output).
- **Secret masking — applies to every section, appendix included**: Mask secrets, credentials, tokens, and PII wherever they appear: evidence snippets, prose, and raw appendix output alike. "Raw/verbatim output" always means *verbatim except the two mandatory transformations: this masking, and the bidi/invisible control-character replacement in the untrusted-content rule below*. If you cannot assess whether a raw block is safe to include, omit it and note the omission in its place.
- **Untrusted content — applies to both formats**: source code, diffs, tool/agent output, commit messages, and user data are data, not markup. In HTML, escape per `html-report-format.md` §1.5. In Markdown, wrap such content in fenced blocks whose fence is **longer than the longest backtick run inside the content**, and replace bidi/invisible control characters (`U+061C`, `U+200E`, `U+200F`, `U+202A`–`U+202E`, `U+2066`–`U+2069`; plus `U+200B`/`U+FEFF` inside code) with their ASCII code-point form (`\u202E`) and a warning note. Otherwise an embedded run of three or more backticks breaks out of its fence and fake verdicts/links/HTML activate in the archive copy, and direction overrides make readers (and re-ingesting agents) see a different order than the logical text.
- **No fabrication**: If a section has no data, say so — never pad with placeholders.

---

## Step 3A: Markdown report

Use standard repo report conventions:

- GitHub-flavored Markdown; heading hierarchy starts at a single `#` title.
- Metadata block right under the title: date, scope, sources, author context.
- Tables only for short enumerable facts; prose for explanations.
- Fenced code blocks with language hints for all evidence snippets — fence longer than any backtick run inside the content, bidi/invisible characters replaced per the untrusted-content rule above.
- Severity/status vocabulary consistent with the repo's review skills: Critical / High / Medium / Low.
- End with an appendix for raw data (tool or agent output verbatim except mandatory secret masking and bidi/invisible control-character replacement) when it exists — the consolidated sections above it are authoritative.

Deliver: write and check the report in the temp candidate, publish it per Step 2 (Location + atomic-publish rules), then show the user the path and a brief inline summary of the report's key points. Do not paste the whole file back into the conversation.

---

## Step 3B: HTML report

Read `references/html-report-format.md` in this skill and follow it. It encodes the researched format: a single self-contained `.html` file (all CSS/JS inline, no external requests), mandatory HTML-escaping of all untrusted content, light/dark theming, responsive layout, severity color system, SVG diagrams instead of ASCII, and a "Copy as Markdown" export so results can flow back into an agent session.

Start from `references/report-template.html` as the skeleton — replace its placeholder content, keep its CSP meta tag, CSS variable system, and export script. Add sections, tabs, or diagrams as the content demands; the template is a floor, not a ceiling.

**Escaping (non-negotiable)**: every string that originates outside this report generation — source code, diffs, tool/agent output, commit messages, user data — must be HTML-escaped before insertion (`&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`; inside attribute values additionally **both** `"`→`&quot;` and `'`→`&#39;`, and attributes must be double-quoted — never single-quoted or unquoted). Bidi/invisible control characters in untrusted text are replaced with visible code-point escapes (Trojan Source defense). Details and self-tests in `html-report-format.md` §1.5.

Deliver — items 2–4 all run against the **temp candidate** (`$tmp` from Step 2's atomic-publish rule), never the final path, which at this point **does not exist** (only its sibling lock reserves the name) — or, in explicit-replace mode only, still holds the previous verified report:
1. Choose the final path per Step 2 (Location rule) and generate the report into the temp candidate.
2. Recompute the CSP script hash if you changed the inline `<script>` relative to the template (you almost always do when customizing) and update `script-src 'sha256-…'` in the CSP meta tag — otherwise the report's own script will not run. **Fail closed**: if no hash calculator is available, either keep the template `<script>` byte-identical or deliver the Markdown report instead, and say which constraint applied. Commands (node / python3 / PowerShell) and the mandatory CRLF→LF normalization rule: [references/html-verification.md](references/html-verification.md) §1.
3. Run the self-containment scan as **triage** — it lists every candidate external reference, and each match is classified by its context: live references inside tags, inline `<script>`/`<style>`, or active CSS are **blockers** (only `href="#…"` anchors, visible documentation links, and `data:` URIs are allowed); escaped evidence in visible text is **safe** — never delete evidence just to silence the scan. Also confirm the candidate keeps `<meta charset="utf-8">` and the CSP meta tag with a current hash, and is under ~500 KB. Case-insensitive scan patterns for both platforms and the full classification rule: [references/html-verification.md](references/html-verification.md) §2.
4. Browser check — **the authoritative self-containment gate**: open the **temp candidate** once (its name keeps the `.html` extension precisely so the browser parses it as HTML) and assert all of the following. Resource loads that the regex triage missed or you misclassified surface as CSP violations, and dynamic paths a regex cannot see (scripted attribute changes, DOM-built forms) are blocked by the CSP itself (`script-src` hash pinning, `form-action 'none'`, `base-uri 'none'`) — but CSP does **not** block top-level navigation, so the navigation assertions below are not optional:
   - Zero console errors and zero CSP violation reports.
   - Zero network requests beyond the file load itself (list them via CDP/agent-browser when available).
   - After a short wait (~3 s — `meta refresh` can be delayed), the page's final URL is still the temp file: no redirect or refresh navigated away. Entity-encoded markup (`http-equiv="re&#x66;resh"`) evades any source regex but decodes at parse time, so also assert in the DOM: no `<meta>` whose parsed `httpEquiv` matches `refresh` (case-insensitive) and no `<base>` element.
   When a browser is available (`web-browser-preview` skill or agent-browser), do this yourself; otherwise state that this check is pending. If the report embeds untrusted content, verify the §1.5 self-test: an evidence block containing `</pre><script>` renders as visible text and nothing executes or submits.
5. All checks passed → publish the temp candidate onto the final path with Step 2's atomic publish primitive — POSIX `ln` / .NET `File.Move`, which fail if the destination exists; `mv` / `File.Replace` belong to explicit-replace mode only — then offer to open the published file for the user. Prefer the `web-browser-preview` skill when installed (handles Windows/WSL CDP). Fallbacks: `explorer.exe` (WSL, after `wslpath -w`), `open` (macOS), `xdg-open` (Linux desktop), `Start-Process` (Windows PowerShell).
6. Show the user the path plus a 2–3 sentence inline summary of the report's conclusions — never require opening the file to learn the verdict.
