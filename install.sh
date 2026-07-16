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
COMPONENT_CATALOG="$SCRIPT_DIR/components.json"
CATALOG_TOOL="$SCRIPT_DIR/scripts/catalog.py"
MANIFEST_TOOL="$SCRIPT_DIR/scripts/manifest.py"

# 설치 범위 (ask_install_scope에서 결정)
INSTALL_SCOPE="global"      # "global" | "project"
INSTALL_BASE_DIR="$HOME"    # 안전 검사 기준 경로 (global=HOME, project=PROJECT_DIR)

# 설치 대상 경로 (ask_install_scope에서 재설정)
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CLAUDE_AGENTS_DIR="$HOME/.claude/agents"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json"
CODEX_SKILLS_DIR="$HOME/.agents/skills"
CODEX_AGENTS_DIR="$HOME/.codex/agents"
CODEX_HOOKS_DIR="$HOME/.codex/hooks"
CODEX_HOOKS_FILE="$HOME/.codex/hooks.json"
CODEX_CONFIG_FILE="$HOME/.codex/config.toml"

# codex 사용 여부 (create_skill_links에서 참조)
USE_CODEX=true

# Claude의 skills/agents 디렉터리를 이번 실행에서 처음 만들었는지 추적한다.
CLAUDE_DIRECTORY_CREATED=false

# 스킬 설치 방식: "symlink" 또는 "copy"
SKILL_INSTALL_MODE="copy"

# 설치 소유권 추적 매니페스트 (set_manifest_path에서 스코프 기준으로 확정)
MANIFEST_DIR="$HOME/.claude-code-skills"
MANIFEST_FILE="$MANIFEST_DIR/manifest.json"
LEGACY_MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"

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
    MANIFEST_FILE="$MANIFEST_DIR/manifest.json"
    LEGACY_MANIFEST_FILE="$MANIFEST_DIR/manifest.tsv"
    python3 "$MANIFEST_TOOL" import-v1 --manifest "$MANIFEST_FILE" \
        --legacy "$LEGACY_MANIFEST_FILE" --scope "$INSTALL_SCOPE" 2>/dev/null || \
        warn "v1 매니페스트를 읽을 수 없습니다: $LEGACY_MANIFEST_FILE"
}

catalog_names() {
    python3 "$CATALOG_TOOL" "$COMPONENT_CATALOG" --kind "$1" --client "$2" --platform posix
}

catalog_source() {
    local args=("$COMPONENT_CATALOG" --kind "$1" --client "$2" --platform posix --field source)
    [[ -n "${3:-}" ]] && args+=(--name "$3")
    python3 "$CATALOG_TOOL" "${args[@]}" | head -1
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
}

# 한 항목 기록: type, abs_path, mode(symlink|copy|external), source, hash(선택)
# 경로 기준 dedupe 후 원자적 교체. 이전처럼 일반 설치에서는 best-effort로 사용한다.
manifest_record_required() {
    local type="$1" abs="$2" mode="$3" src="$4" hash="${5:--}"
    manifest_init || return 1
    local client="${type%%-*}" kind="${type#*-}" component
    component="$(basename "$abs")"
    [[ "$kind" == "agent" ]] && component="${component%.*}"
    [[ "$kind" == "hook" ]] && component="workflow-reminder"
    python3 "$MANIFEST_TOOL" record --manifest "$MANIFEST_FILE" \
        --platform posix --scope "$INSTALL_SCOPE" --client "$client" --kind "$kind" \
        --component "$component" --target "$abs" --method "$mode" --source "$src" --hash "$hash" \
        2>/dev/null || return 1
    python3 "$MANIFEST_TOOL" lookup --manifest "$MANIFEST_FILE" --target "$abs" >/dev/null 2>&1
}

manifest_record() {
    manifest_record_required "$@" || warn "매니페스트 갱신 실패: $2"
    return 0
}

