---
name: web-browser-preview
description: "Open the current working file or project in a Windows browser for visual review, using agent-browser connected to Windows Chrome CDP (WSL environment). Trigger when user says '브라우저에서 확인해', '브라우저로 열어줘', 'browser로 확인해', 'check in browser', or similar requests. Automatically derives the URL from the current working path when possible; asks the user for the URL when the project uses routing."
---

# Web Browser Preview

Open the current project in a Windows browser from WSL for visual review. This skill handles URL resolution and WSL→Windows CDP connection. Actual browser commands follow the **agent-browser skill**.

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
- `/var/www/html/myapp/` → `http://localhost/myapp/`
- `/var/www/html/myapp/pages/users.php` → `http://localhost/myapp/pages/users.php`

If a routing framework is detected (e.g., Laravel, Slim in `composer.json`), stop and ask:
> "라우팅 앱이 감지되었습니다. 브라우저에서 확인할 URL을 알려주세요."

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

With the host IP resolved, follow the agent-browser skill to:

1. Connect to CDP: `agent-browser connect http://${WINDOWS_HOST}:9333`
2. Open the URL: `agent-browser open <url>`
3. Take a snapshot or screenshot to report the current state

## Error Handling

**CDP connection fails**:
Windows Chrome must be running with remote debugging enabled. Inform the user:
```
Chrome를 원격 디버깅 모드로 실행해주세요:
  chrome.exe --remote-debugging-port=9333
```

**URL returns 404 / connection refused**:
Ask the user to confirm the web server is running (Apache/nginx/php -S).
