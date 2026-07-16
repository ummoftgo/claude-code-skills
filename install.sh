#!/usr/bin/env bash
# =============================================================================
# 팀 Claude Code 스킬·훅 설치 스크립트
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
SKILLS_DIR="$SCRIPT_DIR/skills"
AGENTS_DIR="$SCRIPT_DIR/agents"
HOOKS_DIR="$SCRIPT_DIR/hooks"
HOOK_CONFIG_TOOL="$HOOKS_DIR/workflow_hook_config.py"

# 설치 범위 (ask_install_scope에서 결정)
INSTALL_SCOPE="global"      # "global" | "project"
INSTALL_BASE_DIR="$HOME"    # 안전 검사 기준 경로 (global=HOME, project=PROJECT_DIR)

# 설치 대상 경로 (ask_install_scope에서 재설정)
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json"
CODEX_SKILLS_DIR="$HOME/.codex/skills/local"
CODEX_AGENTS_DIR="$HOME/.codex/agents"
CODEX_HOOKS_DIR="$HOME/.codex/hooks"
CODEX_HOOKS_FILE="$HOME/.codex/hooks.json"
CODEX_CONFIG_FILE="$HOME/.codex/config.toml"

LOCAL_BIN="$HOME/.local/bin"
NPM_GLOBAL="$HOME/.npm-global"

# PATH에 추가가 필요한 디렉토리를 추적
NEED_PATH_SETUP=()

# codex 사용 여부 (create_skill_links에서 참조)
USE_CODEX=true

# 스킬 설치 방식: "symlink" 또는 "copy"
SKILL_INSTALL_MODE="symlink"

# 설치 소유권 추적 매니페스트 (set_manifest_path에서 스코프 기준으로 확정)
MANIFEST_DIR="$HOME/.claude-code-skills"
MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"
MANIFEST_HEADER="#claude-code-skills-manifest v1"

