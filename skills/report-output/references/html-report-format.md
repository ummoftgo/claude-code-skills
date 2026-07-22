# HTML Report Format

Format rules for human-readable HTML reports. Synthesized from Thariq Shihipar's "The Unreasonable Effectiveness of HTML" (Anthropic Claude Code team, 2026-05), the community `html-artifacts` skills that operationalized it, and format benchmarks. The purpose of an HTML report is **agent-to-human** communication: a person should understand, evaluate, and act on the content faster than they would reading the same content as Markdown.

Keep the canonical data in Markdown/JSON when agents must re-read it later — HTML is the presentation layer, not the archive.

---

## 1. Hard constraints — single self-contained file

| Constraint | Reason |
|---|---|
| One `.html` file per report | Double-click to open anywhere; trivially shareable |
| All CSS in one `<style>` tag | Works offline; no external stylesheets |
| All JS in one `<script>` tag, vanilla JS only | No CDN, no React/Vue/Tailwind/Bootstrap, no build step |
| Diagrams as inline SVG | No `<img src>` to external files; SVG scales and themes |
| Images (if unavoidable) as `data:` URIs | No external file references |
| `<meta charset="utf-8">` + `<meta name="viewport" ...>` + `<title>` | Consistent rendering; the title names the report |
| CSP meta tag (see below) | Defense in depth: blocks network exfiltration even if malicious content slips through escaping |
| No network requests of any kind | No external fonts, analytics, iframes, fetch/XHR |
| Target ≤ 500 KB | Keeps generation and load fast; forces selectivity |

URLs may appear only as visible documentation links (`<a href>`) for the reader to click — never as resource loads.

