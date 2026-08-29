# Node.js Quality Reference

Server-side review: HTTP services, CLIs, daemons, and libraries. Tool invocation and the
environment-neutral patterns (comments, style, duplication) live in `js-toolchain.md` — read
that first, then this file for what only matters when JS runs outside a browser.

> **The read-only rule in `SKILL.md` overrides every instruction in this file.** Under a
> read-only request, no command here may install a tool, create a config file, write a
> report file, or auto-fix code — regardless of what an individual section says. Each
> write-causing command below carries its own read-only contract line; when one is
> skipped, record it in the report with its reason.

## Table of Contents
1. [Async Control Flow](#1-async-control-flow)
2. [Error Propagation](#2-error-propagation)
3. [Streams & Backpressure](#3-streams--backpressure)
4. [Process Lifecycle](#4-process-lifecycle)
5. [Resource Management](#5-resource-management)
6. [TypeScript Strictness](#6-typescript-strictness)
7. [Data Access & Evaluation Order](#7-data-access--evaluation-order)

---

## 1. Async Control Flow

### Sequential await inside a loop

```js
// BAD — N round trips serialised for no reason
const users = [];
for (const id of ids) {
  users.push(await db.getUser(id));      // each waits for the previous
}

// GOOD — independent work runs concurrently
const users = await Promise.all(ids.map(id => db.getUser(id)));

// GOOD — bounded concurrency when the target has limits
// A pool of 1000 unbounded queries is its own outage.
const users = await mapWithConcurrency(ids, 10, id => db.getUser(id));
```

`await` inside a loop is correct when each iteration **depends on the previous** or when the
downstream has a rate limit. Flag it only after checking which of the three cases it is; say
which one in the finding.

### Forgotten await

```js
// BAD — the caller returns before the write lands, and a rejection becomes unhandled
async function save(order) {
  db.insert(order);                       // ← missing await
  return { ok: true };
}
```

`@typescript-eslint/no-floating-promises` catches this when TypeScript type information is
available. Without it, grep for a bare call to a known-async function on its own statement line.

### `Promise.all` where one failure should not sink the rest

```js
// BAD — the first rejection settles the caller while the rest keep running unwatched
await Promise.all(targets.map(send));

// GOOD — collect outcomes, then decide
const results = await Promise.allSettled(targets.map(send));
const failed = results.filter(r => r.status === 'rejected');
```

`Promise.all` rejects as soon as one input rejects — it does **not** cancel the others. They keep
running, and **the caller never receives their outcomes**: a later success writes state nobody
recorded, and a later failure is invisible to the code that asked for the work. (Those later
rejections are not *unhandled* — `Promise.all` attaches a handler to every input — so no warning
appears. The loss is silent.) Use `Promise.all` when the caller
genuinely cannot proceed without every result; `Promise.allSettled` when partial success is a
real outcome the caller must see. Cancellation needs an `AbortSignal` passed to each task —
neither combinator provides it.

## 2. Error Propagation

### Unhandled rejection is fatal by default

Since Node 15 the `--unhandled-rejections` default mode is `throw`: with **no**
`unhandledRejection` listener, an unhandled rejection raises an uncaught exception and the
process exits. Registering a listener suppresses that default — so a listener that only logs
converts a crash into silent data loss, and the request that caused it is already gone. Confirm
the project's Node version before applying this: on Node 14 and earlier the default was a
warning, and the same code behaves differently.

```js
// BAD — suppresses the runtime's own safety default and continues in unknown state
process.on('unhandledRejection', err => logger.error(err));

// GOOD — re-raise so the normal uncaught-exception path runs
process.on('unhandledRejection', err => { throw err; });
```

Prefer re-throwing over `process.exit()`. Exiting truncates pending I/O — an async log
transport may not have flushed, so the very record explaining the crash is the one most likely
to be lost. Throwing lets `uncaughtException` handlers, the exit hooks, and the supervisor see
it in order. Flag a bare-logging handler as a real finding.

### Losing the cause

```js
// BAD — the original stack and message are gone
catch (err) {
  throw new Error('failed to load user');
}

// GOOD
catch (err) {
  throw new Error('failed to load user', { cause: err });
}
```

### Catch that hides control flow

```js
// BAD — a network error and a 404 become the same empty result
try {
  return await api.getUser(id);
} catch {
  return null;
}
```

An empty `catch`, or one that returns a neutral value for every error class, is a finding
whenever the caller behaves differently for different failures.

## 3. Streams & Backpressure

Writing without honouring backpressure buffers the whole payload in memory. A large export
becomes an out-of-memory kill under load, and it will not reproduce on a small dataset.

```js
// BAD — ignores the return value of write()
for await (const row of rows) {
  res.write(serialize(row));            // buffers unboundedly
}

// GOOD — pipeline propagates backpressure and errors, and cleans up on failure
const { pipeline } = require('node:stream/promises');
await pipeline(rows, serializeTransform, res);
```

When `write()` is used directly, its `false` return value must be respected by waiting for
`'drain'`. Manual `.pipe()` chains do not forward errors or destroy the source on failure — that
is what `pipeline` exists for. Flag a `.pipe()` chain with no error handling on every stream.

Two caveats when reviewing a fix: `pipeline` does not destroy a stream that has already emitted
`end`, `finish`, or `close`, so a handle can survive it; and once it has destroyed an HTTP response the
handler can no longer send an error status — the client sees a truncated body. A route that
needs a proper error response must validate before the first byte goes out.

## 4. Process Lifecycle

### Graceful shutdown

A container sends `SIGTERM` and kills after a grace period. A service that ignores it drops
in-flight requests on every deploy.

```js
// GOOD — idempotent, awaits the close, and lets a clean drain exit on its own
let shuttingDown = false;

async function shutdown(signal) {
  if (shuttingDown) return;             // a second SIGTERM must not re-enter
  shuttingDown = true;

  const forced = setTimeout(() => process.exit(1), SHUTDOWN_TIMEOUT_MS).unref();
  try {
    await new Promise((resolve, reject) =>
      server.close(err => (err ? reject(err) : resolve())));   // no new connections; drain in-flight
    await pool.end();
    clearTimeout(forced);
    // No process.exit(0): with the server and pool closed the event loop empties and Node
    // exits on its own, after stdout and any async log transport have flushed.
  } catch (err) {
    logger.error({ err, signal }, 'graceful shutdown failed');
    process.exitCode = 1;
  }
}

for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => shutdown(signal));
```

Check four things: the handler exists, it is idempotent under a repeated signal, it stops
accepting before releasing dependencies, and a timeout keeps one stuck connection from hanging
the shutdown forever. Note that `server.close(cb)` passes an error to the callback — an
`async` callback whose rejection nobody awaits loses it.

### `process.exit()` in the middle of work

`process.exit()` truncates pending async I/O — buffered stdout, an open transaction, a log
flush. Setting `process.exitCode` and letting the event loop drain is correct except when the
process is already unrecoverable (see the rejection handler above).

## 5. Resource Management

- A timer or interval that outlives its owner keeps the event loop alive. Long-lived timers in
  a CLI need `.unref()`, and per-request timers need clearing on every exit path.
- Event listeners added per request against a long-lived emitter leak. A `MaxListenersExceeded`
  warning is a symptom, not the defect.
- A file handle, DB client, or subprocess acquired in a `try` needs release in `finally` — a
  release on the happy path only leaks exactly when the system is already failing.
- Cancellation should reach the work: an `AbortSignal` accepted by the caller but never passed
  to `fetch`, the DB driver, or the child process is decorative.

## 6. TypeScript Strictness

Read `tsconfig.json` before reviewing TS. Findings differ sharply by configuration, and a
strictness gap explains a whole class of runtime errors better than any individual line.

| Setting | Off means |
|---|---|
| `strict` | The rest of this table is likely off too |
| `strictNullChecks` | `null` and `undefined` are assignable everywhere; optional-chaining findings are noise |
| `noUncheckedIndexedAccess` | `arr[i]` is typed as present, so index access lies |
| `exactOptionalPropertyTypes` | `{ a?: string }` silently accepts `{ a: undefined }` |

Type checking runs through `js-toolchain.md` §2, which owns the invocation **and the tsconfig
check it requires** — `--noEmit` alone does not make the run read-only. `any` at a trust boundary (request body, env var, JSON parse) is a finding even when the config is loose;
that is where the type system was supposed to earn its keep.

## 7. Data Access & Evaluation Order

The principle matches `php-quality.md` §6 — cheapest check first, and never per-row I/O in a
loop — but the mechanics differ.

```js
// BAD — N+1 across an async boundary; harder to see than the SQL version
const orders = await db.orders.findAll();
for (const order of orders) {
  order.user = await db.users.findById(order.userId);
}

// GOOD — one additional query
const users = await db.users.findByIds(orders.map(o => o.userId));
const byId = new Map(users.map(u => [u.id, u]));
orders.forEach(o => { o.user = byId.get(o.userId); });
```

Also check:

- **Connection pool exhaustion** — a query issued per item under `Promise.all` over a large
  array will exhaust the pool and time out. This is the failure mode that unbounded concurrency
  in §1 actually produces.
- **Transaction scope** — an `await` on an unrelated network call inside a transaction holds
  locks for the duration of that call.
- **Guard before I/O** — validate identifiers and required fields before touching the database
  or filesystem, not after.

### Audit grep

```bash
# await inside a for/while body — classify each as dependent, rate-limited, or serialisable
rg -n "for\s*\(.*\)\s*\{" --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" -A5 . | rg "await"

# .pipe() chains without an error handler on the same statement
rg -n "\.pipe\(" --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" .

# rejection handlers that only log
rg -n "unhandledRejection" -A3 --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" .

# signal handling — absence is the finding for a long-running service
rg -n "SIGTERM|SIGINT" --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" .
```
