#!/usr/bin/env bash
# =============================================================================
# 팀 Claude Code 스킬 설치 스크립트
# sudo 없이 현재 사용자 기준으로 설치합니다.
# =============================================================================

set -euo pipefail

# --- 색상 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- 경로 설정 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_INSTALL_DIR="$HOME/.claude/skills"
LOCAL_BIN="$HOME/.local/bin"
NPM_GLOBAL="$HOME/.npm-global"

# PATH에 추가가 필요한 디렉토리를 추적
NEED_PATH_SETUP=()

# codex 사용 여부 (create_skill_links에서 참조)
USE_CODEX=true

# 스킬 설치 방식: "symlink" 또는 "copy"
SKILL_INSTALL_MODE="symlink"

# =============================================================================
# 유틸 함수
# =============================================================================

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
section() { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

# yes/no 질문 (기본값 y)
ask_yn() {
    local prompt="$1"
    local reply
    read -rp "$(echo -e "${YELLOW}?${NC} ${prompt} [Y/n] ")" reply
    reply="${reply:-Y}"
    [[ "$reply" =~ ^[Yy]$ ]]
}

# 설치 방식 선택: 1=전역, 2=npx/skip
ask_install_mode() {
    local tool_name="$1"
    local opt1="$2"   # 전역 설치 설명
    local opt2="$3"   # npx/skip 설명
    local choice

    echo -e "  ${YELLOW}?${NC} ${tool_name} 설치 방식을 선택하세요:"
    echo -e "    ${BOLD}1)${NC} 전역 설치 — ${opt1}"
    echo -e "    ${BOLD}2)${NC} ${opt2}"
    while true; do
        read -rp "  선택 (1/2): " choice
        case "$choice" in
            1) return 0 ;;
            2) return 1 ;;
            *) warn "1 또는 2를 입력하세요." ;;
        esac
    done
}

# ~/.local/bin이 PATH에 있는지 확인
ensure_local_bin_in_path() {
    if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
        NEED_PATH_SETUP+=("$LOCAL_BIN")
    fi
    mkdir -p "$LOCAL_BIN"
}

# ~/.npm-global/bin이 PATH에 있는지 확인
# npm prefix가 이미 $HOME 하위에 있으면 (nvm/fnm/volta 등) 별도 설정 불필요
ensure_npm_global_in_path() {
    local current_prefix
    current_prefix="$(npm config get prefix 2>/dev/null)" || true

    if [[ -n "$current_prefix" && "$current_prefix" == "$HOME"* ]]; then
        return
    fi

    if [[ ":$PATH:" != *":$NPM_GLOBAL/bin:"* ]]; then
        NEED_PATH_SETUP+=("$NPM_GLOBAL/bin")
    fi
    mkdir -p "$NPM_GLOBAL"
    npm config set prefix "$NPM_GLOBAL" 2>/dev/null || true
}

# PHAR 다운로드 후 실행 가능하게 설정
install_phar() {
    local name="$1"
    local url="$2"
    local dest="$LOCAL_BIN/$name"

    info "${name} 다운로드 중..."
    if command -v wget &>/dev/null; then
        wget -q -O "$dest" "$url"
    elif command -v curl &>/dev/null; then
        curl -qsL "$url" -o "$dest"
    else
        warn "wget 또는 curl이 필요합니다."
        return 1
    fi
    chmod +x "$dest"
    ok "${name} → ${dest}"
}

# =============================================================================
# 섹션 1: PHP 품질 도구 (code-quality-review 스킬용)
# =============================================================================