# =============================================================================
# 유틸 함수
# =============================================================================

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
section() { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

# yes/no 질문 (기본값 y)
# 경로 입력값 정규화: 따옴표 제거, ~ 확장, 후행 슬래시 제거
normalize_path_input() {
    local input="$1"
    # 앞뒤 공백 제거
    input="${input#"${input%%[![:space:]]*}"}"
    input="${input%"${input##*[![:space:]]}"}"
    # 앞뒤 따옴표 제거 (드래그&드롭 시 붙는 경우)
    input="${input#\'}" ; input="${input%\'}"
    input="${input#\"}" ; input="${input%\"}"
    # ~ 확장
    input="${input/#\~/$HOME}"
    # 후행 슬래시 제거
    input="${input%/}"
    echo "$input"
}

ask_yn() {
    local prompt="$1"
    local reply
    read -rp "$(echo -e "${YELLOW}?${NC} ${prompt} [Y/n] ")" reply
    reply="${reply:-Y}"
    [[ "$reply" =~ ^[Yy]$ ]]
}

# 기본값 N 확인 (파괴적/소유권 불확실 분기용)
ask_yn_default_no() {
    local prompt="$1"
    local reply
    read -rp "$(echo -e "${YELLOW}?${NC} ${prompt} [y/N] ")" reply || reply=""
    reply="${reply:-N}"
    [[ "$reply" =~ ^[Yy]$ ]]
}

# =============================================================================
# 소유권 추적 헬퍼 (매니페스트 + 심볼릭 링크 검증 + 내용 해시)
# =============================================================================

# 스코프(INSTALL_BASE_DIR) 기준으로 매니페스트 경로 확정
set_manifest_path() {
    MANIFEST_DIR="$INSTALL_BASE_DIR/.claude-code-skills"
    MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"
}

# 파일/디렉터리 내용 지문(해시). 실패 시 "-". 항상 0 반환.
content_hash() {
    local path="$1" h="-"
    if [[ -d "$path" ]]; then
        h="$( { cd "$path" 2>/dev/null && find . -type f -print0 2>/dev/null \
                | LC_ALL=C sort -z | xargs -0 sha256sum 2>/dev/null; } \
              | sha256sum 2>/dev/null | awk '{print $1}' )" || h="-"
    elif [[ -e "$path" ]]; then
        h="$(sha256sum "$path" 2>/dev/null | awk '{print $1}')" || h="-"
    fi
    [[ -n "$h" ]] || h="-"
    printf '%s\n' "$h"
}

# copy 스킬 디렉터리에 소유 마커 기록 (보조 신호). best-effort.
marker_write() {
    local dir="$1"
    [[ -d "$dir" ]] || return 0
    {
        printf 'repo=claude-code-skills\n'
        printf 'installed_at=%s\n' "$(date -u +%FT%TZ 2>/dev/null || echo '-')"
    } > "$dir/.installed-by" 2>/dev/null || true
}

# 매니페스트 헤더 보장
manifest_init() {
    mkdir -p "$MANIFEST_DIR" 2>/dev/null || { warn "매니페스트 디렉터리 생성 실패: $MANIFEST_DIR"; return 1; }
    if [[ ! -f "$MANIFEST_FILE" ]]; then
        printf '%s\n' "$MANIFEST_HEADER" > "$MANIFEST_FILE" 2>/dev/null || { warn "매니페스트 생성 실패"; return 1; }
    fi
}

# 한 항목 기록: type, abs_path, mode(symlink|copy|external), source, hash(선택)
# 경로 기준 dedupe 후 원자적 교체. best-effort(실패해도 설치는 진행).
manifest_record() {
    local type="$1" abs="$2" mode="$3" src="$4" hash="${5:--}"
    local ts; ts="$(date -u +%FT%TZ 2>/dev/null || echo '-')"
    manifest_init || return 0
    local tmp; tmp="$(mktemp "${MANIFEST_DIR}/.manifest.XXXXXX" 2>/dev/null)" || { warn "매니페스트 임시파일 실패"; return 0; }
    {
        printf '%s\n' "$MANIFEST_HEADER"
        if [[ -f "$MANIFEST_FILE" ]]; then
            awk -F'\t' -v p="$abs" '!/^#/ && $2!=p' "$MANIFEST_FILE" 2>/dev/null || true
        fi
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$type" "$abs" "$mode" "$src" "$hash" "$ts"
    } > "$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
    mv "$tmp" "$MANIFEST_FILE" 2>/dev/null || { rm -f "$tmp"; warn "매니페스트 갱신 실패"; return 0; }
}

# 대상 소유권 분류: ours | foreign | legacy-unverified | none
# $1=abs path, $2=name(목록 매칭용), $3=kind("skill"|"agent")
classify_ownership() {
    local target="$1" name="$2"
    if [[ ! -e "$target" && ! -L "$target" ]]; then echo "none"; return; fi

    local mline=""
    if [[ -f "$MANIFEST_FILE" ]]; then
        mline="$(awk -F'\t' -v p="$target" '!/^#/ && $2==p {print; exit}' "$MANIFEST_FILE" 2>/dev/null || true)"
    fi

    if [[ -L "$target" ]]; then
        local dest; dest="$(readlink -f "$target" 2>/dev/null || true)"
        if [[ -n "$dest" && ( "$dest" == "$SCRIPT_DIR/skills/"* || "$dest" == "$SCRIPT_DIR/agents/"* ) ]]; then
            echo "ours"; return
        fi
        # 깨진 링크(해석 실패/대상 없음) → 확증 불가, 기본 N 대상
        if [[ -z "$dest" || ! -e "$dest" ]]; then echo "legacy-unverified"; return; fi
        # 외부 실재 경로를 가리키는 동명 링크 → 보호
        echo "foreign"; return
    fi

    # 실제 파일/디렉터리: 매니페스트는 힌트일 뿐 — 현재 내용 해시로 확증
    if [[ -n "$mline" ]]; then
        local rec_hash cur_hash
        rec_hash="$(printf '%s' "$mline" | awk -F'\t' '{print $5}')"
        cur_hash="$(content_hash "$target")"
        if [[ "$rec_hash" != "-" && "$rec_hash" == "$cur_hash" ]]; then echo "ours"; return; fi
        echo "legacy-unverified"; return
    fi

    # 매니페스트 없음(유실/스코프 오선택): 내용으로 확증 불가 → 기본 N(legacy-unverified).
    # .installed-by 마커는 사람이 읽는 provenance 용도이며 소유권 판정에는 사용하지 않는다
    # (내용 검증 없이 ours로 단정하면 사용자가 수정한 복사본을 무확인 삭제할 위험).

    # 레거시/미검증: 이름이 목록에 있고 경계 안이면 기본 N, 아니면 외부
    if [[ -n "$name" && "${target}/" == "$INSTALL_BASE_DIR/"* ]]; then
        echo "legacy-unverified"; return
    fi
    echo "foreign"
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

# PHAR가 실제로 실행 가능한지 확인 (부분 다운로드 파일 감지)
phar_ok() {
    local name="$1"
    local path
    path="$(command -v "$name" 2>/dev/null)" || return 1
    # 파일 크기 1KB 미만이면 불완전한 파일로 간주
    [[ -s "$path" ]] && [[ "$(stat -c%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null)" -gt 1024 ]]
}

# PHAR 다운로드 후 실행 가능하게 설정
install_phar() {
    local name="$1"
    local url="$2"
    local dest="$LOCAL_BIN/$name"

    info "${name} 다운로드 중... (최대 120초)"
    local ok_download=false
    if command -v wget &>/dev/null; then
        wget -q --timeout=120 --tries=2 -O "$dest" "$url" && ok_download=true
    elif command -v curl &>/dev/null; then
        curl -fSL --max-time 120 --retry 1 "$url" -o "$dest" && ok_download=true
    else
        warn "wget 또는 curl이 필요합니다."
        return 1
    fi

    if ! $ok_download; then
        rm -f "$dest"
        warn "${name} 다운로드 실패 — 파일을 삭제했습니다. 나중에 다시 시도하세요."
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
        phar_ok "$tool" || { any_missing=true; break; }
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
    if phar_ok phpstan; then
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
    if phar_ok phpcs; then
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
    if phar_ok phpmd; then
        ok "phpmd 이미 설치됨"
    else
        if ask_install_mode "phpmd" \
            "~/.local/bin/phpmd 으로 설치" \
            "건너뜀"; then
            install_phar "phpmd" \
                "https://github.com/phpmd/phpmd/releases/latest/download/phpmd.phar"
        else
            skip "phpmd 건너뜀"
        fi
    fi

    # phpcpd
    if phar_ok phpcpd; then
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

    # --- Claude Code용 Codex 플러그인 설치 (codex-delegate 스킬이 우선 사용) ---
    install_codex_cc_plugin
}

# Claude Code에 OpenAI 공식 Codex 플러그인(codex@openai-codex)을 설치한다.
# codex-delegate 스킬은 이 플러그인이 있으면 슬래시 커맨드를, 없으면 codex CLI를 사용한다.
install_codex_cc_plugin() {
    local marketplace="openai-codex"
    local marketplace_source="openai/codex-plugin-cc"
    local plugin="codex@${marketplace}"

    echo
    info "Claude Code용 Codex 플러그인(${plugin}) 확인 중..."

    # claude CLI가 없으면 플러그인 설치를 진행할 수 없다.
    if ! command -v claude &>/dev/null; then
        skip "claude CLI를 찾을 수 없어 Codex 플러그인 설치를 건너뜁니다. (codex-delegate는 codex CLI로 폴백)"
        return
    fi

    # 이미 설치되어 있으면 그대로 둔다.
    if claude plugin list 2>/dev/null | grep -q "${plugin}"; then
        ok "Codex 플러그인이 이미 설치되어 있습니다 (${plugin})."
        return
    fi

    echo
    if ! ask_yn "Claude Code에 Codex 플러그인(${plugin})을 설치하시겠습니까?"; then
        skip "Codex 플러그인 건너뜀 (codex-delegate는 codex CLI로 폴백)"
        return
    fi

    # 마켓플레이스가 등록되어 있지 않으면 먼저 등록한다.
    if claude plugin marketplace list 2>/dev/null | grep -q "${marketplace}"; then
        ok "마켓플레이스 이미 등록됨 (${marketplace})"
    else
        info "마켓플레이스 등록 중: ${marketplace_source}"
        if ! claude plugin marketplace add "${marketplace_source}"; then
            warn "마켓플레이스 등록 실패. 수동으로 등록하세요: claude plugin marketplace add ${marketplace_source}"
            return
        fi
        ok "마켓플레이스 등록 완료 (${marketplace})"
    fi

    info "Codex 플러그인 설치 중: ${plugin}"
    if claude plugin install "${plugin}"; then
        ok "Codex 플러그인 설치 완료 (${plugin})"
        info "Claude Code를 재시작하면 /codex 슬래시 커맨드가 활성화됩니다."
    else
        warn "Codex 플러그인 설치 실패. 수동으로 설치하세요: claude plugin install ${plugin}"
    fi
}

# =============================================================================
# 섹션 4: context7 MCP 설정 (선택)
# =============================================================================

setup_context7_mcp() {
    section "context7 MCP 설정 (선택)"
    info "MCP를 설정하면 ctx7 CLI 없이도 Claude Code에서 자동으로 문서를 조회합니다."

    if [[ "$INSTALL_SCOPE" == "project" ]]; then
        skip "프로젝트 설치 모드 — context7 MCP는 전역 설정입니다. 필요 시 별도로 추가하세요."
        return
    fi

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

    if [[ "$INSTALL_SCOPE" == "project" ]]; then
        skip "프로젝트 설치 모드 — agent-browser는 전역 스킬입니다. 필요 시 별도로 설치하세요."
        return
    fi

    # --- 스킬 설치 ---
    if [[ -d "$HOME/.claude/skills/agent-browser" ]]; then
        # 기존에 이미 있는 디렉터리는 이 스크립트가 설치한 것이라고 단정할 수 없으므로
        # 매니페스트에 자동 등록(adopt)하지 않는다 (§10.6). 제거 시 legacy-unverified로 기본 N 처리.
        ok "agent-browser 스킬이 이미 설치되어 있습니다 (이 스크립트 설치본이 아닐 수 있어 매니페스트 미등록)."
    else
        echo
        if ! ask_yn "agent-browser 스킬을 설치하시겠습니까?"; then
            skip "agent-browser 스킬 건너뜀 (web-browser-preview 스킬 미동작)"
        elif command -v npx &>/dev/null; then
            info "agent-browser 스킬 설치 중..."
            if npx skills add vercel-labs/agent-browser --skill agent-browser; then
                ok "agent-browser 스킬 설치 완료"
                # 신규 설치본은 내용 해시로 기록 → 제거 시 변경 없으면 ours로 검증 가능
                manifest_record agent-browser "$HOME/.claude/skills/agent-browser" external "vercel-labs/agent-browser" "$(content_hash "$HOME/.claude/skills/agent-browser")"
            else
                warn "agent-browser 스킬 설치 실패. 수동으로 설치하세요: npx skills add vercel-labs/agent-browser --skill agent-browser"
            fi
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
# 섹션 6: 설치 범위 + 방식 선택
# =============================================================================

ask_install_scope() {
    section "설치 범위 선택"
    echo -e "  ${BOLD}1)${NC} 전역 설치  — 모든 프로젝트에서 사용 (~/.claude/, ~/.codex/)"
    echo -e "  ${BOLD}2)${NC} 프로젝트  — 특정 프로젝트 디렉토리에만 설치"
    echo
    local choice
    while true; do
        read -rp "  선택 (1/2): " choice
        case "$choice" in
            1)
                INSTALL_SCOPE="global"
                INSTALL_BASE_DIR="$HOME"
                CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
                CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
                CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
                CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json"
                CODEX_SKILLS_DIR="$HOME/.codex/skills/local"
                CODEX_AGENTS_DIR="$HOME/.codex/agents"
                CODEX_HOOKS_DIR="$HOME/.codex/hooks"
                CODEX_HOOKS_FILE="$HOME/.codex/hooks.json"
                CODEX_CONFIG_FILE="$HOME/.codex/config.toml"
                ok "전역 설치 선택"
                return
                ;;
            2)
                INSTALL_SCOPE="project"
                echo
                local default_dir
                default_dir="$(dirname "$(pwd)")"
                read -re -i "$default_dir" -p "  프로젝트 경로: " input_dir
                local project_dir
                project_dir="$(normalize_path_input "${input_dir:-$default_dir}")"

                # 절대 경로로 정규화
                project_dir="$(cd "$project_dir" 2>/dev/null && pwd)" || {
                    warn "디렉토리를 찾을 수 없습니다: ${input_dir:-$default_dir}"
                    continue
                }

                INSTALL_BASE_DIR="$project_dir"
                CLAUDE_SKILLS_DIR="$project_dir/.claude/skills"
                CLAUDE_AGENTS_DIR="$project_dir/.claude/agents"
                CLAUDE_HOOKS_DIR="$project_dir/.claude/hooks"
                CLAUDE_SETTINGS_FILE="$project_dir/.claude/settings.json"
                CODEX_SKILLS_DIR="$project_dir/.codex/skills"
                CODEX_AGENTS_DIR="$project_dir/.codex/agents"
                CODEX_HOOKS_DIR="$project_dir/.codex/hooks"
                CODEX_HOOKS_FILE="$project_dir/.codex/hooks.json"
                CODEX_CONFIG_FILE="$project_dir/.codex/config.toml"
                ok "프로젝트 설치 선택: ${project_dir}"
                return
                ;;
            *) warn "1 또는 2를 입력하세요." ;;
        esac
    done
}

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
    local src="$SKILLS_DIR/$skill"
    local dst="$dst_dir/$skill"
    local mtype="claude-skill"
    [[ "$dst_dir" == "$CODEX_SKILLS_DIR" ]] && mtype="codex-skill"

    if [[ ! -d "$src" ]]; then
        warn "소스 디렉토리 없음: $src — 건너뜀"
        return
    fi

    if [[ "$SKILL_INSTALL_MODE" == "copy" ]]; then
        # 안전 검사: dst가 dst_dir 자체이거나 INSTALL_BASE_DIR 외부이면 거부
        if [[ -z "$skill" || "$dst" == "$dst_dir" || "$dst" == "$dst_dir/" || \
              "$dst/" != "$INSTALL_BASE_DIR/"* ]]; then
            warn "안전 검사 실패: 예상치 못한 경로 — 건너뜀 (${dst})"
            return
        fi

        if [[ -L "$dst" ]]; then
            local own; own="$(classify_ownership "$dst" "$skill" skill)"
            warn "${skill} 위치에 심볼릭 링크가 있습니다: $dst"
            local proceed=false
            if [[ "$own" == "ours" ]]; then
                proceed=true   # 우리 링크 → 확인 없이 파일로 대체
            else
                # foreign(외부) / legacy-unverified(깨진·미검증 링크) — 파괴적이므로 기본 N
                [[ "$own" == "foreign" ]] && warn "  이 링크는 이 저장소가 만든 것이 아닙니다 (외부 대상)." \
                                          || warn "  이 링크의 소유를 확증할 수 없습니다 (깨진/미검증 링크)."
                ask_yn_default_no "  그래도 제거하고 파일로 복사할까요?" && proceed=true
            fi
            if $proceed; then
                rm "$dst"
                cp -r "$src" "$dst"
                marker_write "$dst"
                manifest_record "$mtype" "$dst" copy "$src" "$(content_hash "$dst")"
                ok "${skill} → ${dst} (복사, 링크 대체)"
            else
                skip "${skill} 건너뜀"
            fi
        elif [[ -d "$dst" ]]; then
            local own; own="$(classify_ownership "$dst" "$skill" skill)"
            local proceed=false
            if [[ "$own" == "ours" ]]; then
                proceed=true   # 이 저장소가 설치한 항목 — 확인 없이 갱신
            else
                warn "${skill} 디렉토리가 이미 존재합니다: $dst"
                [[ "$own" == "foreign" ]] && warn "  이 저장소가 설치한 항목이 아닐 수 있습니다 (사용자/외부 자산)."
                ask_yn_default_no "  덮어쓰시겠습니까?" && proceed=true
            fi
            if $proceed; then
                rm -rf "$dst"
                cp -r "$src" "$dst"
                marker_write "$dst"
                manifest_record "$mtype" "$dst" copy "$src" "$(content_hash "$dst")"
                ok "${skill} → ${dst} (복사, 덮어씀)"
            else
                skip "${skill} 건너뜀"
            fi
        else
            cp -r "$src" "$dst"
            marker_write "$dst"
            manifest_record "$mtype" "$dst" copy "$src" "$(content_hash "$dst")"
            ok "${skill} → ${dst} (복사)"
        fi
    else
        # symlink mode
        if [[ -L "$dst" ]]; then
            local current_target
            current_target="$(readlink "$dst")"
            if [[ "$current_target" == "$src" ]]; then
                manifest_record "$mtype" "$dst" symlink "$src" "-"
                ok "${skill} 링크 이미 존재 (최신)"
            else
                local own; own="$(classify_ownership "$dst" "$skill" skill)"
                warn "${skill} 링크가 다른 경로를 가리킵니다: $current_target"
                local proceed=false
                if [[ "$own" == "ours" ]]; then
                    # 우리 저장소를 가리키는 링크 → 경로 갱신(기본 Y)
                    ask_yn "  링크를 현재 경로(${src})로 업데이트할까요?" && proceed=true
                else
                    # foreign(외부) / legacy-unverified(깨진·미검증) — 파괴적이므로 기본 N
                    [[ "$own" == "foreign" ]] && warn "  이 링크는 이 저장소가 만든 것이 아닙니다 (외부 대상)." \
                                              || warn "  이 링크의 소유를 확증할 수 없습니다 (깨진/미검증 링크)."
                    ask_yn_default_no "  현재 경로(${src})로 강제 업데이트할까요?" && proceed=true
                fi
                if $proceed; then
                    ln -sfn "$src" "$dst"
                    manifest_record "$mtype" "$dst" symlink "$src" "-"
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
            manifest_record "$mtype" "$dst" symlink "$src" "-"
            ok "${skill} → ${dst} (링크)"
        fi
    fi
}

