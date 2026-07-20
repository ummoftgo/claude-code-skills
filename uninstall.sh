#!/usr/bin/env bash
# =============================================================================
# 팀 AI 스킬·훅·에이전트 제거 스크립트
# 설치된 스킬/훅/에이전트 링크·파일만 제거합니다. 프로그램·패키지는 건드리지 않습니다.
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
HOOK_CONFIG_TOOL="$SCRIPT_DIR/hooks/workflow_hook_config.py"
COMPONENT_CATALOG="$SCRIPT_DIR/components.json"
CATALOG_TOOL="$SCRIPT_DIR/scripts/catalog.py"
MANIFEST_TOOL="$SCRIPT_DIR/scripts/manifest.py"

# 제거 범위 (ask_uninstall_scope에서 결정)
UNINSTALL_SCOPE="global"    # "global" | "project"
INSTALL_BASE_DIR="$HOME"    # 안전 검사 기준 경로

# 제거 대상 경로 (ask_uninstall_scope에서 재설정)
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json"
CODEX_SKILLS_DIR="$HOME/.agents/skills"
CODEX_AGENTS_DIR="$HOME/.codex/agents"
CODEX_HOOKS_DIR="$HOME/.codex/hooks"
CODEX_HOOKS_FILE="$HOME/.codex/hooks.json"

# 설치 소유권 추적 매니페스트 (set_manifest_path에서 스코프 기준으로 확정)
MANIFEST_DIR="$HOME/.claude-code-skills"
MANIFEST_FILE="$MANIFEST_DIR/manifest.json"
LEGACY_MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"

# 제거 대상 스킬 목록
ALL_SKILLS=()

# 제거 대상 에이전트 목록
ALL_AGENTS=()

