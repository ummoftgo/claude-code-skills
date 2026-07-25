# Consolidated Report Template

Structure for the team leader's consolidated output (SKILL.md Step 5). The same structure is used whether the report is emitted inline (default) or handed to `report-output` for file delivery.

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
