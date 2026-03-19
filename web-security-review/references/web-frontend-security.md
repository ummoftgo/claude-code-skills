# Web Frontend Security Reference

Security checklist for vanilla JS, jQuery, Svelte, and HTMX frontends. Used by the `web-security-review` skill.

## Table of Contents
1. [DOM XSS — Dangerous Sinks (Vanilla JS)](#1-dom-xss--dangerous-sinks-vanilla-js)
2. [jQuery-Specific XSS Risks](#2-jquery-specific-xss-risks)
3. [Svelte-Specific XSS Risks](#3-svelte-specific-xss-risks)
4. [HTMX-Specific Security](#4-htmx-specific-security)
5. [Sensitive Data Exposure on Client](#5-sensitive-data-exposure-on-client)
6. [CORS & Subresource Integrity](#6-cors--subresource-integrity)
7. [Content Security Policy (CSP)](#7-content-security-policy-csp)
8. [localStorage / sessionStorage](#8-localstorage--sessionstorage)
9. [CSRF for AJAX/Fetch Requests](#9-csrf-for-ajaxfetch-requests)

---

## 1. DOM XSS — Dangerous Sinks (Vanilla JS)

**Severity if violated**: High–Critical

### MUST
- MUST NOT assign untrusted data directly to `innerHTML`, `outerHTML`, `insertAdjacentHTML`, or `document.write`.
- MUST prefer `textContent` or `innerText` for plain-text output.
- MUST prefer DOM construction (`document.createElement`, `element.setAttribute`) over HTML string building.
- MUST sanitize with DOMPurify if HTML rendering of user content is genuinely required.
- MUST NOT pass untrusted strings to `eval()`, `new Function()`, `setTimeout(string)`, or `setInterval(string)`.

### Secure pattern
```js
// GOOD — text only
el.textContent = userInput;

// GOOD — DOM construction
const a = document.createElement('a');
a.href = encodeURI(url); // verify scheme too (no javascript:)
a.textContent = linkText;
container.appendChild(a);

// BAD
el.innerHTML = userInput;
eval(userInput);
document.write(userInput);
```

### Audit grep patterns
```bash
grep -rn "innerHTML\s*=" --include="*.js" --include="*.html"
grep -rn "document\.write\b" --include="*.js"
grep -rn "\beval\s*(" --include="*.js"
grep -rn "insertAdjacentHTML" --include="*.js"
```

---

## 2. jQuery-Specific XSS Risks

**Severity if violated**: High

### MUST
- MUST use `.text()` instead of `.html()` for displaying user-generated content.
- MUST NOT pass untrusted data to `$(userInput)` — jQuery parses it as HTML.
- MUST NOT use `.load(url + userInput)` with user-controlled URL paths.
- MUST NOT use JSONP (`dataType: 'jsonp'`) with untrusted or user-controlled URLs.
- MUST validate `event.origin` before acting on `postMessage` data.

### Secure pattern
```js
// GOOD
$('#comment').text(userComment);

// BAD
$('#comment').html(userComment);
$('#wrapper').html('<div>' + userInput + '</div>');
$(userInput); // if userInput comes from URL/form
```

### Audit grep patterns
```bash
grep -rn "\.html\s*(" --include="*.js"
grep -rn "\$\s*(\s*[\"']?.*\+" --include="*.js"  # jQuery selector with concatenation
grep -rn "\.load\s*(" --include="*.js"
grep -rn "dataType.*jsonp\|jsonp.*dataType" --include="*.js"
```

---

## 3. Svelte-Specific XSS Risks

**Severity if violated**: High

### MUST
- MUST NOT use `{@html userContent}` with untrusted or user-generated content.
- If `{@html}` is absolutely required (e.g., CMS rich text), MUST sanitize with DOMPurify first.
- MUST use `{variable}` (auto-escaped by Svelte) for all normal text interpolation.
- MUST NOT pass user-controlled strings to `<svelte:component this={...}>` without strict allowlisting.

### Secure pattern
```svelte
<!-- GOOD — auto-escaped -->
<p>{userComment}</p>

<!-- BAD — XSS if userComment contains <script> -->
<p>{@html userComment}</p>

<!-- GOOD — if HTML rendering is required -->
<script>
  import DOMPurify from 'dompurify';
  $: safeHtml = DOMPurify.sanitize(rawHtml);
</script>
<p>{@html safeHtml}</p>
```

### Audit grep patterns
```bash
grep -rn "{@html" --include="*.svelte"
grep -rn "svelte:component" --include="*.svelte"
```

---

## 4. HTMX-Specific Security

**Severity if violated**: High

### MUST
- MUST include CSRF token in HTMX requests via `htmx:configRequest` event handler.
- MUST NOT use `hx-on:` or `hx-on[event]:` attributes with user-controlled content (event handler injection).
- MUST set `htmx.config.selfRequestsOnly = true` if all requests should be same-origin.
- MUST set `htmx.config.allowScriptTags = false` if responses should not contain script tags.
- MUST validate server-side that HTMX responses only contain expected HTML — do NOT use client-provided `HX-*` headers for authorization decisions.
- SHOULD configure a restrictive CSP; audit which HTMX features require `unsafe-eval` before adding that directive.

### Secure CSRF with HTMX
```html
<!-- In page <head> -->
<meta name="csrf-token" content="<?= htmlspecialchars($_SESSION['csrf_token'], ENT_QUOTES, 'UTF-8') ?>">
<script>
  document.addEventListener('htmx:configRequest', function(evt) {
    evt.detail.headers['X-CSRF-Token'] =
      document.querySelector('meta[name="csrf-token"]').content;
  });
  htmx.config.selfRequestsOnly = true;
  htmx.config.allowScriptTags = false;
</script>
```

### Audit grep patterns
```bash
grep -rn "hx-on" --include="*.html" --include="*.php"
grep -rn "htmx\.config" --include="*.js" --include="*.html"
grep -rn "HX-" --include="*.php"  # check if HX-* headers affect auth/logic
```

---

## 5. Sensitive Data Exposure on Client

**Severity if violated**: High

### MUST
- MUST NOT embed secrets (API keys, private tokens, service credentials) in JS bundles or inline scripts.
- MUST NOT expose user PII or session tokens in URL query parameters (logged by servers/proxies).
- MUST NOT include server-side env vars in responses unless intentionally public.
- MUST ensure API error responses do not include stack traces, SQL, file paths, or internal state.

### Audit grep patterns
```bash
grep -rn "api_key\|apiKey\|secret\|private_key" --include="*.js" --include="*.svelte" --include="*.html"
grep -rn "console\.log" --include="*.js"  # check for accidental credential logging
```

---

## 6. CORS & Subresource Integrity

**Severity if violated**: High

### MUST
- MUST NOT configure the backend to respond with `Access-Control-Allow-Origin: *` for cookie/session-authenticated endpoints.
- MUST use Subresource Integrity (SRI) for third-party scripts and stylesheets loaded from CDN:
  ```html
  <script src="https://cdn.example.com/lib.js"
          integrity="sha384-..."
          crossorigin="anonymous"></script>
  ```
- MUST NOT use `<script src>` with user-controlled URLs.

### Audit grep patterns
```bash
# Find CDN scripts missing integrity attribute
grep -rn "<script\s" --include="*.html" --include="*.php" | grep "http" | grep -v "integrity"
grep -rn "<link\s" --include="*.html" --include="*.php" | grep "cdn\|http" | grep -v "integrity"
```

---

## 7. Content Security Policy (CSP)

**Severity if violated**: Medium (reduces XSS blast radius)

### SHOULD
- SHOULD deploy a CSP header that restricts `script-src`, `style-src`, `connect-src`, and `object-src`.
- SHOULD avoid `unsafe-inline` and `unsafe-eval` in `script-src`.
- SHOULD use nonces or hashes for any inline scripts that cannot be moved to external files.
- HTMX note: Some HTMX features require `unsafe-eval`. Audit HTMX config usage before deciding.

### Minimum starting CSP for PHP + HTMX/jQuery
```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-{SERVER_GENERATED_NONCE}';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data:;
  connect-src 'self';
  object-src 'none';
  base-uri 'self';
  form-action 'self';
```

---

## 8. localStorage / sessionStorage

**Severity if violated**: High

### MUST
- MUST NOT store session tokens, authentication tokens, or sensitive PII in `localStorage` or `sessionStorage`. These are accessible to any JS on the page (XSS steals them).
- MUST use `httpOnly` cookies for authentication tokens.
- MAY store non-sensitive UI preferences (theme, language) in localStorage.

| Data | localStorage | Verdict |
|------|-------------|---------|
| Session / auth token | Never | Use httpOnly cookie |
| JWT with claims | Never | Use httpOnly cookie |
| User ID (non-sensitive) | Caution | Low risk only |
| UI preferences | OK | Acceptable |
| Cached API responses | Caution | Sanitize on read |

### Audit grep patterns
```bash
grep -rn "localStorage\.setItem\|sessionStorage\.setItem" --include="*.js" --include="*.svelte"
```

---

## 9. CSRF for AJAX/Fetch Requests

**Severity if violated**: High

### MUST
- MUST include the CSRF token in AJAX/fetch requests that perform state-changing operations (POST, PUT, DELETE, PATCH).
- MUST send the token as a custom request header (e.g., `X-CSRF-Token`) or in the request body.
- MUST NOT rely solely on `Content-Type: application/json` as a CSRF defense.

### Secure pattern (fetch)
```js
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

fetch('/api/update', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken
  },
  body: JSON.stringify(payload)
});
```

### jQuery global CSRF setup
```js
$.ajaxSetup({
  headers: {
    'X-CSRF-Token': $('meta[name="csrf-token"]').attr('content')
  }
});
```