# =============================================================================
# 유틸 함수
# =============================================================================

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
removed() { echo -e "${RED}[삭제]${NC}  $*"; }
section() { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

# 경로 입력값 정규화: 따옴표 제거, ~ 확장, 후행 슬래시 제거
normalize_path_input() {
    local input="$1"
    input="${input#"${input%%[![:space:]]*}"}"
    input="${input%"${input##*[![:space:]]}"}"
    input="${input#\'}" ; input="${input%\'}"
    input="${input#\"}" ; input="${input%\"}"
    input="${input/#\~/$HOME}"
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
    MANIFEST_FILE="$MANIFEST_DIR/manifest.json"
    LEGACY_MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"
    python3 "$MANIFEST_TOOL" import-v1 --manifest "$MANIFEST_FILE" \
        --legacy "$LEGACY_MANIFEST_FILE" --scope "$UNINSTALL_SCOPE" 2>/dev/null || \
        warn "v1 매니페스트를 읽을 수 없습니다: $LEGACY_MANIFEST_FILE"
    mapfile -t ALL_SKILLS < <(catalog_names skill claude)
    mapfile -t ALL_AGENTS < <(catalog_names agent claude)
}

catalog_names() {
    python3 "$CATALOG_TOOL" "$COMPONENT_CATALOG" --kind "$1" --client "$2" --platform posix
}

manifest_hash() {
    python3 "$MANIFEST_TOOL" lookup --manifest "$MANIFEST_FILE" --target "$1" 2>/dev/null | \
        python3 -c 'import json,sys; print(json.load(sys.stdin).get("hash", "-"))' 2>/dev/null || true
}

manifest_has_entry() {
    [[ -f "$MANIFEST_FILE" ]] && python3 "$MANIFEST_TOOL" lookup --manifest "$MANIFEST_FILE" --target "$1" >/dev/null 2>&1
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

# 대상 소유권 분류: ours | foreign | legacy-unverified | none
# $1=abs path, $2=name(목록 매칭용), $3=kind("skill"|"agent")
classify_ownership() {
    local target="$1" name="$2"
    if [[ ! -e "$target" && ! -L "$target" ]]; then echo "none"; return; fi

    local rec_hash=""
    [[ -f "$MANIFEST_FILE" ]] && rec_hash="$(manifest_hash "$target")"

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
    if [[ -n "$rec_hash" ]]; then
        local cur_hash
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

# 매니페스트에서 해당 경로 라인 제거 (원자적). best-effort.
manifest_prune() {
    local abs="$1"
    [[ -f "$MANIFEST_FILE" ]] || return 0
    python3 "$MANIFEST_TOOL" prune --manifest "$MANIFEST_FILE" --target "$abs" 2>/dev/null || true
}

# =============================================================================
# 제거 범위 선택
# =============================================================================

ask_uninstall_scope() {
    section "제거 범위 선택"
    echo -e "  ${BOLD}1)${NC} 전역 제거  — 홈 디렉토리에서 제거 (~/.claude/, ~/.codex/)"
    echo -e "  ${BOLD}2)${NC} 프로젝트  — 특정 프로젝트 디렉토리에서만 제거"
    echo
    local choice
    while true; do
        read -rp "  선택 (1/2): " choice
        case "$choice" in
            1)
                UNINSTALL_SCOPE="global"
                INSTALL_BASE_DIR="$HOME"
                CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
                CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
                CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
                CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json"
                CODEX_SKILLS_DIR="$HOME/.agents/skills"
                CODEX_AGENTS_DIR="$HOME/.codex/agents"
                CODEX_HOOKS_DIR="$HOME/.codex/hooks"
                CODEX_HOOKS_FILE="$HOME/.codex/hooks.json"
                ok "전역 제거 선택"
                return
                ;;
            2)
                UNINSTALL_SCOPE="project"
                echo
                local default_dir
                default_dir="$(dirname "$(pwd)")"
                read -re -i "$default_dir" -p "  프로젝트 경로: " input_dir
                local project_dir
                project_dir="$(normalize_path_input "${input_dir:-$default_dir}")"

                project_dir="$(cd "$project_dir" 2>/dev/null && pwd)" || {
                    warn "디렉토리를 찾을 수 없습니다: ${input_dir:-$default_dir}"
                    continue
                }

                INSTALL_BASE_DIR="$project_dir"
                CLAUDE_SKILLS_DIR="$project_dir/.claude/skills"
                CLAUDE_AGENTS_DIR="$project_dir/.claude/agents"
                CLAUDE_HOOKS_DIR="$project_dir/.claude/hooks"
                CLAUDE_SETTINGS_FILE="$project_dir/.claude/settings.json"
                CODEX_SKILLS_DIR="$project_dir/.agents/skills"
                CODEX_AGENTS_DIR="$project_dir/.codex/agents"
                CODEX_HOOKS_DIR="$project_dir/.codex/hooks"
                CODEX_HOOKS_FILE="$project_dir/.codex/hooks.json"
                ok "프로젝트 제거 선택: ${project_dir}"
                return
                ;;
            *) warn "1 또는 2를 입력하세요." ;;
        esac
    done
}

# 스킬 하나를 제거 (심볼릭 링크 또는 복사된 디렉토리 모두 처리)
remove_skill() {
    local skill="$1"
    local base_dir="$2"
    local target="$base_dir/$skill"

    # 소유권 판정: 우리 것만 자동 제거, 외부는 보호, 레거시/미검증은 기본 N
    local own; own="$(classify_ownership "$target" "$skill" skill)"
    case "$own" in
        none)    skip "${skill} — 설치된 항목 없음"; return ;;
        foreign) warn "${skill} — 이 저장소가 설치한 항목이 아닙니다 — 보호(건너뜀): ${target}"; return ;;
    esac

    # 안전 검사: target이 base_dir 자체이거나 INSTALL_BASE_DIR 외부이면 거부
    if [[ -z "$skill" || "$target" == "$base_dir" || "$target" == "$base_dir/" || \
          "$target/" != "$INSTALL_BASE_DIR/"* ]]; then
        warn "안전 검사 실패: 예상치 못한 경로 — 건너뜀 (${target})"
        return
    fi

    if [[ -L "$target" ]]; then
        # 심볼릭 링크 — 링크만 제거 (원본 파일 보존)
        local link_dest; link_dest="$(readlink "$target" 2>/dev/null || true)"
        if [[ "$own" == "legacy-unverified" ]]; then
            warn "${skill} 링크의 소유를 확증할 수 없습니다 (깨진 링크 등): ${target}"
            skip "미확인 링크를 보존합니다. 필요한 경우 수동으로 정리하세요."
            return
        fi
        rm "$target"
        manifest_prune "$target"
        removed "${skill} 링크 제거 (원본: ${link_dest})"

    elif [[ -d "$target" ]]; then
        if [[ "$own" == "ours" ]]; then
            rm -rf "$target"
            manifest_prune "$target"
            removed "${skill} 디렉토리 삭제"
        else
            # legacy-unverified — 항상 보존
            warn "${skill} 은 복사 방식으로 설치되어 있으나 이 저장소 소유로 확증할 수 없습니다: ${target}"
            skip "미확인 디렉터리를 보존합니다. 필요한 경우 수동으로 정리하세요."
        fi

    else
        skip "${skill} — 설치된 항목 없음"
    fi
}

