# Consolidated Report Template

Structure for the team leader's consolidated output (SKILL.md Step 5). The same structure is used whether the report is emitted inline (default) or handed to `report-output` for file delivery.

`(feature/label)` below is the readable form of a finding identifier, owned by the `readable-ids` skill: full form on first mention in the report — the blocking-items line and each finding heading — and the bare identifier everywhere after that. When `readable-ids` is not installed, keep a short label in the same position anyway; a recheck later refers to these findings by number from a different document.

```
# Branch Review Report
**Date**: [date]
**Branch**: [current-branch] vs [base-branch]
**Changed files reviewed**: N (Backend: X | Frontend: Y | Style: Z | Config: W | Deleted: D)
**Execution**: Direct review | Team review
**Reviewers**: [lead or actual child names, with quality/security responsibilities; do not invent independent reviewers]
**Cross-model**: Codex completed | Codex skipped — [reason] | Codex incomplete — single-model review

## Executive Summary
[2–3 sentences: overall quality and security posture, most critical findings]

**Review completeness**: [per language/surface — `PHP: reviewed` · `Browser JS/CSS: reviewed` · `Node: reviewer did not complete` · `Go: no reference, unreviewed`]
**Recommendation**: Block merge | Merge after fixes | Ready to merge
  ↳ `Ready to merge` requires all applicable quality passes and every security reference selected
    for the actual changes to be reviewed (SKILL.md Step 3, including the browser-assets-only exception).
**Blocking items**: [CH-1(feature/label), H-2(feature/label), ...] | None
**Findings**: Critical: N · High: N · Medium: N · Low: N  |  Validated: N · Needs verification: N · Cleared: N

## Review Coverage
- Files reviewed: [list or count by category]
- Completed passes: [language/surface, quality/security references, lead or child reviewer]
- Skipped reviewers: [e.g., "PHP quality — no PHP files changed"]
- Excluded from quality scope: [deleted files, if any]

---

## Critical / High Findings  ← Fix before merging
### [CH-1(feature/label)] Finding Title
- **Type**: Security | Quality — Backend | Frontend
- **Location**: `path/to/file.php:42`
- **Source**: Claude + Codex | Claude | Codex
- **Evidence**: `[1–3 lines from diff; mask any secrets]`
- **Impact**: [one sentence: what can go wrong]
- **Recommendation**: [specific direction — no code, no modifications]
- **Context trace**: [entry point → … → sink as `file:line` hops; or `⚠ 방어 확인 불가` and what would settle it]
- **Validation**: ✓ Manually confirmed | ⚠ Needs runtime/architectural verification (± ✓ Pattern corroborated)

---

## Medium Findings
### [M-1(feature/label)] ...

---

## Low / Informational
### [L-1(feature/label)] ...
(Omit this section if empty)

---

## Cleared
[Critical/High candidates traced and found defended on every path, one line each: the candidate and the defence `file:line`. Those reported at Low as `주의: 다른 층에서 방어됨` are listed here too.]
(Omit this section if empty)

---

## Passed Checks
[Up to 5 security controls or quality patterns correctly implemented in this diff that increase merge confidence]

---

## Cross-Model Agreement
[Omit when Codex did not complete. Findings both models raised; findings only one raised, with any downgrade or dismissal reason; explicit disagreements and how they were decided]

---

## Open Questions / Follow-up
[For each ⚠ Needs verification finding: one line describing what to verify and how]

---

## Appendix: Raw Reviewer Reports
In direct mode, include only the Codex report; no child reports were produced. Omit the appendix when neither exists.
> The consolidated sections above are authoritative. These are the unedited reviewer outputs for reference.

### Backend Quality Reviewer
[Per-language quality reports — or "Skipped: no files changed for this language"]

### Security Reviewer
[Security reviewer full report]

### Frontend Quality Reviewer
[Frontend quality report — or "Skipped: no frontend files changed"]

### Codex Cross-Model Reviewer
[Codex report — or the skip/incomplete reason]
```