# =============================================================================
# 섹션 7: Claude Code 스킬 설치
# =============================================================================

create_skill_links() {
    section "Claude Code 스킬 설치 → ${CLAUDE_SKILLS_DIR}"

    mkdir -p "$CLAUDE_SKILLS_DIR"

    # Claude + Codex 공용 스킬
    local shared_skills=(
        "use-context7"
        "plan-and-build"
        "systematic-debugging"
        "web-security-review"
        "web-parallel-dispatch"
        "code-quality-review"
        "branch-merge-review"
    )

    # Claude 전용 스킬
    local claude_only_skills=(
        "web-browser-preview"
    )

    if $USE_CODEX; then
        claude_only_skills+=("codex-delegate")
    else
        skip "codex-delegate 스킬 건너뜀 (Codex 미사용)"
    fi

    for skill in "${shared_skills[@]}" "${claude_only_skills[@]}"; do
        install_skill "$skill" "$CLAUDE_SKILLS_DIR"
    done
}

# =============================================================================
# 섹션 8: 개발 워크플로우 훅 설치 (Claude Code / Codex)
# =============================================================================

setup_workflow_hook() {
    local client="$1"
    local hooks_dir="$2"
    local settings_file="$3"
    local manifest_type="$4"
    local codex_config_file="${5:-}"
    local codex_base_config_file="${6:-}"

    section "개발 워크플로우 리마인더 훅 (${client})"
    info "새 프로젝트·기능 구현 요청에서 plan-and-build 스킬을 가볍게 상기시킵니다."
    info "작은 수정, 리뷰, 설명 요청에는 동작하지 않습니다."

    if ! command -v python3 &>/dev/null; then
        warn "python3가 없어 워크플로우 훅을 설치할 수 없습니다."
        return
    fi

    echo
    if ! ask_yn "${client}에 plan-and-build UserPromptSubmit 훅을 설치하시겠습니까?"; then
        skip "${client} 개발 워크플로우 훅 건너뜀"
        return
    fi

    local src="$HOOKS_DIR/workflow-reminder.py"
    local dst="$hooks_dir/claude-code-skills-workflow.py"
    if [[ ! -f "$src" ]]; then
        warn "훅 소스 파일 없음: $src"
        return 1
    fi
    if [[ ! -f "$HOOK_CONFIG_TOOL" ]]; then
        warn "훅 설정 도우미 없음: $HOOK_CONFIG_TOOL"
        return 1
    fi

    local outside_scope_approved=false
    local config_scope_args=(--allowed-root "$INSTALL_BASE_DIR")
    if python3 "$HOOK_CONFIG_TOOL" validate "$settings_file" "${config_scope_args[@]}"; then
        :
    else
        local validation_status=$?
        if [[ $validation_status -eq 3 ]]; then
            warn "훅 설정 대상이 선택한 설치 범위 밖에 있습니다: $settings_file"
            if ! ask_yn_default_no "  범위 밖의 워크플로우 파일 수정을 허용할까요?"; then
                skip "${client} 워크플로우 훅 건너뜀 — 설치 범위 밖 설정 보호"
                return
            fi
            outside_scope_approved=true
            config_scope_args+=(--allow-outside-root)
            if ! python3 "$HOOK_CONFIG_TOOL" validate "$settings_file" "${config_scope_args[@]}"; then
                warn "훅 설정 등록 실패: $settings_file 의 JSON 구조를 확인하세요."
                return 1
            fi
        else
            warn "훅 설정 등록 실패: $settings_file 의 JSON 구조를 확인하세요."
            return 1
        fi
    fi

    if python3 "$HOOK_CONFIG_TOOL" scope-status "$dst" --allowed-root "$INSTALL_BASE_DIR"; then
        :
    else
        local hook_scope_status=$?
        if [[ $hook_scope_status -eq 3 ]]; then
            warn "훅 파일 대상이 선택한 설치 범위 밖에 있습니다: $dst"
            if ! $outside_scope_approved && \
                ! ask_yn_default_no "  범위 밖의 워크플로우 파일 수정을 허용할까요?"; then
                skip "${client} 워크플로우 훅 건너뜀 — 설치 범위 밖 훅 파일 보호"
                return
            fi
            outside_scope_approved=true
        else
            warn "훅 파일 경로를 안전하게 확인할 수 없습니다: $dst"
            return 1
        fi
    fi

    if [[ -n "$codex_config_file" ]]; then
        local disabled_reason=""
        local disabled_args=()
        local enable_codex_hooks=false
        if [[ -n "$codex_base_config_file" ]]; then
            disabled_args+=(--base-config "$codex_base_config_file")
        fi
        if disabled_reason="$(python3 "$HOOK_CONFIG_TOOL" disabled-status "$codex_config_file" "${disabled_args[@]}")"; then
            warn "Codex 사용자·프로젝트 훅을 실행할 수 없는 설정입니다: $disabled_reason"
            warn "이 상태에서는 설치한 hooks.json 훅이 실행되지 않습니다: $codex_config_file"
            if ! ask_yn_default_no "  Codex 훅 기능을 활성화하고 워크플로우 훅을 설치할까요?"; then
                skip "Codex 워크플로우 훅 건너뜀 — 기존 비활성화 설정 유지"
                return
            fi
            enable_codex_hooks=true
        else
            local disabled_status=$?
            if [[ $disabled_status -eq 2 ]]; then
                warn "Codex 훅 활성화 상태를 확인할 수 없습니다: $codex_config_file"
                return 1
            fi
        fi

        if python3 "$HOOK_CONFIG_TOOL" inline-status "$codex_config_file"; then
            warn "Codex config.toml에 인라인 훅이 이미 있습니다: $codex_config_file"
            warn "같은 설정 계층에 hooks.json을 추가하면 Codex가 둘을 병합하고 시작 시 경고합니다."
            if ! ask_yn_default_no "  그래도 별도 hooks.json에 워크플로우 훅을 설치할까요?"; then
                skip "Codex 워크플로우 훅 건너뜀 — 기존 config.toml 훅 유지"
                return
            fi
        else
            local inline_status=$?
            if [[ $inline_status -eq 2 ]]; then
                warn "Codex 인라인 훅 설정을 확인할 수 없습니다: $codex_config_file"
                return 1
            fi
        fi

        if $enable_codex_hooks; then
            local enable_args=(--allowed-root "$INSTALL_BASE_DIR")
            if python3 "$HOOK_CONFIG_TOOL" enable-hooks "$codex_config_file" "${enable_args[@]}"; then
                :
            else
                local enable_status=$?
                if [[ $enable_status -eq 3 ]]; then
                    warn "Codex config.toml 대상이 선택한 설치 범위 밖에 있습니다: $codex_config_file"
                    if ! $outside_scope_approved && \
                        ! ask_yn_default_no "  범위 밖의 워크플로우 파일 수정을 허용할까요?"; then
                        skip "Codex 워크플로우 훅 건너뜀 — 설치 범위 밖 config.toml 보호"
                        return
                    fi
                    outside_scope_approved=true
                    enable_args+=(--allow-outside-root)
                    if ! python3 "$HOOK_CONFIG_TOOL" enable-hooks "$codex_config_file" "${enable_args[@]}"; then
                        warn "Codex 훅 기능을 활성화할 수 없습니다: $codex_config_file"
                        return 1
                    fi
                else
                    warn "Codex 훅 기능을 활성화할 수 없습니다: $codex_config_file"
                    return 1
                fi
            fi
            ok "Codex 훅 기능을 활성화했습니다: $codex_config_file"
        fi
    fi

    mkdir -p "$hooks_dir" "$(dirname "$settings_file")"

    local install_file=false
    local own=""
    if [[ ! -e "$dst" && ! -L "$dst" ]]; then
        install_file=true
    elif cmp -s "$src" "$dst" 2>/dev/null; then
        own="$(classify_ownership "$dst" "claude-code-skills-workflow.py" hook)"
        if [[ "$own" == "ours" ]]; then
            ok "워크플로우 훅 파일이 이미 최신입니다."
        else
            warn "동일한 훅 파일이 있지만 이 저장소가 설치한 항목인지 확인할 수 없습니다: $dst"
            if ask_yn_default_no "  이 저장소의 관리 대상으로 등록할까요?"; then
                ok "기존 훅 파일을 관리 대상으로 등록합니다."
            else
                skip "워크플로우 훅 건너뜀"
                return
            fi
        fi
    else
        own="$(classify_ownership "$dst" "claude-code-skills-workflow.py" hook)"
        if [[ "$own" == "ours" ]]; then
            install_file=true
        else
            warn "동명 훅 파일이 이미 있으며 이 저장소 소유로 확증할 수 없습니다: $dst"
            if ask_yn_default_no "  덮어쓰시겠습니까?"; then
                install_file=true
            else
                skip "워크플로우 훅 건너뜀"
                return
            fi
        fi
    fi

    local backup_dir=""
    local file_changed=false
    if $install_file; then
        if [[ -e "$dst" || -L "$dst" ]]; then
            backup_dir="$(mktemp -d "$hooks_dir/.workflow-backup.XXXXXX")" || {
                warn "기존 훅 백업 디렉터리를 만들 수 없습니다."
                return 1
            }
            if ! mv "$dst" "$backup_dir/original"; then
                rmdir "$backup_dir" 2>/dev/null || true
                warn "기존 훅 파일을 백업할 수 없습니다: $dst"
                return 1
            fi
        fi
        if ! cp "$src" "$dst" || ! chmod +x "$dst"; then
            rm -f "$dst" 2>/dev/null || true
            if [[ -n "$backup_dir" ]]; then
                mv "$backup_dir/original" "$dst" 2>/dev/null || true
                rmdir "$backup_dir" 2>/dev/null || true
            fi
            warn "워크플로우 훅 파일을 설치할 수 없습니다: $dst"
            return 1
        fi
        file_changed=true
        ok "워크플로우 훅 파일 → $dst"
    fi

    if ! python3 "$HOOK_CONFIG_TOOL" install "$settings_file" "$dst" "${config_scope_args[@]}"; then
        if $file_changed; then
            rm -f "$dst" 2>/dev/null || true
            if [[ -n "$backup_dir" ]]; then
                mv "$backup_dir/original" "$dst" 2>/dev/null || true
                rmdir "$backup_dir" 2>/dev/null || true
            fi
        fi
        warn "훅 설정 등록 실패 — 훅 파일 변경을 원복했습니다: $settings_file"
        return 1
    fi

    if [[ -n "$backup_dir" ]]; then
        rm -rf "$backup_dir" 2>/dev/null || warn "임시 훅 백업 정리 실패: $backup_dir"
    fi
    manifest_record "$manifest_type" "$dst" copy "$src" "$(content_hash "$dst")"
    ok "${client} UserPromptSubmit 훅을 등록했습니다: $settings_file"
    if [[ "$client" == "Codex" ]]; then
        info "Codex를 다시 시작한 뒤 /hooks에서 새 훅을 검토하고 신뢰하세요."
    fi
}