install_php_tools() {
    section "PHP 품질 도구 (PHPStan / phpcs / phpmd / phpcpd)"
    info "code-quality-review 스킬이 PHP 코드 검토 시 사용합니다."

    # PHP가 설치되어 있는지 먼저 확인
    if ! command -v php &>/dev/null; then
        warn "PHP CLI가 설치되어 있지 않습니다. PHP 도구를 건너뜁니다."
        return
    fi
    info "PHP $(php -r 'echo PHP_VERSION;') 감지"

    local any_missing=false
    for tool in phpstan phpcs phpmd phpcpd; do
        command -v "$tool" &>/dev/null || { any_missing=true; break; }
    done

    if ! $any_missing; then
        ok "모든 PHP 도구가 이미 설치되어 있습니다."
        return
    fi

    echo
    if ! ask_yn "PHP 품질 도구를 설치하시겠습니까?"; then
        skip "PHP 도구 건너뜀"
        return
    fi

    ensure_local_bin_in_path

    # PHPStan
    if command -v phpstan &>/dev/null; then
        ok "phpstan 이미 설치됨 ($(phpstan --version 2>/dev/null | head -1))"
    else
        if ask_install_mode "phpstan" \
            "~/.local/bin/phpstan 으로 설치" \
            "건너뜀 (스킬 실행 시 수동 설치 필요)"; then
            install_phar "phpstan" \
                "https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar"
        else
            skip "phpstan 건너뜀"
        fi
    fi

    # phpcs + phpcbf
    if command -v phpcs &>/dev/null; then
        ok "phpcs 이미 설치됨"
    else
        if ask_install_mode "phpcs / phpcbf" \
            "~/.local/bin/phpcs, phpcbf 으로 설치" \
            "건너뜀"; then
            install_phar "phpcs"  "https://phars.phpcodesniffer.com/phpcs.phar"
            install_phar "phpcbf" "https://phars.phpcodesniffer.com/phpcbf.phar"
        else
            skip "phpcs / phpcbf 건너뜀"
        fi
    fi

    # phpmd
    if command -v phpmd &>/dev/null; then
        ok "phpmd 이미 설치됨"
    else
        if ask_install_mode "phpmd" \
            "~/.local/bin/phpmd 으로 설치" \
            "건너뜀"; then
            install_phar "phpmd" \
                "https://static.phpmd.org/php/latest/phpmd.phar"
        else
            skip "phpmd 건너뜀"
        fi
    fi

    # phpcpd
    if command -v phpcpd &>/dev/null; then
        ok "phpcpd 이미 설치됨"
    else
        if ask_install_mode "phpcpd" \
            "~/.local/bin/phpcpd 으로 설치" \
            "건너뜀"; then
            install_phar "phpcpd" \
                "https://phar.phpunit.de/phpcpd.phar"
        else
            skip "phpcpd 건너뜀"
        fi
    fi
}

# =============================================================================
# 섹션 2: ctx7 CLI (use-context7 스킬용)
# =============================================================================

install_ctx7() {
    section "ctx7 CLI (use-context7 스킬용)"
    info "MCP 없이 context7 문서를 조회할 때 사용합니다."

    if command -v ctx7 &>/dev/null; then
        ok "ctx7 이미 설치됨"
        return
    fi

    echo
    if ! ask_yn "ctx7를 설치하시겠습니까?"; then
        skip "ctx7 건너뜀 (MCP가 설정되어 있으면 불필요)"
        return
    fi

    if ask_install_mode "ctx7" \
        "npm install -g ctx7 (전역 설치)" \
        "npx ctx7 로 실행 (설치 없음, 매번 다운로드)"; then
        ensure_npm_global_in_path
        info "ctx7 전역 설치 중..."
        npm install -g ctx7
        ok "ctx7 설치 완료"
    else
        ok "npx ctx7 방식 사용 — 설치 불필요"
        info "사용 예: npx ctx7 docs /sveltejs/svelte \"\\\$state runes\""
    fi
}

# =============================================================================
# 섹션 3: Codex CLI (codex-delegate 스킬용)
# =============================================================================

