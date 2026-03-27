---
name: web-browser-preview
description: "Open the current working file or project in a Windows browser for visual review, using agent-browser connected to Windows Chrome CDP (WSL environment). Trigger when user says '브라우저에서 확인해', '브라우저로 열어줘', 'browser로 확인해', 'check in browser', or similar requests. Automatically derives the URL from the current working path when possible; asks the user for the URL when the project uses routing. IMPORTANT: In WSL environments, always use this skill instead of invoking agent-browser directly. This skill supersedes agent-browser for all browser preview tasks in WSL — it resolves the Windows Host IP and derives the correct URL before delegating browser commands to agent-browser."
---

# Web Browser Preview

Open the current project in a Windows browser from WSL for visual review. This skill handles URL resolution and WSL→Windows CDP connection. Actual browser commands follow the **agent-browser skill**.

> **Priority over agent-browser**: Even if the `agent-browser` skill is installed, always invoke this skill first for any browser preview request in a WSL environment. This skill resolves the WSL→Windows IP and derives the correct URL, then delegates the actual browser interaction to `agent-browser`.

## Prerequisites (Step 0)

Check if the `agent-browser` skill is installed. If not, confirm with the user and install:

```bash
npx skills add vercel-labs/agent-browser --skill agent-browser
```

All browser navigation, snapshot, and screenshot commands are defined in the agent-browser skill — refer to it for those operations.

## Step 1: Determine the URL

Inspect the project to decide whether the URL can be auto-derived or must be requested from the user.

| Project type | Detection signal | Action |
|---|---|---|
| Simple PHP files | `index.php` present, no routing framework | Auto-derive from CWD |
| Routing app | `composer.json` has laravel/slim/etc., or SPA `package.json` | Ask user for URL |
| Local dev server | `php -S` process running, or `npm run dev` / Vite port | Detect port, build URL |

**Auto-derive rule**: map CWD to web root relative path.
- `/var/www/html/myapp/` → `http://<host>/myapp/`
- `/var/www/html/myapp/pages/users.php` → `http://<host>/myapp/pages/users.php`

Replace `<host>` with the `WINDOWS_HOST` resolved in Step 2. A web server running in WSL (Apache/nginx/php -S) is not reachable via `localhost` from Windows Chrome — the WSL IP must be used.

If a routing framework is detected (e.g., Laravel, Slim in `composer.json`), stop and ask the user for the URL:
> "A routing framework was detected. Please provide the URL you want to open in the browser."

## Step 2: Resolve Windows Host IP (WSL)

Windows host IP is not fixed — resolve it at runtime:

```bash
# Method 1 (preferred): default gateway
WINDOWS_HOST=$(ip route show | grep -i default | awk '{print $3}' | head -1)

# Method 2 (fallback): nameserver from /etc/resolv.conf
WINDOWS_HOST=$(grep nameserver /etc/resolv.conf | awk '{print $2}' | head -1)
```

If both return empty, ask the user to provide the Windows host IP directly.

## Step 3: Connect and Open

With the host IP resolved:

1. **Apply WINDOWS_HOST to the URL**: Replace the `<host>` placeholder from Step 1 with `${WINDOWS_HOST}`.
   - Example: `http://${WINDOWS_HOST}/myapp/pages/users.php`
2. **Connect CDP and open the page** — follow the agent-browser skill:
   - Connect: `agent-browser connect http://${WINDOWS_HOST}:9333`
   - Open: `agent-browser open http://${WINDOWS_HOST}/<path>`
3. Take a snapshot or screenshot to report the current state

## Error Handling

**CDP connection fails**:
Windows Chrome must be running with remote debugging enabled. Inform the user:
```
Please launch Chrome with remote debugging enabled:
  chrome.exe --remote-debugging-port=9333
```

**URL returns 404 / connection refused**:
Ask the user to confirm the web server is running (Apache/nginx/php -S).