# =============================================================================
# 섹션 9: Codex 스킬 설치 (선택)
# =============================================================================

install_codex_skills() {
    section "Codex 스킬 설치 (선택)"

    if ! $USE_CODEX; then
        skip "Codex 미사용 — Codex 스킬 설치 건너뜀"
        return
    fi

    if [[ ! -d "$HOME/.codex" ]]; then
        warn "~/.codex 디렉토리가 없습니다. Codex가 설치되어 있는지 확인하세요."
        return
    fi

    echo
    if ! ask_yn "Codex에도 스킬을 설치하시겠습니까?"; then
        skip "Codex 스킬 설치 건너뜀"
        return
    fi

    mkdir -p "$CODEX_SKILLS_DIR"

    # Codex에는 codex-delegate만 제외 (Claude→Codex 위임 전용 스킬)
    local codex_skills=(
        "use-context7"
        "plan-and-build"
        "systematic-debugging"
        "web-security-review"
        "web-parallel-dispatch"
        "code-quality-review"
        "branch-merge-review"
        "web-browser-preview"
    )

    echo
    for skill in "${codex_skills[@]}"; do
        install_skill "$skill" "$CODEX_SKILLS_DIR"
    done

    local codex_base_config_file=""
    if [[ "$INSTALL_SCOPE" == "project" ]]; then
        codex_base_config_file="$HOME/.codex/config.toml"
    fi
    setup_workflow_hook "Codex" "$CODEX_HOOKS_DIR" "$CODEX_HOOKS_FILE" \
        "codex-hook" "$CODEX_CONFIG_FILE" "$codex_base_config_file"
}