# =============================================================================
# 섹션 1: Claude Code 스킬 제거
# =============================================================================

# 한 디렉터리의 스킬 집합 제거.
# 소유권으로 라벨링 → 일괄 프롬프트 기본 N → ours만 자동, legacy는 개별 기본 N(remove_skill), foreign 보호.
# $1=base_dir, $2=표시 라벨, $3..=스킬 이름들
remove_skill_set() {
    local base_dir="$1" what="$2"; shift 2
    local names=("$@")
    local installed=() skill target own
    for skill in "${names[@]}"; do
        target="$base_dir/$skill"
        [[ -L "$target" || -d "$target" ]] && installed+=("$skill")
    done

    if [[ ${#installed[@]} -eq 0 ]]; then
        ok "${what}: 제거할 스킬이 없습니다."
        return
    fi

    echo
    info "${what} 설치된 스킬 (소유권 분류):"
    local has_removable=false
    for skill in "${installed[@]}"; do
        own="$(classify_ownership "$base_dir/$skill" "$skill" skill)"
        case "$own" in
            ours)              echo -e "    ${GREEN}[내 것]${NC}     $skill"; has_removable=true ;;
            legacy-unverified) echo -e "    ${YELLOW}[미검증·보존]${NC} $skill (자동 제거하지 않음)" ;;
            foreign)           echo -e "    ${CYAN}[외부·보호]${NC} $skill (제거하지 않음)" ;;
            *)                 echo -e "    ${CYAN}[?]${NC}        $skill" ;;
        esac
    done

    if ! $has_removable; then
        skip "${what}: 제거 대상(내 것/미검증)이 없습니다 — 외부 항목은 보호합니다."
        return
    fi

    echo
    if ! ask_yn_default_no "위 항목을 제거하시겠습니까? (내 것=자동, 미검증=개별 확인, 외부=보호)"; then
        skip "${what} 유지"
        return
    fi
    for skill in "${installed[@]}"; do
        remove_skill "$skill" "$base_dir"
    done
}

remove_claude_skills() {
    section "Claude Code 스킬 제거 (${CLAUDE_SKILLS_DIR})"

    if [[ ! -d "$CLAUDE_SKILLS_DIR" ]]; then
        info "~/.claude/skills/ 디렉토리가 없습니다. 건너뜁니다."
        return
    fi

    remove_skill_set "$CLAUDE_SKILLS_DIR" "Claude" "${ALL_SKILLS[@]}"
}

# =============================================================================
# 섹션 2: Codex 스킬 제거
# =============================================================================

remove_codex_skills() {
    section "Codex 스킬 제거 (${CODEX_SKILLS_DIR})"

    if [[ ! -d "$CODEX_SKILLS_DIR" ]]; then
        skip "Codex 스킬 디렉토리 없음 — 건너뜁니다: $CODEX_SKILLS_DIR"
        return
    fi

    local codex_skills=()
    mapfile -t codex_skills < <(catalog_names skill codex)

    remove_skill_set "$CODEX_SKILLS_DIR" "Codex" "${codex_skills[@]}"
}

# =============================================================================
# 섹션 3: 개발 워크플로우 훅 제거
# =============================================================================