# 새 항목을 같은 파일시스템의 임시 경로에 완성한 뒤 교체한다.
# 복사/링크/매니페스트 갱신 중 하나라도 실패하면 기존 대상을 복원한다.
install_staged_component() {
    local source="$1" target="$2" method="$3" manifest_type="$4"
    local parent base staging backup new_hash="-"
    parent="$(dirname "$target")"
    base="$(basename "$target")"
    mkdir -p "$parent" || return 1
    staging="$(mktemp -d "$parent/.${base}.install.XXXXXX")" || return 1
    rmdir "$staging" || return 1
    backup="$parent/.${base}.backup.$$"

    if [[ "$method" == "copy" ]]; then
        if ! cp -r "$source" "$staging"; then
            rm -rf "$staging" 2>/dev/null || true
            return 1
        fi
        marker_write "$staging"
        new_hash="$(content_hash "$staging")"
    else
        if ! ln -s "$source" "$staging"; then
            rm -f "$staging" 2>/dev/null || true
            return 1
        fi
    fi

    local had_target=false
    if [[ -e "$target" || -L "$target" ]]; then
        had_target=true
        rm -rf "$backup" 2>/dev/null || true
        if ! mv "$target" "$backup"; then
            rm -rf "$staging" 2>/dev/null || true
            return 1
        fi
    fi

    if ! mv "$staging" "$target"; then
        $had_target && mv "$backup" "$target" 2>/dev/null || true
        rm -rf "$staging" 2>/dev/null || true
        return 1
    fi

    if ! manifest_record_required "$manifest_type" "$target" "$method" "$source" "$new_hash"; then
        rm -rf "$target" 2>/dev/null || true
        $had_target && mv "$backup" "$target" 2>/dev/null || true
        return 1
    fi

    $had_target && rm -rf "$backup" 2>/dev/null || true
    return 0
}

manifest_hash() {
    python3 "$MANIFEST_TOOL" lookup --manifest "$MANIFEST_FILE" --target "$1" 2>/dev/null | \
        python3 -c 'import json,sys; print(json.load(sys.stdin).get("hash", "-"))' 2>/dev/null || true
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

# =============================================================================
# 설치 범위 + 방식 선택
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
                CODEX_SKILLS_DIR="$HOME/.agents/skills"
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
                CODEX_SKILLS_DIR="$project_dir/.agents/skills"
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
    echo -e "  ${BOLD}1)${NC} 파일 복사   — 기본값, 저장소 없이도 동작"
    echo -e "  ${BOLD}2)${NC} 심볼릭 링크 — 저장소 파일을 직접 참조"
    echo
    while true; do
        read -rp "  선택 (1/2): " choice
        case "$choice" in
            1) SKILL_INSTALL_MODE="copy";    ok "파일 복사 방식 선택";   return ;;
            2) SKILL_INSTALL_MODE="symlink"; ok "심볼릭 링크 방식 선택"; return ;;
            *) warn "1 또는 2를 입력하세요." ;;
        esac
    done
}