# =============================================================================
# 섹션 10: 에이전트 설치 (Claude + Codex)
# =============================================================================

install_agents() {
    section "에이전트 설치 (php-backend-developer / frontend-developer / security-auditor)"
    info "역할별 페르소나 에이전트를 Claude와 Codex에 설치합니다."

    local agent_names=("php-backend-developer" "frontend-developer" "security-auditor")
    local any_installed=false

    echo

    # Claude 에이전트 설치
    if ask_yn "Claude 에이전트를 설치하시겠습니까? (~/.claude/agents/)"; then
        mkdir -p "$CLAUDE_AGENTS_DIR"
        for agent in "${agent_names[@]}"; do
            local src="$AGENTS_DIR/$agent/claude.md"
            local dst="$CLAUDE_AGENTS_DIR/${agent}.md"

            if [[ ! -f "$src" ]]; then
                warn "파일 없음: $src — 건너뜀"
                continue
            fi

            # 안전 검사 (Codex 에이전트 분기와 동일하게 INSTALL_BASE_DIR 기준)
            if [[ -z "$agent" || "${dst}/" != "$INSTALL_BASE_DIR/"* ]]; then
                warn "안전 검사 실패: $dst — 건너뜀"
                continue
            fi

            # 기존 항목이 있으면 소유권 확인 후 덮어쓰기 (foreign/레거시는 기본 N)
            if [[ -e "$dst" || -L "$dst" ]]; then
                local own; own="$(classify_ownership "$dst" "$agent" agent)"
                if [[ "$own" != "ours" && "$own" != "none" ]]; then
                    warn "${agent}.md 이(가) 이미 있습니다: $dst"
                    [[ "$own" == "foreign" ]] && warn "  이 저장소가 설치한 항목이 아닐 수 있습니다."
                    if ! ask_yn_default_no "  덮어쓰시겠습니까?"; then
                        skip "${agent}.md 건너뜀"
                        continue
                    fi
                fi
            fi

            if [[ "$SKILL_INSTALL_MODE" == "symlink" ]]; then
                ln -sfn "$src" "$dst"
                manifest_record claude-agent "$dst" symlink "$src" "-"
                ok "${agent} → ~/.claude/agents/${agent}.md (링크)"
            else
                cp "$src" "$dst"
                manifest_record claude-agent "$dst" copy "$src" "$(content_hash "$dst")"
                ok "${agent} → ~/.claude/agents/${agent}.md (복사)"
            fi
        done
        any_installed=true
    else
        skip "Claude 에이전트 건너뜀"
    fi

    # Codex 에이전트 설치
    if $USE_CODEX; then
        echo
        if ask_yn "Codex 에이전트를 설치하시겠습니까? (~/.codex/agents/)"; then
            if [[ ! -d "$HOME/.codex" ]]; then
                warn "~/.codex 디렉토리가 없습니다. Codex가 설치되어 있는지 확인하세요."
            else
                mkdir -p "$CODEX_AGENTS_DIR"
                for agent in "${agent_names[@]}"; do
                    local src="$AGENTS_DIR/$agent/codex.toml"
                    local dst="$CODEX_AGENTS_DIR/${agent}.toml"

                    if [[ ! -f "$src" ]]; then
                        warn "파일 없음: $src — 건너뜀"
                        continue
                    fi

                    if [[ -z "$agent" || "${dst}/" != "$INSTALL_BASE_DIR/"* ]]; then
                        warn "안전 검사 실패: $dst — 건너뜀"
                        continue
                    fi

                    # 기존 항목이 있으면 소유권 확인 후 덮어쓰기 (foreign/레거시는 기본 N)
                    if [[ -e "$dst" || -L "$dst" ]]; then
                        local own; own="$(classify_ownership "$dst" "$agent" agent)"
                        if [[ "$own" != "ours" && "$own" != "none" ]]; then
                            warn "${agent}.toml 이(가) 이미 있습니다: $dst"
                            [[ "$own" == "foreign" ]] && warn "  이 저장소가 설치한 항목이 아닐 수 있습니다."
                            if ! ask_yn_default_no "  덮어쓰시겠습니까?"; then
                                skip "${agent}.toml 건너뜀"
                                continue
                            fi
                        fi
                    fi

                    if [[ "$SKILL_INSTALL_MODE" == "symlink" ]]; then
                        ln -sfn "$src" "$dst"
                        manifest_record codex-agent "$dst" symlink "$src" "-"
                        ok "${agent} → ~/.codex/agents/${agent}.toml (링크)"
                    else
                        cp "$src" "$dst"
                        manifest_record codex-agent "$dst" copy "$src" "$(content_hash "$dst")"
                        ok "${agent} → ~/.codex/agents/${agent}.toml (복사)"
                    fi
                done
                any_installed=true
            fi
        else
            skip "Codex 에이전트 건너뜀"
        fi
    fi

    if $any_installed; then
        info "에이전트는 Claude/Codex 재시작 후 활성화됩니다."
    fi
}