install_codex() {
    section "Codex CLI (codex-delegate 스킬용)"
    info "코덱스에게 검토/구현 위임 시 사용합니다."

    echo
    if ! ask_yn "Codex를 사용하시겠습니까?"; then
        skip "Codex 건너뜀 (codex-delegate 스킬도 설치하지 않습니다)"
        USE_CODEX=false
        return
    fi

    # --- Codex CLI 설치 ---
    if command -v codex &>/dev/null; then
        ok "codex 이미 설치됨"
    else
        if ! ask_yn "Codex CLI를 설치하시겠습니까?"; then
            skip "Codex CLI 건너뜀"
        elif ask_install_mode "Codex CLI" \
            "npm install -g @openai/codex (전역 설치)" \
            "npx @openai/codex 로 실행 (설치 없음)"; then
            ensure_npm_global_in_path
            info "Codex CLI 전역 설치 중..."
            npm install -g @openai/codex
            ok "Codex CLI 설치 완료"
        else
            ok "npx @openai/codex 방식 사용"
        fi
    fi

    # --- 인증 확인 (Codex 사용 시 필수) ---
    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
        ok "OPENAI_API_KEY 환경변수 확인됨"
    elif command -v codex &>/dev/null && codex login status &>/dev/null; then
        ok "codex 로그인 상태 확인됨"
    else
        echo
        warn "Codex 인증이 설정되어 있지 않습니다."
        info "다음 중 하나로 인증을 설정하세요:"
        echo -e "  ${CYAN}1) codex login${NC}  (브라우저 로그인)"
        echo -e "  ${CYAN}2) ~/.bashrc 또는 ~/.zshrc에 추가:${NC}"
        echo -e "     ${CYAN}export OPENAI_API_KEY=\"sk-...\"${NC}"
    fi
}

# =============================================================================
# 섹션 4: context7 MCP 설정 (선택)
# =============================================================================

setup_context7_mcp() {
    section "context7 MCP 설정 (선택)"
    info "MCP를 설정하면 ctx7 CLI 없이도 Claude Code에서 자동으로 문서를 조회합니다."

    local settings_file="$HOME/.claude/settings.json"

    # 이미 설정되어 있는지 확인
    if [[ -f "$settings_file" ]] && grep -q "context7" "$settings_file" 2>/dev/null; then
        ok "context7 MCP가 이미 settings.json에 설정되어 있습니다."
        return
    fi

    echo
    if ! ask_yn "context7 MCP를 ~/.claude/settings.json에 추가하시겠습니까?"; then
        skip "context7 MCP 설정 건너뜀"
        return
    fi

    mkdir -p "$HOME/.claude"

    if [[ -f "$settings_file" ]]; then
        # 기존 settings.json에 mcpServers 추가
        # Python으로 JSON 병합 (jq 없이도 동작)
        python3 - "$settings_file" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    data = json.load(f)

data.setdefault("mcpServers", {})
data["mcpServers"]["context7"] = {
    "command": "npx",
    "args": ["-y", "@upstash/context7-mcp"]
}

with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
        ok "context7 MCP를 기존 settings.json에 추가했습니다."
    else
        # settings.json 신규 생성
        cat > "$settings_file" <<'JSON'
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
JSON
        ok "~/.claude/settings.json 생성 및 context7 MCP 추가 완료"
    fi
}

# =============================================================================
# 섹션 5: agent-browser 스킬 설치 (web-browser-preview 스킬용)
# =============================================================================

install_agent_browser() {
    section "agent-browser 스킬 (web-browser-preview 스킬용)"
    info "WSL에서 Windows Chrome으로 브라우저 미리보기 시 필요합니다."

    # --- 스킬 설치 ---
    if [[ -d "$SKILLS_INSTALL_DIR/agent-browser" ]]; then
        ok "agent-browser 스킬이 이미 설치되어 있습니다."
    else
        echo
        if ! ask_yn "agent-browser 스킬을 설치하시겠습니까?"; then
            skip "agent-browser 스킬 건너뜀 (web-browser-preview 스킬 미동작)"
        elif command -v npx &>/dev/null; then
            info "agent-browser 스킬 설치 중..."
            npx skills add vercel-labs/agent-browser --skill agent-browser
            ok "agent-browser 스킬 설치 완료"
        else
            warn "npx를 찾을 수 없습니다. Node.js를 먼저 설치하세요."
        fi
    fi

    # --- npm 패키지 설치 (스킬 설치 여부와 무관하게 항상 확인) ---
    echo
    if command -v npm &>/dev/null; then
        if npm list -g --depth=0 agent-browser 2>/dev/null | grep -q "agent-browser"; then
            ok "agent-browser npm 패키지 이미 설치됨"
        else
            if ask_yn "agent-browser npm 패키지를 전역으로 설치하시겠습니까?"; then
                ensure_npm_global_in_path
                info "agent-browser npm 패키지 전역 설치 중..."
                if npm install -g agent-browser; then
                    ok "agent-browser npm 패키지 설치 완료"
                else
                    warn "agent-browser npm 패키지 설치에 실패했습니다."
                    info "수동으로 설치하려면: npm install -g agent-browser"
                fi
            else
                skip "agent-browser npm 패키지 건너뜀"
            fi
        fi
    else
        warn "npm을 찾을 수 없습니다. Node.js를 먼저 설치하세요."
    fi
}