remove_workflow_hook() {
    local client="$1"
    local hooks_dir="$2"
    local settings_file="$3"

    section "개발 워크플로우 리마인더 훅 제거 (${client})"

    local catalog_client="claude"
    [[ "$client" == "Codex" ]] && catalog_client="codex"
    if ! catalog_names hook "$catalog_client" | grep -qx 'workflow-reminder'; then
        skip "카탈로그에서 ${client} POSIX 훅 지원을 찾을 수 없습니다."
        return
    fi

    local target="$hooks_dir/claude-code-skills-workflow.py"
    local configured=false
    local config_invalid=false
    local outside_scope_approved=false
    local config_scope_args=(--allowed-root "$INSTALL_BASE_DIR")
    if [[ -e "$settings_file" || -L "$settings_file" ]]; then
        if [[ ! -f "$HOOK_CONFIG_TOOL" ]]; then
            warn "훅 설정 도우미 없음: $HOOK_CONFIG_TOOL"
            config_invalid=true
        else
            local validation_status=0
            if python3 "$HOOK_CONFIG_TOOL" validate "$settings_file" "${config_scope_args[@]}"; then
                :
            else
                validation_status=$?
            fi

            if [[ $validation_status -eq 3 ]]; then
                warn "훅 설정 대상이 선택한 제거 범위 밖에 있습니다: $settings_file"
                if ask_yn_default_no "  범위 밖의 워크플로우 파일 수정을 허용할까요?"; then
                    outside_scope_approved=true
                    config_scope_args+=(--allow-outside-root)
                    if ! python3 "$HOOK_CONFIG_TOOL" validate "$settings_file" "${config_scope_args[@]}"; then
                        config_invalid=true
                    fi
                else
                    warn "범위 밖 설정을 보존하기 위해 훅 제거를 중단합니다."
                    return 1
                fi
            elif [[ $validation_status -ne 0 ]]; then
                warn "훅 설정을 읽을 수 없습니다: $settings_file"
                config_invalid=true
            fi

            if ! $config_invalid; then
                if python3 "$HOOK_CONFIG_TOOL" status "$settings_file" "$target" "${config_scope_args[@]}"; then
                    configured=true
                else
                    local status_code=$?
                    if [[ $status_code -eq 2 || $status_code -eq 3 ]]; then
                        warn "훅 설정을 읽을 수 없습니다: $settings_file"
                        config_invalid=true
                    fi
                fi
            fi
        fi
    fi

    if [[ -e "$target" || -L "$target" ]]; then
        if python3 "$HOOK_CONFIG_TOOL" scope-status "$target" --allowed-root "$INSTALL_BASE_DIR"; then
            :
        else
            local hook_scope_status=$?
            if [[ $hook_scope_status -eq 3 ]]; then
                warn "훅 파일 대상이 선택한 제거 범위 밖에 있습니다: $target"
                if ! $outside_scope_approved && \
                    ! ask_yn_default_no "  범위 밖의 워크플로우 파일 수정을 허용할까요?"; then
                    warn "범위 밖 훅 파일을 보존하기 위해 제거를 중단합니다."
                    return 1
                fi
                outside_scope_approved=true
            else
                warn "훅 파일 경로를 안전하게 확인할 수 없습니다: $target"
                return 1
            fi
        fi

        local target_ownership
        target_ownership="$(classify_ownership "$target" "claude-code-skills-workflow.py" hook)"
        if [[ "$target_ownership" != "ours" ]]; then
            warn "훅 파일 소유를 확증할 수 없어 설정과 파일을 모두 보존합니다: $target"
            return
        fi
    fi

    if [[ ! -e "$target" && ! -L "$target" ]] && ! $configured && ! $config_invalid; then
        skip "개발 워크플로우 훅 없음 — 건너뜁니다."
        return
    fi
    if [[ ! -e "$target" && ! -L "$target" ]] && $configured && ! manifest_has_entry "$target"; then
        warn "매니페스트 소유 기록이 없어 훅 설정을 보존합니다: $settings_file"
        return
    fi

    echo
    if ! ask_yn "${client}의 개발 워크플로우 UserPromptSubmit 리마인더 훅을 제거하시겠습니까?"; then
        skip "${client} 개발 워크플로우 훅 유지"
        return
    fi

    if $config_invalid; then
        warn "설정을 안전하게 수정할 수 없어 훅 제거를 중단합니다. JSON 구조를 먼저 복구하세요."
        return 1
    fi

    if $configured; then
        if python3 "$HOOK_CONFIG_TOOL" remove "$settings_file" "$target" "${config_scope_args[@]}"; then
            removed "UserPromptSubmit 훅 설정 제거"
        else
            warn "훅 설정 제거 실패: $settings_file"
            return 1
        fi
    fi

    if [[ -e "$target" || -L "$target" ]]; then
        local own; own="$(classify_ownership "$target" "claude-code-skills-workflow.py" hook)"
        case "$own" in
            ours)
                rm "$target"
                manifest_prune "$target"
                removed "워크플로우 훅 파일 제거"
                ;;
            *) warn "훅 파일 소유를 확증할 수 없어 보존합니다: $target" ;;
        esac
    fi
    rmdir "$hooks_dir" 2>/dev/null || true
}

