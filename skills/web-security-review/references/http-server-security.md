# HTTP Server Surface Security Reference

**Surface axis.** These rules apply to anything that answers HTTP requests, whatever language
serves them. Pair this file with the **language axis** reference for the runtime in use
(`node-security.md`, …) — that file owns runtime APIs, dependency risk, and secrets handling.

**PHP is the exception, deliberately.** `php-backend-security.md` predates this split and
carries its language rules and HTTP-surface rules together. It stays that way until the split is
proven on another language; for a PHP change, load that file and **not** this one. Loading both
would double-report the same findings.

**Severity if violated** is stated per section — the impact decides, not the `MUST` wording.

## Table of Contents
1. [Authentication](#1-authentication)
2. [Session Management](#2-session-management)
3. [CSRF](#3-csrf)
4. [Authorization](#4-authorization)
5. [Input at the HTTP Boundary](#5-input-at-the-http-boundary)
6. [File Upload](#6-file-upload)
7. [Security Headers](#7-security-headers)
8. [CORS](#8-cors)
9. [Response Data Exposure](#9-response-data-exposure)
10. [Rate Limiting & Resource Exhaustion](#10-rate-limiting--resource-exhaustion)

---

## 1. Authentication

**Severity if violated**: Critical

### MUST
- MUST hash passwords with a purpose-built password hash — never a plain digest, however many
  rounds. Prefer a **memory-hard** algorithm at or above OWASP's minimum: argon2id with
  **m=19 MiB, t=2, p=1**, or scrypt with **N=2^17, r=8, p=1**. Quote all three parameters when
  reporting — `N` alone does not fix the cost, because halving `r` halves the memory the
  attacker needs at the same `N`.
  **bcrypt is not memory-hard** — it is an acceptable legacy choice with a work factor of 10 or
  more, but it does not resist GPU attack the way the first two do, so do not describe it as
  equivalent.
- MUST compare secrets and tokens in constant time.
- MUST NOT reveal which factor failed ("no such user" vs "wrong password") in the response or in
  the response *time*.
- MUST invalidate existing sessions on password change.

## 2. Session Management

**Severity if violated**: High

### MUST
- MUST regenerate the session identifier on privilege change (login, role elevation) — fixation
  is the attack this prevents.
- MUST set `HttpOnly`, `Secure`, and `SameSite` on session cookies.
- MUST expire sessions server-side; a client-side expiry is a suggestion.
- MUST NOT put authorization state in a cookie the client can edit unless it is signed **and**
  the signature is verified before use.

## 3. CSRF

**Severity if violated**: High

### MUST
- MUST require a CSRF token on every state-changing request authenticated by a cookie.
- MUST verify the token server-side against the session, not merely against its own presence.
- MUST NOT rely on `SameSite` alone — it is defence in depth, and `SameSite=Lax` still permits
  top-level `GET` navigation.

A token-authenticated API (`Authorization: Bearer`) is not CSRF-exposed the same way, because the
browser does not attach the header automatically. Say which model the endpoint uses before
reporting a missing token.

## 4. Authorization

**Severity if violated**: Critical

### MUST
- MUST check authorization **per object**, not only per route. "The user is logged in" is not
  "the user may read order 4213" — this is the most common real defect in review.
- MUST enforce tenant isolation in the query itself (`WHERE tenant_id = ?`), not by filtering
  results afterwards.
- MUST NOT trust an identifier from the request body to select the acting principal.

```
# Route-level guard with no object check — flag it
router.get('/orders/:id', requireLogin, (req, res) => send(db.order(req.params.id)));
```

## 5. Input at the HTTP Boundary

**Severity if violated**: Medium–High depending on context

### MUST
- MUST validate type, shape, and range at the boundary, before the value reaches a query or a
  filesystem call.
- MUST reject unexpected fields on requests that drive persistence (mass-assignment).
- MUST bound body and field sizes; an unbounded JSON body is a denial-of-service primitive.
- MUST decode exactly once and validate **after** decoding.

## 6. File Upload

**Severity if violated**: Critical (arbitrary code execution) / High

### MUST
- MUST determine type from content, not from the client-supplied filename or `Content-Type`.
- MUST store uploads outside the document root, or serve them from a path that cannot execute.
- MUST generate the stored filename; never use the client's.
- MUST bound size and count before reading the stream.

## 7. Security Headers

**Severity if violated**: Medium

| Header | Applies to |
|---|---|
| `Content-Security-Policy` | **HTML document responses.** Without it an XSS has full reach |
| `X-Frame-Options` or CSP `frame-ancestors` | HTML document responses |
| `X-Content-Type-Options: nosniff` | every response, JSON included |
| `Strict-Transport-Security` | every response on an HTTPS origin |
| `Referrer-Policy` | every response |

**Decide what the endpoint returns before reporting a missing CSP.** Almost every CSP directive
governs how a *document* loads subresources, so a service that only returns JSON gains close to
nothing from one — reporting it there is noise that trains the reader to skip this section. Report
a missing CSP at Medium when the response is an HTML document, and raise it when that document
also reflects user input. For an API that returns no HTML, `nosniff` and HSTS are the headers
that still matter.

## 8. CORS

**Severity if violated**: High if misconfigured

### MUST
- MUST NOT reflect an arbitrary `Origin` header into `Access-Control-Allow-Origin`. Combined
  with `Access-Control-Allow-Credentials: true` this hands any site the user's authenticated
  responses — it is the exposure in this section, and it is Critical in practice.
- MUST NOT combine `Access-Control-Allow-Credentials: true` with a wildcard. Per the
  [Fetch standard](https://fetch.spec.whatwg.org/#cors-protocol-and-credentials) the browser
  **fails** a credentialed request whose response says `Access-Control-Allow-Origin: *`, so this
  is a broken configuration rather than a data leak. Report it as Medium and say so — the danger
  is the fix developers reach for next, which is reflecting the origin.
- MUST keep the allowlist explicit and reviewable.

```
# Reflected origin with credentials — Critical in practice, not just High
res.setHeader('Access-Control-Allow-Origin', req.headers.origin);
res.setHeader('Access-Control-Allow-Credentials', 'true');
```

## 9. Response Data Exposure

**Severity if violated**: High

### MUST
- MUST return only the fields the caller needs — serialising a whole ORM row leaks
  `password_hash`, internal flags, and soft-delete state.
- MUST NOT return stack traces, SQL text, or internal hostnames in error responses.
- MUST NOT put sensitive values in URLs; they reach logs, referrers, and history.

## 10. Rate Limiting & Resource Exhaustion

**Severity if violated**: Medium

### MUST
- MUST rate-limit authentication, password reset, and any endpoint that sends mail or SMS.
- MUST bound expensive work triggered by one request — pagination limits, query timeouts,
  regex complexity on user input (ReDoS).
- MUST NOT let a single request open unbounded concurrent work against a downstream dependency.