Required CSP meta tag (in `<head>`, kept from the template):

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-<hash-of-inline-script>'; img-src data:; form-action 'none'; base-uri 'none'">
```

Why each directive matters:

- `script-src 'sha256-…'` pins the report's **own** inline script by hash. An injected `<script>` (escaping failure) has a different hash and will not execute. Never use `script-src 'unsafe-inline'` — it would run injected scripts too, defeating the defense. Recompute the hash after *any* script edit (command in SKILL.md Step 3B).
- `form-action 'none'` — `form-action` does not fall back to `default-src`, so without it a DOM-built `<form>` could POST report content to an external host. `base-uri 'none'` blocks `<base>` hijacking of relative URLs.
- `default-src 'none'` + `img-src data:` block every network fetch, frame, and beacon; only inline CSS (`style-src 'unsafe-inline'` — accepted residual risk, styles cannot exfiltrate under `default-src 'none'`) and `data:` images render.

## 1.5 Escaping untrusted content — mandatory

Everything that originates outside the report generator is untrusted: source code, diffs, tool/agent output, commit messages, log lines, user-supplied data. A code snippet containing `</code></pre><script>…` would otherwise break out of its container and execute in the reader's browser.

- HTML-escape all untrusted text before inserting it into markup: `&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`.
- Attribute values: escape **both** quote kinds (`"`→`&quot;`, `'`→`&#39;`), write attributes **double-quoted only** — never single-quoted or unquoted (a single-quoted attribute lets a `x' hidden data-x='` payload escape containment without any CSP or scan error) — and never build attribute *names* from untrusted input.
- Raw (unescaped) markup is allowed only for content the generator authored itself: layout, SVG diagrams, badges.
- Never place untrusted text inside `<script>`, inline event handlers (`onclick=` etc.), `style` attributes, or `href`/`src` values.
- Visual forgery (Trojan Source, [UTS #55](https://www.unicode.org/reports/tr55/)): in untrusted text, replace bidirectional and invisible control characters — `U+061C`, `U+200E`, `U+200F`, `U+202A`–`U+202E`, `U+2066`–`U+2069`, plus `U+200B`/`U+FEFF` inside code evidence — with their visible code-point form (e.g. the six characters `\u202E`) and add a warning note beside the affected block. Ordinary RTL letters (Arabic, Hebrew, …) are content and stay untouched. These control characters make the rendered order differ from the logical order, so a reader misjudges what code actually does; escaping, CSP, the containment scan, and a clean browser load all miss them — only this replacement rule catches them, and it survives into the Copy-as-Markdown output automatically since the copy serializes the rendered DOM text.
- Self-test: after generation, an evidence block that literally contains `</pre><script>alert(1)</script>` must *render as visible text*, not execute; an attribute payload containing both `"` and `'` must stay inside its attribute; a `U+202E` payload must appear as the visible text `\u202E`. If you cannot confirm these, re-check every insertion point.

## 2. Document structure

Order the document for a reader who will scan once, top to bottom:

1. **Header** — report title, generation date/time, scope line (branch, files, period), and meta badges (e.g., finding counts by severity).
2. **Executive summary card** — 2–4 sentences: what was examined, headline result, recommended action. Visually distinct (bordered/tinted card). A reader who stops here must still leave with the verdict.
3. **Navigation** — required when there are more than 3 sections: a sticky table of contents (sidebar on wide screens, collapsible on narrow) or a tab bar. Every section gets an `id` anchor.
4. **Body sections** — ordered by importance (Critical → Low, conclusion → supporting detail), never by discovery order.
5. **Appendix** — raw data (tool/agent output verbatim *except the mandatory secret/PII masking and bidi/invisible control-character replacement* — see the skill's common rules and §1.5) inside `<details>` so it exists without dominating. Escaped like all untrusted content (§1.5).
6. **Footer** — generator note naming the **actual client** that produced the report (e.g. "Generated by Claude Code · report-output skill" or "Generated by Codex · report-output skill" — never hardcode a client the run didn't use; omit the client name if it cannot be determined), source references, timestamp.

### Findings (review-type reports)

Render each finding as a card, not a heading-paragraph blob:

- Left border + badge colored by severity; severity is also written as text (never color alone).
- One-line title, then labeled rows: **Location** (`file:line`, monospace), **Evidence** (code block, ≤ 3 lines, secrets masked), **Impact** (one sentence), **Recommendation**.
- Repeated metadata (validation status, category) as small chips, not prose.
- With > ~8 findings, add severity filter buttons (show/hide by class toggle).

### Code and diffs

- `<pre><code>` with `overflow-x: auto` on the container — the page body must never scroll horizontally.
- Diffs: color added/removed lines via per-line classes (green/red tints that also work in dark mode), line numbers in a non-selectable gutter so copy-paste yields clean code. Keep gutters and any other decoration **outside the `<code>` node** (as sibling elements inside `<pre>`): the Copy-as-Markdown export serializes only the single `<code>` node, so anything inside it is treated as evidence.
- Long snippets (> ~30 lines) go inside `<details>`.

### Diagrams

Use inline SVG for flows, architectures, timelines, and comparisons — never ASCII art. Rules: `viewBox` for scaling, `currentColor`/CSS variables for strokes and fills so dark mode works, readable text labels (≥ 12px equivalent), and a caption under the figure. If a diagram would exceed ~200 SVG elements, simplify the diagram instead of shipping a poster.

## 3. Visual design

- **Theme via CSS variables** on `:root`, with a dark palette under `@media (prefers-color-scheme: dark)`. Every color in the document comes from a variable — no hardcoded hex in components.
- **Severity palette** (both themes, text readable at WCAG AA):
  - Critical `--sev-critical` (red family) · High (orange) · Medium (amber) · Low/Info (slate/blue).
- **Typography**: system font stack (`system-ui, -apple-system, 'Segoe UI', sans-serif`; monospace stack for code). Base 16px, line-height ≥ 1.6, content column `max-width` 72–80ch centered.
- **Responsive**: flexbox/grid; cards stack on narrow screens; tables and code scroll inside their own `overflow-x: auto` wrapper; `max-width: 100%` on media.
- **Restraint**: one accent color plus the severity palette. No gradients-everywhere, no animation except subtle hover/expand transitions. The design goal is scannability, not spectacle.

## 4. Interactivity — progressive, closed-loop

Add interactivity only when it reduces reading effort, in this order of preference:

1. **`<details>/<summary>`** for collapsing — free, no JS, degrades perfectly.
2. **Tabs / severity filters** — small vanilla JS class toggles.
3. **Copy-as-Markdown export** — a button that serializes the report's key content (summary + findings) to Markdown and copies it to the clipboard. This is the closed loop: the human reads HTML, the excerpt pasted back to an agent is Markdown. Every report with findings should have it. Serialization rules:
   - Code/diff evidence: serialize the **single `<code>` node's** `textContent` into a fenced block — leading newlines, trailing spaces, and interior blank lines are preserved byte-for-byte; nothing is trimmed. One exception is forced by CommonMark itself: a fenced block re-parses with exactly one final newline regardless of the original (0 or ≥2 cannot be represented), so the export separates the trailing-newline run and appends an explicit `(EOF 개행 N개)` marker outside the fence whenever N ≠ 1 — lossless by annotation instead of silently misparsed. The generator writes evidence immediately after `<code>` with no layout newline; layout newlines or gutters directly under `<pre>` are outside `<code>` and therefore never exported. If a `<pre>` doesn't contain exactly one `<code>`, emit a visible structure warning in the export instead of silently guessing. Extend the fence when the content itself contains backtick runs.
   - Prose fields and titles: collapse whitespace **and escape Markdown/GFM control characters** (`\` `` ` `` `*` `_` `[` `]` `<` `>` `|` `!` `&` `#` `~` — `~` covers GFM strikethrough), **and neutralize GFM autolinks** (`://` → `\://`, `www.` → `www\.`, `@` → `\@`) so bare URLs and e-mail addresses that were inert text in the HTML don't become clickable links in the copied excerpt. Without this, text that was safely escaped in the HTML (`<img …>`, `<!--`, `[link]`, `~~struck~~`, `https://attacker…`) re-activates as raw HTML/Markdown downstream and can hide, forge, or link out content.
   - On clipboard failure, show the generated Markdown in a real modal — native `<dialog>` + `showModal()` (browser-provided focus trap, `aria-modal`, Escape) with focus returned to the invoking button on close. A button-label change alone is not a fallback.
4. **Keyboard**: `Escape` closes any open overlay; arrow keys only for deck-style reports.

Anything beyond this (sliders, drag-and-drop editors, live re-rendering) belongs to a purpose-built artifact, not a report — ask the user before escalating.

## 5. Accessibility & correctness checklist

Before delivering, verify:

- [ ] Semantic tags (`<header> <nav> <main> <section> <footer>`), heading levels descend without gaps.
- [ ] Severity conveyed by text label as well as color.
- [ ] All untrusted content HTML-escaped (§1.5) and the CSP meta tag present.
- [ ] Contrast meets WCAG AA (≥ 4.5:1) for every text/background pair, both themes — badges included. When you add or change colors, compute it (relative luminance `L`, ratio `(L1+0.05)/(L2+0.05)`) with a quick node/python snippet instead of eyeballing; the template's shipped palette is pre-verified.
- [ ] No live external references: run the triage scan from SKILL.md Step 3B (case-insensitive; resource attributes, embedding elements, `meta refresh`, `url(`, `@import`, network APIs) and classify every match by source context — live markup/script/CSS matches are blockers unless they are `#` anchors, visible doc links, or `data:` URIs; matches inside escaped evidence text are data and stay.
- [ ] CSP `script-src` hash matches the current inline script (recompute after any script edit, with CRLF→LF normalization — see SKILL.md Step 3B).
- [ ] Opens with zero console errors, **zero CSP violation reports, zero extra network requests, and no navigation** (final URL still the file after ~3 s; DOM contains no parsed `meta[http-equiv=refresh]` — entity-encoded variants decode at parse time — and no `<base>`) — this browser load is the authoritative self-containment check; CSP alone does not block top-level navigation. Load it once via `web-browser-preview` or agent-browser when available. With untrusted content embedded, the §1.5 fixture renders as text — nothing executes, nothing submits.
- [ ] All numbers/claims match the source data — the HTML step must not silently rewrite findings.

## 6. Anti-patterns

- ASCII/unicode diagrams inside HTML — use SVG.
- Dumping a Markdown report inside `<pre>` and calling it HTML.
- External fonts, icon CDNs, framework CDNs — breaks offline/self-contained rule.
- Dark-mode-blind SVG (black strokes on dark background).
- Interactive controls with no export path back to text.
- Padding sections with boilerplate to look complete — an honest short report beats a padded long one.

## 7. Sources

- Anthropic blog — [Using Claude Code: The unreasonable effectiveness of HTML](https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html) (use cases, why HTML for human review)
- Community skills operationalizing it: `dogum/html-artifacts`, `luopeixiang/html-artifacts` (self-contained + closed-loop export + dark mode rules), `notque/vexjoy-agent` html-artifact (hard constraints table, 500 KB cap)
- Format benchmarks (why Markdown stays the archive format): gallon.me Opus 4.7 HTML-vs-MD test; Beam.ai / FormatArc token analyses
