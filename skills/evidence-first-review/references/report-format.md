# Evidence-first review report

Use this format only when the user did not request another format. Omit empty sections, but never omit a prior finding from a recheck.

## Review header

- Mode: `initial`, `recheck`, or `final-approval`
- Locked scope: context files, code paths, data sources, and revision/current-file boundary
- Constraints: read-only limits and unavailable checks
- Evidence executed: parsers, queries, commands, runtime versions, and relevant counts

## Prior finding ledger

Include this section for `recheck` and `final-approval`.

| Prior finding | Current status | Current evidence | Reason |
|---|---|---|---|
| Stable identifier or original title | `resolved`, `partially resolved`, `unresolved`, or `regressed` | `file:line`, data key, or runtime result | Why the evidence supports this status |

## Findings

Group findings by `Critical`, `High`, `Medium`, and `Low`, unless the user supplied another scale. List new findings separately from the prior finding ledger.

For every finding include:

- Title and severity
- Location: `file:line`, record identifier, query result, or runtime boundary
- Evidence: the observed condition and a representative counterexample when relevant
- Impact: the concrete failure, risk, or contract mismatch
- Recommendation: a bounded change or decision that addresses the evidence
- Confidence or limitation when the evidence is incomplete

Do not inflate severity to make a report look useful. Do not bury a verified blocking issue in a summary.

## Final decision

- `initial`: state whether the reviewed scope is acceptable, needs changes, or could not be fully verified.
- `recheck`: summarize prior-finding counts by status and state whether unresolved or regressed items block the requested outcome.
- `final-approval`: decide `approved`, `conditionally approved`, or `hold`, then list exact remaining conditions.

If no reportable finding remains, say so directly and list only material residual uncertainty.