# install_skill <skill_name> <dst_dir>
# SKILL_INSTALL_MODE 에 따라 심볼릭 링크 또는 복사로 스킬을 설치한다.
install_skill() {
    local skill="$1"
    local dst_dir="$2"
    local catalog_client="claude"
    [[ "$dst_dir" == "$CODEX_SKILLS_DIR" ]] && catalog_client="codex"
    local source_relative
    source_relative="$(catalog_source skill "$catalog_client" "$skill")"
    local src="$SCRIPT_DIR/$source_relative"
    local dst="$dst_dir/$skill"
    local mtype="claude-skill"
    [[ "$dst_dir" == "$CODEX_SKILLS_DIR" ]] && mtype="codex-skill"

    if [[ -z "$source_relative" || ! -d "$src" ]]; then
        warn "소스 디렉토리 없음: $src — 건너뜀"
        return 0
    fi

    # 안전 검사: dst가 dst_dir 자체이거나 INSTALL_BASE_DIR 외부이면 거부
    if [[ -z "$skill" || "$dst" == "$dst_dir" || "$dst" == "$dst_dir/" || \
          "$dst/" != "$INSTALL_BASE_DIR/"* ]]; then
        warn "안전 검사 실패: 예상치 못한 경로 — 건너뜀 (${dst})"
        return 0
    fi

    # 스킬 대상은 디렉터리 또는 링크여야 한다. 동명 일반 파일은 항상 외부 자산으로 보존한다.
    if [[ -e "$dst" && ! -d "$dst" && ! -L "$dst" ]]; then
        warn "${skill} 위치에 동명 파일이 있습니다: $dst"
        skip "외부 파일을 보존하고 ${skill} 설치를 건너뜁니다."
        return 0
    fi

    if [[ "$SKILL_INSTALL_MODE" == "copy" ]]; then
        if [[ -e "$dst" || -L "$dst" ]]; then
            local own; own="$(classify_ownership "$dst" "$skill" skill)"
            if [[ "$own" != "ours" ]]; then
                warn "${skill} 대상의 저장소 소유를 확인할 수 없습니다: $dst"
                skip "기존 항목을 보존하고 ${skill} 설치를 건너뜁니다."
                return 0
            fi
        fi
        if install_staged_component "$src" "$dst" copy "$mtype"; then
            ok "${skill} → ${dst} (복사)"
        else
            warn "${skill} 복사 설치에 실패했습니다. 기존 항목은 보존했습니다: $dst"
        fi
        return 0
    fi

    # symlink mode
    if [[ -L "$dst" ]]; then
        local current_target
        current_target="$(readlink "$dst")"
        if [[ "$current_target" == "$src" ]]; then
            manifest_record "$mtype" "$dst" symlink "$src" "-"
            ok "${skill} 링크 이미 존재 (최신)"
            return 0
        fi
        local own; own="$(classify_ownership "$dst" "$skill" skill)"
        warn "${skill} 링크가 다른 경로를 가리킵니다: $current_target"
        if [[ "$own" != "ours" ]] || ! ask_yn "  링크를 현재 경로(${src})로 업데이트할까요?"; then
            skip "기존 링크를 보존하고 ${skill} 설치를 건너뜁니다."
            return 0
        fi
    elif [[ -d "$dst" ]]; then
        warn "${skill} 위치에 실제 디렉토리가 있습니다: $dst"
        skip "${skill} 건너뜀 (수동 처리 필요)"
        return 0
    fi

    if install_staged_component "$src" "$dst" symlink "$mtype"; then
        ok "${skill} → ${dst} (링크)"
    else
        warn "${skill} 링크 설치에 실패했습니다. 기존 항목은 보존했습니다: $dst"
    fi
    return 0
}

# =============================================================================
# 섹션 7: Claude Code 스킬 설치
# =============================================================================

