---
name: systematic-debugging
description: "Diagnose unclear software failures and fix only confirmed root causes using reproduction, evidence, competing hypotheses, regression protection, and focused verification. Use when a bug's cause is unknown, a failure is intermittent or cross-layer, an attempted fix did not work, or symptoms invite speculative edits. Respect diagnosis-only requests and skip this workflow when the root cause is already confirmed and the fix is obvious."
---

# Systematic Debugging

Find the causal mechanism before changing production code. Keep the investigation proportional, but do not substitute plausible guesses for evidence.

## 1. Preserve the requested scope

- For diagnosis-only requests, inspect and report without modifying files.
- For fix requests, do not edit production code until the failure is reproduced or equivalent evidence isolates the cause.
- Read repository instructions, nearby tests, runtime manifests, and relevant recent changes first.

## 2. Establish the failure

Capture the smallest reliable reproduction:

- exact input, command, environment, and observed output;
- expected behavior and the first point where reality diverges;
- frequency and conditions for intermittent failures;
- a working comparison case when one exists.

If reproduction is unavailable, collect logs, state, and code-path evidence. State what remains uncertain instead of inventing a cause.

## 3. Trace evidence and test hypotheses

Follow data and control flow from the symptom toward its source. Check boundaries first: caller/callee contracts, persistence, network responses, process environment, versioned runtimes, and generated state.

Write at most three active hypotheses. For each, record supporting evidence, contradicting evidence, and the cheapest observation that distinguishes it. Test one variable at a time. Temporary probes are allowed, but do not accumulate speculative fixes.

When the behavior depends on a library, framework, SDK, API, CLI, or cloud service, invoke `use-context7` first if installed and verify the current contract.

## 4. Confirm the root cause

Before fixing, explain the complete causal chain:

1. the triggering condition;
2. the incorrect state or branch;
3. how it produces the observed symptom;
4. why working cases avoid it;
5. which change should prevent it.

If evidence disproves the current hypothesis, return to tracing. After three useful but unsuccessful hypothesis cycles, summarize the evidence and request the missing input or environment access rather than continuing random edits.

## 5. Add regression protection

For an authorized fix, first reuse an existing failing test or the reproduction from §2. Add a permanent regression test only when coverage is missing and the failure's impact or recurrence risk justifies its maintenance and setup cost. When a focused test can cheaply capture the confirmed cause, check that failure before the fix; existing failure evidence already counts. Do not create a separate red-green cycle for each helper or duplicate a reproduction solely to satisfy a sequence. Use characterization tests for risky legacy behavior, or focused runtime checks when automated isolation is disproportionately expensive. Diagnosis-only work stops at findings.

## 6. Make the smallest causal fix

Change only what is needed to break the confirmed causal chain. Avoid unrelated refactoring, broad defensive code, silent fallbacks, or error suppression unless the evidence requires them.

After the causal changes are complete, run the focused reproduction/regression checks together, including the working comparison case. Expand to affected integration or wider checks only when the change's risk or project requirements warrant it. Reuse passing results for unchanged code, inputs, and environment; repeat only after relevant changes, failures, or a concrete unresolved concern. Remove temporary probes you created; they need not become permanent test files.

Report the root cause, evidence, changed files, regression protection, verification results, and any remaining uncertainty.