# =============================================================================
# 섹션 11: Chrome DevTool Protocol 스크립트 → Windows 바탕화면 복사
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
# 섹션 12: PATH 설정 안내
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
        if grep -qF "${p}" "$rc_file" 2>/dev/null; then
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
    echo "║      팀 AI 스킬·훅·에이전트 설치 스크립트      ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    info "소스 경로: $SCRIPT_DIR"
    info "스킬: skills/  훅: hooks/  에이전트: agents/"
    echo

    install_php_tools
    install_ctx7
    install_codex
    ask_install_scope
    set_manifest_path
    setup_context7_mcp
    install_agent_browser
    ask_skill_install_mode
    create_skill_links
    setup_workflow_hook "Claude Code" "$CLAUDE_HOOKS_DIR" "$CLAUDE_SETTINGS_FILE" "claude-hook"
    install_codex_skills
    install_agents
    copy_cdp_script_to_desktop
    print_path_instructions

    echo
    echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${NC}"
    ok "설치 완료!"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo
    info "Claude Code를 재시작하면 스킬, 훅, 에이전트가 활성화됩니다."
    if [[ "$INSTALL_SCOPE" == "global" ]]; then
        info "스킬 확인: Claude Code에서 /skills list 실행"
        if $USE_CODEX; then
            info "Codex 스킬: $CODEX_SKILLS_DIR"
            info "Codex 에이전트: $CODEX_AGENTS_DIR"
        fi
    else
        info "설치된 프로젝트 경로: $INSTALL_BASE_DIR"
        info "Claude 스킬: $CLAUDE_SKILLS_DIR"
        info "Claude 에이전트: $CLAUDE_AGENTS_DIR"
        if $USE_CODEX; then
            info "Codex 스킬: $CODEX_SKILLS_DIR"
            info "Codex 에이전트: $CODEX_AGENTS_DIR"
        fi
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main
fi