create_skill_links() {
    section "Claude Code 스킬 설치 → ${CLAUDE_SKILLS_DIR}"

    [[ -d "$CLAUDE_SKILLS_DIR" ]] || CLAUDE_DIRECTORY_CREATED=true
    mkdir -p "$CLAUDE_SKILLS_DIR"

    local claude_skills=()
    mapfile -t claude_skills < <(catalog_names skill claude)
    for skill in "${claude_skills[@]}"; do
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

    local catalog_client="claude"
    [[ "$client" == "Codex" ]] && catalog_client="codex"
    local hook_source_relative
    hook_source_relative="$(catalog_source hook "$catalog_client" workflow-reminder)"
    if [[ -z "$hook_source_relative" ]]; then
        warn "카탈로그에서 ${client} POSIX 훅을 찾을 수 없습니다."
        return 1
    fi
    local src="$SCRIPT_DIR/$hook_source_relative"
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
            skip "POSIX 설치기는 config.toml을 자동 변경하지 않습니다. 수동 활성화 후 다시 실행하세요."
            return
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
            skip "소유권 미확인 훅을 보존하고 설치를 건너뜁니다."
            return
        fi
    else
        own="$(classify_ownership "$dst" "claude-code-skills-workflow.py" hook)"
        if [[ "$own" == "ours" ]]; then
            install_file=true
        else
            warn "동명 훅 파일이 이미 있으며 이 저장소 소유로 확증할 수 없습니다: $dst"
            skip "소유권 미확인 훅을 보존하고 설치를 건너뜁니다."
            return
        fi
    fi

    local backup_dir=""
    local file_changed=false
    local settings_snapshot_dir settings_existed=false
    settings_snapshot_dir="$(mktemp -d "${TMPDIR:-/tmp}/workflow-settings.XXXXXX")" || {
        warn "훅 설정 백업 디렉터리를 만들 수 없습니다."
        return 1
    }
    if [[ -e "$settings_file" || -L "$settings_file" ]]; then
        settings_existed=true
        if ! cp -p "$settings_file" "$settings_snapshot_dir/settings"; then
            rm -rf "$settings_snapshot_dir" 2>/dev/null || true
            warn "훅 설정을 백업할 수 없습니다: $settings_file"
            return 1
        fi
    fi
    if $install_file; then
        if [[ -e "$dst" || -L "$dst" ]]; then
            backup_dir="$(mktemp -d "$hooks_dir/.workflow-backup.XXXXXX")" || {
                rm -rf "$settings_snapshot_dir" 2>/dev/null || true
                warn "기존 훅 백업 디렉터리를 만들 수 없습니다."
                return 1
            }
            if ! mv "$dst" "$backup_dir/original"; then
                rmdir "$backup_dir" 2>/dev/null || true
                rm -rf "$settings_snapshot_dir" 2>/dev/null || true
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
            rm -rf "$settings_snapshot_dir" 2>/dev/null || true
            warn "워크플로우 훅 파일을 설치할 수 없습니다: $dst"
            return 1
        fi
        file_changed=true
        ok "워크플로우 훅 파일 → $dst"
    fi

    if ! python3 "$HOOK_CONFIG_TOOL" install "$settings_file" "$dst" "${config_scope_args[@]}"; then
        local settings_restored=true hook_restored=true
        if $settings_existed; then
            if ! cp -p "$settings_snapshot_dir/settings" "$settings_file" 2>/dev/null; then
                settings_restored=false
                warn "훅 설정 원복 실패 — 스냅샷을 보존합니다: $settings_snapshot_dir/settings"
            fi
        else
            rm -f "$settings_file" 2>/dev/null || { settings_restored=false; warn "새 훅 설정 제거 실패: $settings_file"; }
        fi
        if $file_changed; then
            rm -f "$dst" 2>/dev/null || hook_restored=false
            if [[ -n "$backup_dir" ]]; then
                if $hook_restored && mv "$backup_dir/original" "$dst" 2>/dev/null; then
                    rmdir "$backup_dir" 2>/dev/null || true
                else
                    hook_restored=false
                    warn "기존 훅 파일 원복 실패 — 백업을 보존합니다: $backup_dir/original"
                fi
            fi
        fi
        $settings_restored && rm -rf "$settings_snapshot_dir" 2>/dev/null || true
        warn "훅 설정 등록 실패 — 훅 파일 변경을 원복했습니다: $settings_file"
        return 1
    fi

    if ! manifest_record_required "$manifest_type" "$dst" copy "$src" "$(content_hash "$dst")"; then
        local settings_restored=true hook_restored=true
        if $settings_existed; then
            if ! cp -p "$settings_snapshot_dir/settings" "$settings_file" 2>/dev/null; then
                settings_restored=false
                warn "훅 설정 원복 실패 — 스냅샷을 보존합니다: $settings_snapshot_dir/settings"
            fi
        else
            rm -f "$settings_file" 2>/dev/null || { settings_restored=false; warn "새 훅 설정 제거 실패: $settings_file"; }
        fi
        if $file_changed; then
            rm -f "$dst" 2>/dev/null || hook_restored=false
            if [[ -n "$backup_dir" ]]; then
                if $hook_restored && mv "$backup_dir/original" "$dst" 2>/dev/null; then
                    rmdir "$backup_dir" 2>/dev/null || true
                else
                    hook_restored=false
                    warn "기존 훅 파일 원복 실패 — 백업을 보존합니다: $backup_dir/original"
                fi
            fi
        fi
        $settings_restored && rm -rf "$settings_snapshot_dir" 2>/dev/null || true
        warn "매니페스트 기록 실패 — 훅 파일과 설정을 원복했습니다: $dst"
        return 1
    fi

    if [[ -n "$backup_dir" ]]; then
        rm -rf "$backup_dir" 2>/dev/null || warn "임시 훅 백업 정리 실패: $backup_dir"
    fi
    rm -rf "$settings_snapshot_dir" 2>/dev/null || warn "임시 설정 백업 정리 실패: $settings_snapshot_dir"
    ok "${client} UserPromptSubmit 훅을 등록했습니다: $settings_file"
    if [[ "$client" == "Codex" ]]; then
        info "Codex를 다시 시작한 뒤 /hooks에서 새 훅을 검토하고 신뢰하세요."
    fi
}