# =============================================================================
# 섹션 6: 스킬 설치 방식 선택 + 공용 헬퍼
# =============================================================================

ask_skill_install_mode() {
    section "스킬 설치 방식 선택"
    echo -e "  ${BOLD}1)${NC} 심볼릭 링크 — 저장소 파일을 직접 참조 (저장소 수정이 자동 반영)"
    echo -e "  ${BOLD}2)${NC} 파일 복사   — 스킬 파일을 독립적으로 복사 (저장소 없이도 동작)"
    echo
    while true; do
        read -rp "  선택 (1/2): " choice
        case "$choice" in
            1) SKILL_INSTALL_MODE="symlink"; ok "심볼릭 링크 방식 선택"; return ;;
            2) SKILL_INSTALL_MODE="copy";    ok "파일 복사 방식 선택";   return ;;
            *) warn "1 또는 2를 입력하세요." ;;
        esac
    done
}

# install_skill <skill_name> <dst_dir>
# SKILL_INSTALL_MODE 에 따라 심볼릭 링크 또는 복사로 스킬을 설치한다.
install_skill() {
    local skill="$1"
    local dst_dir="$2"
    local src="$SCRIPT_DIR/$skill"
    local dst="$dst_dir/$skill"

    if [[ ! -d "$src" ]]; then
        warn "소스 디렉토리 없음: $src — 건너뜀"
        return
    fi

    if [[ "$SKILL_INSTALL_MODE" == "copy" ]]; then
        if [[ -L "$dst" ]]; then
            warn "${skill} 위치에 심볼릭 링크가 있습니다: $dst"
            if ask_yn "  링크를 제거하고 파일로 복사하시겠습니까?"; then
                rm "$dst"
                cp -r "$src" "$dst"
                ok "${skill} → ${dst} (복사, 링크 대체)"
            else
                skip "${skill} 건너뜀"
            fi
        elif [[ -d "$dst" ]]; then
            warn "${skill} 디렉토리가 이미 존재합니다: $dst"
            if ask_yn "  덮어쓰시겠습니까?"; then
                rm -rf "$dst"
                cp -r "$src" "$dst"
                ok "${skill} → ${dst} (복사, 덮어씀)"
            else
                skip "${skill} 건너뜀"
            fi
        else
            cp -r "$src" "$dst"
            ok "${skill} → ${dst} (복사)"
        fi
    else
        # symlink mode
        if [[ -L "$dst" ]]; then
            local current_target
            current_target="$(readlink "$dst")"
            if [[ "$current_target" == "$src" ]]; then
                ok "${skill} 링크 이미 존재 (최신)"
            else
                warn "${skill} 링크가 다른 경로를 가리킵니다: $current_target"
                if ask_yn "  링크를 현재 경로(${src})로 업데이트할까요?"; then
                    ln -sfn "$src" "$dst"
                    ok "${skill} → ${dst} (링크 업데이트)"
                else
                    skip "${skill} 링크 업데이트 건너뜀"
                fi
            fi
        elif [[ -d "$dst" ]]; then
            warn "${skill} 위치에 실제 디렉토리가 있습니다: $dst"
            skip "${skill} 건너뜀 (수동 처리 필요)"
        else
            ln -s "$src" "$dst"
            ok "${skill} → ${dst} (링크)"
        fi
    fi
}

# =============================================================================
# 섹션 7: Claude Code 스킬 설치
# =============================================================================

