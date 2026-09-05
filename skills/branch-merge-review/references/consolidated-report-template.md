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

## Executive Summary
[2–3 sentences: overall quality and security posture, most critical findings]

**Review completeness**: [per language — `PHP: reviewed` · `Node: reviewer did not complete` · `Go: no reference, unreviewed`]
**Recommendation**: Block merge | Merge after fixes | Ready to merge
  ↳ `Ready to merge` requires every language with changed files to be `reviewed`.
**Blocking items**: [CH-1(feature/label), H-2(feature/label), ...] | None
**Findings**: Critical: N · High: N · Medium: N · Low: N  |  Validated: N · Needs verification: N

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
- **Evidence**: `[1–3 lines from diff; mask any secrets]`
- **Impact**: [one sentence: what can go wrong]
- **Recommendation**: [specific direction — no code, no modifications]
- **Validation**: ✓ Pattern corroborated | ✓ Manually confirmed | ⚠ Needs runtime/architectural verification

---

## Medium Findings
### [M-1(feature/label)] ...

---

## Low / Informational
### [L-1(feature/label)] ...
(Omit this section if empty)

---

## Passed Checks
[Up to 5 security controls or quality patterns correctly implemented in this diff that increase merge confidence]

---

## Open Questions / Follow-up
[For each ⚠ Needs verification finding: one line describing what to verify and how]

---

## Appendix: Raw Reviewer Reports
Omit this appendix in direct mode; no child reports were produced.
> The consolidated sections above are authoritative. These are the unedited reviewer outputs for reference.

### Backend Quality Reviewer
[Per-language quality reports — or "Skipped: no files changed for this language"]

### Security Reviewer
[Security reviewer full report]

### Frontend Quality Reviewer
[Frontend quality report — or "Skipped: no frontend files changed"]
```