# =============================================================================
# 섹션 5: 에이전트 제거 (Claude + Codex)
# =============================================================================

# 에이전트 파일 하나 제거 (소유권 판정 + 매니페스트 프루닝)
# $1=abs path, $2=agent name, $3=확장자 라벨(md|toml)
remove_agent_file() {
    local f="$1" agent="$2" label="$3"
    local own; own="$(classify_ownership "$f" "$agent" agent)"
    case "$own" in
        none)    skip "${agent}.${label} — 설치된 항목 없음"; return ;;
        foreign) warn "${agent}.${label} — 이 저장소가 설치한 항목이 아닙니다 — 보호(건너뜀): ${f}"; return ;;
    esac
    if [[ "${f}/" != "$INSTALL_BASE_DIR/"* ]]; then
        warn "안전 검사 실패: $f — 건너뜀"; return
    fi
    if [[ "$own" != "ours" ]]; then
        warn "${agent}.${label} 의 소유를 확증할 수 없습니다 (레거시/수정됨): ${f}"
        skip "미확인 에이전트를 보존합니다. 필요한 경우 수동으로 정리하세요."
        return
    fi
    rm "$f"
    manifest_prune "$f"
    removed "${agent}.${label} 제거"
}

remove_agents() {
    section "에이전트 제거 (Claude + Codex)"

    local claude_agent_names=()
    local codex_agent_names=()
    mapfile -t claude_agent_names < <(catalog_names agent claude)
    mapfile -t codex_agent_names < <(catalog_names agent codex)

    # --- Claude 에이전트 ---
    local claude_installed=()
    for agent in "${claude_agent_names[@]}"; do
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
        if ask_yn "위 Claude 에이전트를 제거하시겠습니까? (외부/미검증 항목은 보호됩니다)"; then
            for agent in "${claude_installed[@]}"; do
                remove_agent_file "$CLAUDE_AGENTS_DIR/${agent}.md" "$agent" md
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
    for agent in "${codex_agent_names[@]}"; do
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
        if ask_yn "위 Codex 에이전트를 제거하시겠습니까? (외부/미검증 항목은 보호됩니다)"; then
            for agent in "${codex_installed[@]}"; do
                remove_agent_file "$CODEX_AGENTS_DIR/${agent}.toml" "$agent" toml
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
    echo "║      팀 AI 스킬·훅·에이전트 제거 스크립트      ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    info "프로그램·패키지(phpstan, codex 등)는 제거하지 않습니다."
    info "이 저장소가 소유한 스킬/훅/에이전트 링크·파일만 제거합니다."

    ask_uninstall_scope
    set_manifest_path
    remove_claude_skills
    remove_workflow_hook "Claude Code" "$CLAUDE_HOOKS_DIR" "$CLAUDE_SETTINGS_FILE"
    remove_codex_skills
    remove_workflow_hook "Codex" "$CODEX_HOOKS_DIR" "$CODEX_HOOKS_FILE"
    remove_agents

    echo
    echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${NC}"
    ok "제거 완료!"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo
    info "Claude Code / Codex를 재시작하면 비활성화됩니다."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main
fi