# =============================================================================
# 섹션 9: Codex 스킬 설치 (선택)
# =============================================================================

migrate_legacy_codex_skills() {
    [[ "$INSTALL_SCOPE" == "global" ]] || return 0
    local legacy_dir="$HOME/.codex/skills/local"
    [[ -d "$legacy_dir" ]] || return 0

    local skill old_target new_target own
    local codex_skills=()
    mapfile -t codex_skills < <(catalog_names skill codex)
    for skill in "${codex_skills[@]}"; do
        old_target="$legacy_dir/$skill"
        new_target="$CODEX_SKILLS_DIR/$skill"
        [[ -e "$old_target" || -L "$old_target" ]] || continue
        if [[ -e "$new_target" || -L "$new_target" ]]; then
            warn "Codex 레거시 이전 충돌 — 두 항목을 모두 보존합니다: $skill"
            continue
        fi
        own="$(classify_ownership "$old_target" "$skill" skill)"
        if [[ "$own" != "ours" ]]; then
            warn "Codex 레거시 항목의 저장소 소유를 확인할 수 없어 보존합니다: $old_target"
            continue
        fi
        mkdir -p "$CODEX_SKILLS_DIR"
        local staging
        staging="$(mktemp -d "$CODEX_SKILLS_DIR/.${skill}.migrate.XXXXXX")" || {
            warn "Codex 레거시 이전 임시 경로를 만들 수 없습니다: $skill"
            continue
        }
        rmdir "$staging"
        if ! cp -rL "$old_target" "$staging"; then
            rm -rf "$staging" 2>/dev/null || true
            warn "Codex 레거시 이전 복사 실패 — 구 항목을 보존합니다: $old_target"
            continue
        fi
        marker_write "$staging"
        if ! mv "$staging" "$new_target"; then
            rm -rf "$staging" 2>/dev/null || true
            warn "Codex 레거시 이전 교체 실패 — 구 항목을 보존합니다: $old_target"
            continue
        fi
        local source_relative
        source_relative="$(catalog_source skill codex "$skill")"
        if ! manifest_record_required codex-skill "$new_target" copy "$SCRIPT_DIR/$source_relative" "$(content_hash "$new_target")"; then
            warn "Codex 레거시 이전 매니페스트 기록 실패 — 구 항목을 보존합니다: $old_target"
            rm -rf "$new_target" || warn "부분 복사본을 제거하지 못했습니다: $new_target"
            continue
        fi
        if ! rm -rf "$old_target"; then
            warn "새 경로 설치는 완료했지만 구 항목을 제거하지 못했습니다: $old_target"
            continue
        fi
        python3 "$MANIFEST_TOOL" prune --manifest "$MANIFEST_FILE" --target "$old_target" 2>/dev/null || true
        ok "Codex 스킬 이전: $old_target → $new_target"
    done
}