create_skill_links() {
    section "Claude Code 스킬 설치 → ${SKILLS_INSTALL_DIR}"

    mkdir -p "$SKILLS_INSTALL_DIR"

    local skills=(
        "use-context7"
        "web-security-review"
        "web-parallel-dispatch"
        "web-browser-preview"
        "code-quality-review"
    )

    # codex 사용 여부에 따라 codex-delegate 포함
    if $USE_CODEX; then
        skills+=("codex-delegate")
    else
        skip "codex-delegate 스킬 건너뜀 (Codex 미사용)"
    fi

    for skill in "${skills[@]}"; do
        install_skill "$skill" "$SKILLS_INSTALL_DIR"
    done
}

# =============================================================================
# 섹션 8: Codex 스킬 설치 (선택)
# =============================================================================

install_codex_skills() {
    section "Codex 스킬 설치 (선택)"

    if ! $USE_CODEX; then
        skip "Codex 미사용 — Codex 스킬 설치 건너뜀"
        return
    fi

    local codex_skills_dir="$HOME/.codex/skills/local"

    if [[ ! -d "$HOME/.codex/skills" ]]; then
        warn "~/.codex/skills 디렉토리가 없습니다. Codex가 설치되어 있는지 확인하세요."
        return
    fi

    info "Claude Code 스킬을 Codex에도 설치할 수 있습니다."
    info "설치 경로: ${codex_skills_dir}"
    echo

    if ! ask_yn "Codex에도 스킬을 설치하시겠습니까?"; then
        skip "Codex 스킬 설치 건너뜀"
        return
    fi

    mkdir -p "$codex_skills_dir"

    # codex-delegate는 "Claude → Codex 위임" 스킬이므로 Codex 자신에게는 제외
    local available_skills=(
        "use-context7"
        "web-security-review"
        "web-parallel-dispatch"
        "web-browser-preview"
        "code-quality-review"
    )

    echo
    info "설치할 스킬을 선택하세요:"
    local selected_skills=()
    for skill in "${available_skills[@]}"; do
        if ask_yn "  ${skill}"; then
            selected_skills+=("$skill")
        fi
    done

    if [[ ${#selected_skills[@]} -eq 0 ]]; then
        skip "선택된 스킬 없음"
        return
    fi

    echo
    for skill in "${selected_skills[@]}"; do
        install_skill "$skill" "$codex_skills_dir"
    done
}

# =============================================================================
# 섹션 9: Chrome DevTool Protocol 스크립트 → Windows 바탕화면 복사
# =============================================================================

copy_cdp_script_to_desktop() {
    section "Chrome DevTool Protocol 스크립트 → Windows 바탕화면"
    info "WSL에서 Chrome CDP를 실행하는 PowerShell 스크립트를 바탕화면에 복사합니다."

    local src="$SCRIPT_DIR/chrome-devtool-protocol.ps1"
    if [[ ! -f "$src" ]]; then
        warn "chrome-devtool-protocol.ps1 파일을 찾을 수 없습니다: $src"
        return
    fi

    echo
    if ! ask_yn "chrome-devtool-protocol.ps1을 Windows 바탕화면으로 복사하시겠습니까?"; then
        skip "바탕화면 복사 건너뜀"
        return
    fi

    # PowerShell로 실제 바탕화면 경로 조회 (OneDrive 리다이렉션 대응)
    if ! command -v powershell.exe &>/dev/null; then
        warn "powershell.exe를 찾을 수 없습니다. WSL 환경이 맞는지 확인하세요."
        return
    fi

    local win_desktop
    # Method 1: GetFolderPath (OneDrive 리다이렉션까지 처리)
    # [Console]::OutputEncoding = UTF8 로 한글/특수문자 포함 경로의 인코딩 깨짐 방지
    win_desktop="$(powershell.exe -NoProfile -Command \
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')" \
        2>/dev/null | tr -d '\r')"

    # Method 2 (fallback): Shell.Application COM 오브젝트
    if [[ -z "$win_desktop" ]]; then
        win_desktop="$(powershell.exe -NoProfile -Command \
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; (New-Object -ComObject Shell.Application).NameSpace('Desktop').Self.Path" \
            2>/dev/null | tr -d '\r')"
    fi

    if [[ -z "$win_desktop" ]]; then
        warn "Windows 바탕화면 경로를 가져오지 못했습니다."
        return
    fi

    # Windows 경로 → WSL 경로로 변환 (-u: Windows → Unix 방향 명시, 공백·한글 포함 경로 대응)
    local wsl_desktop
    wsl_desktop="$(wslpath -u "$win_desktop" 2>/dev/null)"

    # wslpath 실패 시 수동 변환: C:\path → /mnt/c/path
    if [[ -z "$wsl_desktop" ]]; then
        wsl_desktop="$(printf '%s' "$win_desktop" | sed 's|\\|/|g; s|^\([A-Za-z]\):|/mnt/\L\1|')"
    fi

    if [[ -z "$wsl_desktop" || ! -d "$wsl_desktop" ]]; then
        warn "바탕화면 경로 변환 실패: $win_desktop"
        return
    fi

    cp "$src" "$wsl_desktop/chrome-devtool-protocol.ps1"
    ok "복사 완료: $wsl_desktop/chrome-devtool-protocol.ps1"
    info "Windows에서 우클릭 → 'PowerShell로 실행' 하면 됩니다."
}

# =============================================================================
# 섹션 10: PATH 설정 안내
# =============================================================================

print_path_instructions() {
    if [[ ${#NEED_PATH_SETUP[@]} -eq 0 ]]; then
        return
    fi

    # 중복 제거
    local unique_paths
    mapfile -t unique_paths < <(printf '%s\n' "${NEED_PATH_SETUP[@]}" | sort -u)

    # 쉘 감지
    local rc_file
    if [[ "${SHELL:-}" == */zsh ]]; then
        rc_file="$HOME/.zshrc"
    else
        rc_file="$HOME/.bashrc"
    fi

    # rc 파일에 이미 등록된 경로 필터링
    local missing_paths=()
    for p in "${unique_paths[@]}"; do
        if grep -qF "\"${p}:" "$rc_file" 2>/dev/null || grep -qF "=${p}:" "$rc_file" 2>/dev/null; then
            ok "PATH 이미 등록됨: $p ($rc_file)"
        else
            missing_paths+=("$p")
        fi
    done

    if [[ ${#missing_paths[@]} -eq 0 ]]; then
        return
    fi

    echo
    section "PATH 설정 필요"
    warn "아래 경로가 현재 PATH에 없습니다. 쉘 설정 파일에 추가해야 설치된 도구를 사용할 수 있습니다."
    echo

    echo -e "  ${CYAN}# 아래 내용을 ${rc_file} 에 추가하세요:${NC}"
    for p in "${missing_paths[@]}"; do
        echo -e "  ${CYAN}export PATH=\"${p}:\$PATH\"${NC}"
    done

    echo
    info "추가 후 적용: source ${rc_file}"
    echo

    if ask_yn "${rc_file}에 PATH를 지금 자동으로 추가할까요?"; then
        for p in "${missing_paths[@]}"; do
            echo "export PATH=\"${p}:\$PATH\"" >> "$rc_file"
            ok "PATH 추가됨: $p → $rc_file"
        done
        echo
        info "현재 세션에 즉시 적용하려면 다음을 실행하세요:"
        for p in "${missing_paths[@]}"; do
            echo -e "  ${CYAN}export PATH=\"${p}:\$PATH\"${NC}"
        done
    fi
}

# =============================================================================
# 메인
# =============================================================================

main() {
    echo -e "${BOLD}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║     팀 Claude Code 스킬 설치 스크립트           ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    info "스킬 소스 경로: $SCRIPT_DIR"
    info "스킬 설치 경로: $SKILLS_INSTALL_DIR"
    echo

    install_php_tools
    install_ctx7
    install_codex
    setup_context7_mcp
    install_agent_browser
    ask_skill_install_mode
    create_skill_links
    install_codex_skills
    copy_cdp_script_to_desktop
    print_path_instructions

    echo
    echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${NC}"
    ok "설치 완료!"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo
    info "Claude Code를 재시작하면 스킬이 활성화됩니다."
    info "스킬 확인: Claude Code에서 /skills list 실행"
    if $USE_CODEX; then
        info "Codex 스킬 확인: ~/.codex/skills/local/ 디렉토리"
    fi
}

main
