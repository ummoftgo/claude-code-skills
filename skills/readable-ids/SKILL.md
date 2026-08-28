---
name: readable-ids
description: "Give short work identifiers (A1, FR-001, CH-2) a human-readable label so a person can tell what one means without opening another document. Use when assigning stable identifiers to plans, tasks, requirements, workstreams, or review findings; when a report, a decision request, or a handoff document refers to work by identifier; or when another skill says to apply the identifier convention. Labels live in a committed `.uniqid/` registry and render to people as `A1(feature/label)`. Not for one-off numbering that is created and consumed inside a single document."
---

# Readable Identifiers

Short identifiers are for the agent; people need the meaning next to them. Keep the short form in working notes and add the label wherever a person reads it.

`A1: investigate B32 in the bundle and reinforce C23` is fast for a model and opaque for a reader, and it gets worse as the identifiers spread across documents. The registry below makes the short form resolvable without loading another document into a human's head.

## 1. Decide whether the identifier needs a label

Register an identifier when **any** of these holds:

- another document will refer to it;
- it outlives one session or one report;
- a person is asked to decide something by that identifier.

Do not register numbering that is created and consumed in one place: steps in a checklist the reader is already looking at, rows in a table that is never referenced again, a scratch enumeration inside a single message. Adding a registry entry for those is ceremony, and a registry full of dead entries stops being worth reading.

When in doubt, look at where the identifier will next appear. If the answer is "in a sentence somewhere else", register it.

## 2. Register it when you mint it

Write the entry at the moment the identifier is assigned, not at the end of the work. An identifier that exists for an hour without a label has already been written into a message a person had to decode.

- One file per identifier set: `.uniqid/{yyyy-mm-dd}-{slug}.md` at the project root.
- Commit the registry. A label that disappears with the session cannot resolve the identifier in last month's plan.
- Follow an existing project convention for this directory when the repository already has one.

Read [references/registry-format.md](references/registry-format.md) for the file template, the column meanings, and a worked example.

## 3. Render the full form for people

Write `A1(feature/label)` — for example `C1(리뷰신뢰경계/신뢰상태-전달-누락)` — in:

- reports and summaries written for a person;
- any request for a decision, including the blocking-items or open-questions line of a report;
- handoff, progress, and resume documents;
- chat messages that name work by identifier.

Use the **full form on the first mention within one document or one message, and the short form after that**. Repeating the full form on every line buries the sentence it belongs to.

Keep the short form as-is in: code, commit subjects, test names, the registry's own `ID` column, and internal working notes that no one is being asked to read.

At the definition site — the heading or line that introduces the identifier — write the full form once. That is what lets a reader connect a reference elsewhere back to the thing itself.

## 4. Write the label

- Korean or English, whichever a reader parses faster. Do not translate for uniformity.
- Hyphens instead of spaces. No whitespace, and no `/` — the slash separates `feature` from the label.
- Two to four words, roughly 20 characters. A label that needs a sentence belongs in the description column.
- Unique within its `feature`.
- It must say something. `문제-1`, `항목-A`, `issue-two` are rejected: they carry no more meaning than the identifier they were supposed to explain.

`feature` is the short domain noun the identifier set belongs to — usually one per registry file, declared in the file header. It is what disambiguates `A1` in one workstream from `A1` in another.

## 5. Lifecycle

- **Never renumber and never reuse an identifier**, matching the requirement lifecycle in `plan-and-build`.
- **A published label is fixed.** If a label turns out to be inaccurate, correct the description column and leave the label alone — references already written elsewhere still carry the old one, and silently changing it breaks exactly the lookup this skill exists to provide.
- A dropped item keeps its row with status `withdrawn` rather than disappearing, and is excluded from remaining-work counts.
- Status vocabulary is closed: `open` · `in-progress` · `done` · `withdrawn`.

The registry is the source of truth for the identifier-to-label mapping. The document that defines the item stays the source of truth for what the item actually says; do not let the one-line description in the registry grow into a second, competing specification.