install_codex_skills() {
    section "Codex 스킬 설치 (선택)"

    if ! $USE_CODEX; then
        skip "Codex 미사용 — Codex 스킬 설치 건너뜀"
        return
    fi

    echo
    if ! ask_yn "Codex에도 스킬을 설치하시겠습니까?"; then
        skip "Codex 스킬 설치 건너뜀"
        return
    fi

    migrate_legacy_codex_skills
    mkdir -p "$CODEX_SKILLS_DIR"

    local codex_skills=()
    mapfile -t codex_skills < <(catalog_names skill codex)

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

    local claude_agent_names=()
    local codex_agent_names=()
    mapfile -t claude_agent_names < <(catalog_names agent claude)
    mapfile -t codex_agent_names < <(catalog_names agent codex)
    echo

    # Claude 에이전트 설치
    if ask_yn "Claude 에이전트를 설치하시겠습니까? (~/.claude/agents/)"; then
        [[ -d "$CLAUDE_AGENTS_DIR" ]] || CLAUDE_DIRECTORY_CREATED=true
        mkdir -p "$CLAUDE_AGENTS_DIR"
        for agent in "${claude_agent_names[@]}"; do
            local source_relative
            source_relative="$(catalog_source agent claude "$agent")"
            local src="$SCRIPT_DIR/$source_relative"
            local dst="$CLAUDE_AGENTS_DIR/${agent}.md"

            if [[ -z "$source_relative" || ! -f "$src" ]]; then
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
                    skip "소유권 미확인 에이전트를 보존합니다."
                    continue
                fi
            fi

            if install_staged_component "$src" "$dst" copy claude-agent; then
                ok "${agent} → ${dst} (복사)"
            else
                warn "${agent} 에이전트 복사에 실패했습니다. 기존 항목은 보존했습니다: $dst"
            fi
        done
    else
        skip "Claude 에이전트 건너뜀"
    fi

    # Codex 에이전트 설치
    if $USE_CODEX; then
        echo
        if ask_yn "Codex 에이전트를 설치하시겠습니까? (~/.codex/agents/)"; then
            mkdir -p "$CODEX_AGENTS_DIR"
                for agent in "${codex_agent_names[@]}"; do
                    local source_relative
                    source_relative="$(catalog_source agent codex "$agent")"
                    local src="$SCRIPT_DIR/$source_relative"
                    local dst="$CODEX_AGENTS_DIR/${agent}.toml"

                    if [[ -z "$source_relative" || ! -f "$src" ]]; then
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
                            skip "소유권 미확인 에이전트를 보존합니다."
                            continue
                        fi
                    fi

                    if install_staged_component "$src" "$dst" copy codex-agent; then
                        ok "${agent} → ${dst} (복사)"
                    else
                        warn "${agent} 에이전트 복사에 실패했습니다. 기존 항목은 보존했습니다: $dst"
                    fi
            done
        else
            skip "Codex 에이전트 건너뜀"
        fi
    fi

}

show_dependency_diagnostics() {
    section "외부 도구 진단 (자동 설치 없음)"
    local name command install_hint
    while IFS='|' read -r name command install_hint; do
        if command -v "$command" &>/dev/null; then
            ok "$name 감지됨: $(command -v "$command")"
        else
            warn "$name 없음 — $install_hint"
        fi
    done <<'EOF'
Node.js|node|https://nodejs.org/
PHP|php|배포판 패키지 관리자로 PHP CLI 설치
Codex CLI|codex|npm install -g @openai/codex
Context7 CLI|ctx7|npm install -g ctx7
agent-browser|agent-browser|npm install -g agent-browser
EOF
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

    ask_install_scope
    set_manifest_path
    ask_skill_install_mode
    create_skill_links
    setup_workflow_hook "Claude Code" "$CLAUDE_HOOKS_DIR" "$CLAUDE_SETTINGS_FILE" "claude-hook"
    install_codex_skills
    install_agents
    show_dependency_diagnostics

    echo
    echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${NC}"
    ok "설치 완료!"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo
    if $CLAUDE_DIRECTORY_CREATED; then
        info "Claude skills/agents 디렉터리를 처음 만들었습니다. Claude Code를 한 번 재시작하세요."
    fi
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
