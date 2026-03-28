#!/usr/bin/env bash
# =============================================================================
# 팀 AI 스킬 & 에이전트 제거 스크립트
# 설치된 스킬/에이전트 링크/파일만 제거합니다. 프로그램·패키지는 건드리지 않습니다.
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
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
CODEX_SKILLS_DIR="$HOME/.codex/skills/local"
CODEX_AGENTS_DIR="$HOME/.codex/agents"

# 제거 대상 스킬 목록
ALL_SKILLS=(
    "use-context7"
    "web-security-review"
    "web-parallel-dispatch"
    "web-browser-preview"
    "codex-delegate"
    "code-quality-review"
    "branch-merge-review"
)

# 제거 대상 에이전트 목록
ALL_AGENTS=(
    "php-backend-developer"
    "frontend-developer"
    "security-auditor"
)

# =============================================================================
# 유틸 함수
# =============================================================================

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
removed() { echo -e "${RED}[삭제]${NC}  $*"; }
section() { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

ask_yn() {
    local prompt="$1"
    local reply
    read -rp "$(echo -e "${YELLOW}?${NC} ${prompt} [Y/n] ")" reply
    reply="${reply:-Y}"
    [[ "$reply" =~ ^[Yy]$ ]]
}

# 스킬 하나를 제거 (심볼릭 링크 또는 복사된 디렉토리 모두 처리)
remove_skill() {
    local skill="$1"
    local base_dir="$2"
    local target="$base_dir/$skill"

    if [[ -L "$target" ]]; then
        # 심볼릭 링크 — 링크만 제거 (원본 파일 보존)
        local link_dest
        link_dest="$(readlink "$target")"
        rm "$target"
        removed "${skill} 링크 제거 (원본: ${link_dest})"

    elif [[ -d "$target" ]]; then
        # 복사된 디렉토리 — 내용 포함 삭제 전 확인

        # 안전 검사: target이 base_dir 자체이거나 HOME 외부이면 거부
        if [[ -z "$skill" || "$target" == "$base_dir" || "$target" == "$base_dir/" || \
              "$target/" != "$HOME/"* ]]; then
            warn "안전 검사 실패: 예상치 못한 경로 — 건너뜀 (${target})"
            return
        fi

        warn "${skill} 은 복사 방식으로 설치되어 있습니다: ${target}"
        if ask_yn "  디렉토리를 삭제하시겠습니까?"; then
            rm -rf "$target"
            removed "${skill} 디렉토리 삭제"
        else
            skip "${skill} 건너뜀"
        fi

    else
        skip "${skill} — 설치된 항목 없음"
    fi
}

# =============================================================================
# 섹션 1: Claude Code 스킬 제거
# =============================================================================

remove_claude_skills() {
    section "Claude Code 스킬 제거 (${CLAUDE_SKILLS_DIR})"

    if [[ ! -d "$CLAUDE_SKILLS_DIR" ]]; then
        info "~/.claude/skills/ 디렉토리가 없습니다. 건너뜁니다."
        return
    fi

    # 설치된 스킬 목록 미리 확인
    local installed=()
    for skill in "${ALL_SKILLS[@]}"; do
        local target="$CLAUDE_SKILLS_DIR/$skill"
        [[ -L "$target" || -d "$target" ]] && installed+=("$skill")
    done

    if [[ ${#installed[@]} -eq 0 ]]; then
        ok "제거할 스킬이 없습니다."
        return
    fi

    echo
    info "설치된 스킬:"
    for skill in "${installed[@]}"; do
        local target="$CLAUDE_SKILLS_DIR/$skill"
        if [[ -L "$target" ]]; then
            echo -e "    ${CYAN}[링크]${NC} $skill → $(readlink "$target")"
        else
            echo -e "    ${CYAN}[복사]${NC} $skill"
        fi
    done

    echo
    if ! ask_yn "위 스킬을 모두 제거하시겠습니까?"; then
        echo
        info "개별 선택으로 진행합니다."
        for skill in "${installed[@]}"; do
            if ask_yn "  ${skill} 제거?"; then
                remove_skill "$skill" "$CLAUDE_SKILLS_DIR"
            else
                skip "$skill"
            fi
        done
    else
        for skill in "${installed[@]}"; do
            remove_skill "$skill" "$CLAUDE_SKILLS_DIR"
        done
    fi
}

# =============================================================================
# 섹션 2: Codex 스킬 제거
# =============================================================================

remove_codex_skills() {
    section "Codex 스킬 제거 (${CODEX_SKILLS_DIR})"

    if [[ ! -d "$CODEX_SKILLS_DIR" ]]; then
        skip "~/.codex/skills/local/ 디렉토리 없음 — 건너뜁니다."
        return
    fi

    # codex-delegate는 Codex에 설치되지 않으므로 제외
    local codex_skills=(
        "use-context7"
        "web-security-review"
        "web-parallel-dispatch"
        "web-browser-preview"
        "code-quality-review"
    )

    local installed=()
    for skill in "${codex_skills[@]}"; do
        local target="$CODEX_SKILLS_DIR/$skill"
        [[ -L "$target" || -d "$target" ]] && installed+=("$skill")
    done

    if [[ ${#installed[@]} -eq 0 ]]; then
        ok "Codex에 제거할 스킬이 없습니다."
        return
    fi

    echo
    info "Codex에 설치된 스킬:"
    for skill in "${installed[@]}"; do
        local target="$CODEX_SKILLS_DIR/$skill"
        if [[ -L "$target" ]]; then
            echo -e "    ${CYAN}[링크]${NC} $skill → $(readlink "$target")"
        else
            echo -e "    ${CYAN}[복사]${NC} $skill"
        fi
    done

    echo
    if ! ask_yn "위 Codex 스킬을 모두 제거하시겠습니까?"; then
        echo
        info "개별 선택으로 진행합니다."
        for skill in "${installed[@]}"; do
            if ask_yn "  ${skill} 제거?"; then
                remove_skill "$skill" "$CODEX_SKILLS_DIR"
            else
                skip "$skill"
            fi
        done
    else
        for skill in "${installed[@]}"; do
            remove_skill "$skill" "$CODEX_SKILLS_DIR"
        done
    fi
}

# =============================================================================
# 섹션 3: context7 MCP 설정 제거
# =============================================================================

remove_context7_mcp() {
    section "context7 MCP 설정 제거"

    local settings_file="$HOME/.claude/settings.json"

    if [[ ! -f "$settings_file" ]] || ! grep -q "context7" "$settings_file" 2>/dev/null; then
        skip "context7 MCP 설정 없음 — 건너뜁니다."
        return
    fi

    echo
    if ! ask_yn "~/.claude/settings.json 에서 context7 MCP 설정을 제거하시겠습니까?"; then
        skip "context7 MCP 설정 유지"
        return
    fi

    python3 - "$settings_file" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    data = json.load(f)

removed = data.get("mcpServers", {}).pop("context7", None)
if removed is None:
    print("context7 항목을 찾을 수 없습니다.")
    sys.exit(0)

# mcpServers가 비면 키 자체를 제거
if "mcpServers" in data and not data["mcpServers"]:
    del data["mcpServers"]

with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
    ok "context7 MCP 설정 제거 완료"
}

# =============================================================================
# 섹션 4: 에이전트 제거 (Claude + Codex)
# =============================================================================

remove_agents() {
    section "에이전트 제거 (Claude + Codex)"

    # --- Claude 에이전트 ---
    local claude_installed=()
    for agent in "${ALL_AGENTS[@]}"; do
        local f="$CLAUDE_AGENTS_DIR/${agent}.md"
        [[ -L "$f" || -f "$f" ]] && claude_installed+=("$agent")
    done

    if [[ ${#claude_installed[@]} -gt 0 ]]; then
        echo
        info "Claude 에이전트 (${CLAUDE_AGENTS_DIR}):"
        for agent in "${claude_installed[@]}"; do
            local f="$CLAUDE_AGENTS_DIR/${agent}.md"
            [[ -L "$f" ]] && echo -e "    ${CYAN}[링크]${NC} ${agent}.md" \
                          || echo -e "    ${CYAN}[파일]${NC} ${agent}.md"
        done
        echo
        if ask_yn "위 Claude 에이전트를 모두 제거하시겠습니까?"; then
            for agent in "${claude_installed[@]}"; do
                local f="$CLAUDE_AGENTS_DIR/${agent}.md"
                # 안전 검사
                if [[ "${f}/" != "$HOME/"* ]]; then
                    warn "안전 검사 실패: $f — 건너뜀"
                    continue
                fi
                rm "$f"
                removed "${agent}.md 제거"
            done
        else
            skip "Claude 에이전트 유지"
        fi
    else
        skip "Claude 에이전트 — 설치된 항목 없음"
    fi

    # --- Codex 에이전트 ---
    if [[ ! -d "$CODEX_AGENTS_DIR" ]]; then
        skip "Codex 에이전트 — ~/.codex/agents 없음"
        return
    fi

    local codex_installed=()
    for agent in "${ALL_AGENTS[@]}"; do
        local f="$CODEX_AGENTS_DIR/${agent}.toml"
        [[ -L "$f" || -f "$f" ]] && codex_installed+=("$agent")
    done

    if [[ ${#codex_installed[@]} -gt 0 ]]; then
        echo
        info "Codex 에이전트 (${CODEX_AGENTS_DIR}):"
        for agent in "${codex_installed[@]}"; do
            local f="$CODEX_AGENTS_DIR/${agent}.toml"
            [[ -L "$f" ]] && echo -e "    ${CYAN}[링크]${NC} ${agent}.toml" \
                          || echo -e "    ${CYAN}[파일]${NC} ${agent}.toml"
        done
        echo
        if ask_yn "위 Codex 에이전트를 모두 제거하시겠습니까?"; then
            for agent in "${codex_installed[@]}"; do
                local f="$CODEX_AGENTS_DIR/${agent}.toml"
                if [[ "${f}/" != "$HOME/"* ]]; then
                    warn "안전 검사 실패: $f — 건너뜀"
                    continue
                fi
                rm "$f"
                removed "${agent}.toml 제거"
            done
        else
            skip "Codex 에이전트 유지"
        fi
    else
        skip "Codex 에이전트 — 설치된 항목 없음"
    fi
}

# =============================================================================
# 메인
# =============================================================================

main() {
    echo -e "${BOLD}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║     팀 AI 스킬 & 에이전트 제거 스크립트         ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    info "프로그램·패키지(phpstan, codex 등)는 제거하지 않습니다."
    info "스킬/에이전트 링크·파일과 MCP 설정만 제거합니다."

    remove_claude_skills
    remove_codex_skills
    remove_agents
    remove_context7_mcp

    echo
    echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${NC}"
    ok "제거 완료!"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo
    info "Claude Code / Codex를 재시작하면 비활성화됩니다."
}

main
