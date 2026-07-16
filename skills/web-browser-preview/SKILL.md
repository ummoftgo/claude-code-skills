---
name: web-browser-preview
description: "Open the current project in Windows Chrome for visual review, using agent-browser over CDP from native Windows or WSL. Trigger when user says '브라우저에서 확인해', '브라우저로 열어줘', 'browser로 확인해', 'check in browser', or similar requests. Resolves the correct CDP and application host for the active platform before delegating browser commands to agent-browser."
---

# Web Browser Preview

Open the current project in Windows Chrome from native Windows or WSL. This skill resolves the platform-specific application host and CDP endpoint. Actual navigation and capture commands follow the **agent-browser skill**.

> **Priority over agent-browser**: Invoke this skill first for Windows/WSL preview requests, then invoke `agent-browser` by skill name for browser operations.

## Prerequisites (Step 0)

Check whether the `agent-browser` skill and CLI are available. Report their state; do not install packages automatically.

```bash
command -v agent-browser || echo "agent-browser missing — npm install -g agent-browser"
```

```powershell
if (-not (Get-Command agent-browser -ErrorAction SilentlyContinue)) {
  Write-Host 'agent-browser missing — npm install -g agent-browser'
}
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

On native Windows use `127.0.0.1` unless the project declares another host. In WSL replace `<host>` with `WINDOWS_HOST` from Step 2.

If a routing framework is detected (e.g., Laravel, Slim in `composer.json`), stop and ask the user for the URL:
> "A routing framework was detected. Please provide the URL you want to open in the browser."

## Step 2: Select the platform endpoint

### Native Windows

Use `http://127.0.0.1:9333` as the CDP endpoint. Chrome 136+ requires remote debugging to use a non-default user-data directory. Never use the user's default Chrome profile and do not launch Chrome automatically. If Chrome is not ready, report this exact safe setup command for the user to run:

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$cdpProfile = Join-Path $env:LOCALAPPDATA 'claude-code-skills\chrome-cdp-profile'
& $chrome --remote-debugging-port=9333 --user-data-dir="$cdpProfile"
```

Connect with `agent-browser connect http://127.0.0.1:9333`.

### WSL

Windows host IP is not fixed — resolve it at runtime:

```bash
# Method 1 (preferred): default gateway
WINDOWS_HOST=$(ip route show | grep -i default | awk '{print $3}' | head -1)

# Method 2 (fallback): nameserver from /etc/resolv.conf
WINDOWS_HOST=$(grep nameserver /etc/resolv.conf | awk '{print $2}' | head -1)
```

If both return empty, ask the user to provide the Windows host IP directly.

## Step 3: Connect and Open

With the platform endpoint resolved:

1. **Apply the application host to the URL**: use `127.0.0.1` on native Windows or `${WINDOWS_HOST}` for a server running in WSL.
   - Example: `http://${WINDOWS_HOST}/myapp/pages/users.php`
2. **Connect CDP and open the page** — follow the agent-browser skill:
   - Native Windows connect: `agent-browser connect http://127.0.0.1:9333`
   - WSL connect: `agent-browser connect http://${WINDOWS_HOST}:9333`
   - Open the application URL resolved in Step 1.
3. Take a snapshot or screenshot to report the current state

## Error Handling

**CDP connection fails**:
Report whether Chrome and agent-browser were detected. Chrome must be running with remote debugging and a dedicated profile. Inform the user without launching or installing anything:
```
Please launch Chrome with remote debugging enabled:
  chrome.exe --remote-debugging-port=9333 --user-data-dir=<dedicated-cdp-profile>
```

**URL returns 404 / connection refused**:
Ask the user to confirm the web server is running (Apache/nginx/php -S).
