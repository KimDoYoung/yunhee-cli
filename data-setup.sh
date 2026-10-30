#!/usr/bin/env bash
# ==============================================================================
# yunhee 데이터 및 색인 관리 스크립트 (data-setup.sh)
#
# AssetERP 레거시 프레임워크(GWT/GXT)를 신규 프레임워크(Spring Boot/React)로
# 전환·분석하기 위해 필요한 DB 스키마 스냅샷, 도메인별 DBML 색인,
# AS-IS 소스/UI 호출경로 색인을 준비·삭제·재구축합니다.
#
# ★ 중요 원칙:
#   - 동작 대상(.yunhee 및 docs/as-is)은 반드시 "현재 working 폴더(pwd)"입니다.
#   - 작업 디렉터리에 .yunhee 가 없으면 /init을 안내하거나 자동 생성합니다.
# ==============================================================================

set -eo pipefail

# ANSI 색상 코드
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# 스크립트 위치 및 현재 working 디렉터리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$(pwd)"
YUNHEE_DOT_DIR="${TARGET_DIR}/.yunhee"
DOCS_AS_IS="${TARGET_DIR}/docs/as-is"

# CLI 실행 명령어 판별
if command -v uv >/dev/null 2>&1; then
    RUN_CMD="uv run"
    YUNHEE_CMD="uv run yunhee"
elif command -v yunhee >/dev/null 2>&1; then
    RUN_CMD=""
    YUNHEE_CMD="yunhee"
else
    echo -e "${RED}[ERROR] uv 또는 yunhee 명령어를 찾을 수 없습니다.${NC}"
    exit 1
fi

# 설정값 단일 조회 헬퍼
get_config_val() {
    local key="$1"
    local val
    val=$($YUNHEE_CMD value "$key" 2>/dev/null || true)
    echo "$val"
}

# 기본 경로 및 환경변수 로드
load_env_vars() {
    ASIS_SRC_DIR="$(get_config_val YUNHEE_ASIS_SRC_DIR)"
    TOBE_SRC_DIR="$(get_config_val YUNHEE_TOBE_SRC_DIR)"
    SCHEMA_ENV="$(get_config_val YUNHEE_SCHEMA_ENV)"
    [ -z "$SCHEMA_ENV" ] && SCHEMA_ENV="LOCAL_DB"

    DB_DSN="$(get_config_val "$SCHEMA_ENV")"
    if [ -z "$DB_DSN" ]; then
        if [ "$SCHEMA_ENV" = "YUNHEE_DB" ]; then
            DB_DSN="$(get_config_val LOCAL_DB)"
        elif [ "$SCHEMA_ENV" = "LOCAL_DB" ]; then
            DB_DSN="$(get_config_val YUNHEE_DB)"
        fi
    fi
}

# 현재 working 폴더의 .yunhee 디렉터리 존재 여부 검사 및 init 안내
ensure_yunhee_project() {
    if [ ! -d "$YUNHEE_DOT_DIR" ] || [ ! -f "${YUNHEE_DOT_DIR}/project.json" ]; then
        echo -e "\n${YELLOW}${BOLD}[!] 현재 working 폴더(${TARGET_DIR})에 .yunhee 프로젝트 설정이 없습니다.${NC}"
        read -rp "  'yunhee init'을 실행하여 현재 폴더를 yunhee 프로젝트로 초기화하시겠습니까? (Y/n): " ans
        if [[ "$ans" =~ ^[Nn]$ ]]; then
            echo -e "${RED}[ERROR] .yunhee 프로젝트가 초기화되지 않아 작업을 계속할 수 없습니다.${NC}"
            return 1
        fi
        echo -e "${CYAN}>> 현재 폴더에서 yunhee init 실행 중...${NC}"
        $YUNHEE_CMD init
        echo -e "${GREEN}✅ .yunhee 프로젝트 디렉터리가 생성되었습니다: ${YUNHEE_DOT_DIR}${NC}\n"
    fi
    return 0
}

# ------------------------------------------------------------------------------
# 1. 현재 상태 출력
# ------------------------------------------------------------------------------
show_status() {
    load_env_vars
    echo ""
    echo -e "${BOLD}${CYAN}======================================================================${NC}"
    echo -e "${BOLD}${CYAN} 📊 [yunhee] 데이터 및 색인 현황 요약 (Working Dir 기준)${NC}"
    echo -e "${BOLD}${CYAN}======================================================================${NC}"
    
    echo -e "\n${BOLD}[1] 위치 및 환경 설정${NC}"
    echo -e "  - 현재 작업 폴더 (Working Dir) : ${BLUE}${TARGET_DIR}${NC}"
    if [ -d "$YUNHEE_DOT_DIR" ] && [ -f "${YUNHEE_DOT_DIR}/project.json" ]; then
        echo -e "  - 프로젝트 .yunhee 위치        : ${GREEN}${YUNHEE_DOT_DIR} [초기화됨]${NC}"
    else
        echo -e "  - 프로젝트 .yunhee 위치        : ${RED}${YUNHEE_DOT_DIR} [미초기화: yunhee init 필요]${NC}"
    fi
    echo -e "  - yunhee 전역 설치 홈 (Home)   : ${BLUE}${SCRIPT_DIR}${NC}"
    
    if [ -n "$ASIS_SRC_DIR" ] && [ -d "$ASIS_SRC_DIR" ]; then
        echo -e "  - AS-IS 소스 디렉터리          : ${GREEN}${ASIS_SRC_DIR} [정상]${NC}"
    else
        echo -e "  - AS-IS 소스 디렉터리          : ${RED}${ASIS_SRC_DIR:-미설정} [경로 없음]${NC}"
    fi

    if [ -n "$TOBE_SRC_DIR" ] && [ -d "$TOBE_SRC_DIR" ]; then
        echo -e "  - TOBE 소스 디렉터리          : ${GREEN}${TOBE_SRC_DIR} [정상]${NC}"
    else
        echo -e "  - TOBE 소스 디렉터리          : ${YELLOW}${TOBE_SRC_DIR:-미설정} [Working Dir fallback]${NC}"
    fi

    if [ -n "$DB_DSN" ]; then
        echo -e "  - DB 접속 URL (${SCHEMA_ENV})       : ${GREEN}설정됨 [정상]${NC}"
    else
        echo -e "  - DB 접속 URL (${SCHEMA_ENV})       : ${RED}미설정 (.env.local 확인 필요)${NC}"
    fi

    echo -e "\n${BOLD}[2] DB 관련 조사 자료 (현재 working 프로젝트)${NC}"
    # 2-1. 스키마 JSON 스냅샷 (.yunhee/ 우선 탐색)
    local snapshot_json=""
    if [ -f "${YUNHEE_DOT_DIR}/${SCHEMA_ENV}.json" ]; then
        snapshot_json="${YUNHEE_DOT_DIR}/${SCHEMA_ENV}.json"
    elif [ -f "${YUNHEE_DOT_DIR}/LOCAL_DB.json" ]; then
        snapshot_json="${YUNHEE_DOT_DIR}/LOCAL_DB.json"
    elif [ -f "${YUNHEE_DOT_DIR}/YUNHEE_DB.json" ]; then
        snapshot_json="${YUNHEE_DOT_DIR}/YUNHEE_DB.json"
    elif [ -f "${SCRIPT_DIR}/data/schema/${SCHEMA_ENV}.json" ]; then
        snapshot_json="${SCRIPT_DIR}/data/schema/${SCHEMA_ENV}.json (전역)"
    fi

    if [ -n "$snapshot_json" ]; then
        local real_file="${snapshot_json% (전역)}"
        local sz
        sz=$(du -h "$real_file" 2>/dev/null | cut -f1 || echo "")
        local dt
        dt=$(date -r "$real_file" "+%Y-%m-%d %H:%M" 2>/dev/null || stat -c %y "$real_file" 2>/dev/null | cut -d'.' -f1 || echo "")
        echo -e "  - 스키마 JSON 스냅샷            : ${GREEN}[O] $(basename "$real_file") (${sz}, ${dt})${NC}"
        if [[ "$snapshot_json" == *" (전역)"* ]]; then
            echo -e "      * 출처: 전역 캐시 (${real_file})"
        else
            echo -e "      * 출처: 로컬 .yunhee (${real_file})"
        fi
    else
        echo -e "  - 스키마 JSON 스냅샷            : ${RED}[X] 없음 (yunhee make-dbml 필요)${NC}"
    fi

    # 2-2. DBML 마크다운 (.yunhee/ 우선 탐색)
    local dbml_files=()
    while IFS= read -r f; do
        [ -n "$f" ] && dbml_files+=("$f")
    done < <(find "${YUNHEE_DOT_DIR}" "${TARGET_DIR}" -maxdepth 1 -name "*-dbml.md" 2>/dev/null || true)

    if [ ${#dbml_files[@]} -gt 0 ]; then
        echo -e "  - DBML 마크다운 파일            : ${GREEN}[O] ${#dbml_files[@]}개 발견${NC}"
        for df in "${dbml_files[@]}"; do
            local lcnt
            lcnt=$(wc -l < "$df" 2>/dev/null || echo 0)
            echo -e "      * ${df#${TARGET_DIR}/} (${lcnt} 줄)"
        done
    else
        echo -e "  - DBML 마크다운 파일            : ${RED}[X] 없음${NC}"
    fi

    # 2-3. DB 분할 색인 (docs/as-is/db)
    local db_idx_dir="${DOCS_AS_IS}/db"
    if [ -d "$db_idx_dir" ]; then
        local tbl_cnt
        tbl_cnt=$(find "${db_idx_dir}/tables" -name "*.md" 2>/dev/null | wc -l)
        local fn_cnt
        fn_cnt=$(find "${db_idx_dir}/functions" -name "*.md" 2>/dev/null | wc -l)
        local has_views="[X]"
        local has_trigs="[X]"
        [ -f "${db_idx_dir}/views.md" ] && has_views="[O]"
        [ -f "${db_idx_dir}/triggers.md" ] && has_trigs="[O]"
        echo -e "  - DB 분할 색인 (docs/as-is/db)   : ${GREEN}[O] 정상 색인됨${NC}"
        echo -e "      * 도메인별 테이블 파일 : ${tbl_cnt}개"
        echo -e "      * 함수/프로시저 파일   : ${fn_cnt}개"
        echo -e "      * views.md: ${has_views} | triggers.md: ${has_trigs}"
    else
        echo -e "  - DB 분할 색인 (docs/as-is/db)   : ${RED}[X] 없음 (yunhee index-db 필요)${NC}"
    fi

    echo -e "\n${BOLD}[3] SRC 관련 조사 자료 (현재 working 프로젝트)${NC}"
    # 3-1. 메뉴 TSV
    local menus_tsv="${DOCS_AS_IS}/menus.tsv"
    if [ -f "$menus_tsv" ]; then
        local m_lines
        m_lines=$(wc -l < "$menus_tsv" 2>/dev/null || echo 0)
        echo -e "  - 메뉴 목록 (menus.tsv)         : ${GREEN}[O] ${m_lines}개 메뉴 정의됨 (${menus_tsv#${TARGET_DIR}/})${NC}"
    else
        echo -e "  - 메뉴 목록 (menus.tsv)         : ${RED}[X] 없음 (index-src 시 자동생성 권장)${NC}"
    fi

    # 3-2. 화면 및 소스 호출경로 색인 (docs/as-is/src)
    local src_idx_dir="${DOCS_AS_IS}/src"
    if [ -d "$src_idx_dir" ]; then
        local domain_cnt
        domain_cnt=$(find "$src_idx_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
        local screen_cnt
        screen_cnt=$(find "$src_idx_dir" -name "*.md" ! -name "README.md" ! -name "menus.md" ! -name "unresolved.md" 2>/dev/null | wc -l)
        echo -e "  - 화면/소스 색인 (docs/as-is/src): ${GREEN}[O] ${domain_cnt}개 도메인, ${screen_cnt}개 화면 색인됨${NC}"
    else
        echo -e "  - 화면/소스 색인 (docs/as-is/src): ${RED}[X] 없음 (yunhee index-src 필요)${NC}"
    fi

    # 3-3. SQLite mapper_index
    local db_file="${SCRIPT_DIR}/data/db/yunhee.db"
    if [ -f "$db_file" ]; then
        local mapper_cnt=0
        if command -v sqlite3 >/dev/null 2>&1; then
            mapper_cnt=$(sqlite3 "$db_file" "SELECT count(*) FROM mapper_index;" 2>/dev/null || echo 0)
        fi
        if [ "$mapper_cnt" -gt 0 ]; then
            echo -e "  - SQLite 매퍼 인덱스            : ${GREEN}[O] ${mapper_cnt}개 SQL statement 캐시됨${NC}"
        else
            echo -e "  - SQLite 매퍼 인덱스            : ${YELLOW}[!] 캐시 테이블 비어있음 (tools/parse_mapper.py 필요)${NC}"
        fi
    else
        echo -e "  - SQLite 매퍼 인덱스            : ${RED}[X] yunhee.db 없음${NC}"
    fi

    echo -e "${BOLD}${CYAN}======================================================================${NC}\n"
}

# ------------------------------------------------------------------------------
# 2. DB 관련 조사 자료 삭제 (현재 working 디렉터리 기준)
# ------------------------------------------------------------------------------
delete_db_data() {
    local silent="${1:-false}"
    load_env_vars

    if [ "$silent" != "true" ]; then
        echo -e "\n${YELLOW}현재 working 폴더(${TARGET_DIR})의 DB 관련 자료들이 삭제됩니다:${NC}"
        echo -e "  - ${YUNHEE_DOT_DIR}/*-dbml.md"
        echo -e "  - ${YUNHEE_DOT_DIR}/${SCHEMA_ENV}.json (로컬 스키마 스냅샷)"
        echo -e "  - ${TARGET_DIR}/*-dbml.md"
        echo -e "  - ${DOCS_AS_IS}/db"
        read -rp "정말 삭제하시겠습니까? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo -e "${CYAN}삭제가 취소되었습니다.${NC}"
            return 0
        fi
    fi

    echo -e "${YELLOW}>> 현재 working 폴더의 DB 관련 자료 삭제 중...${NC}"
    rm -f "${YUNHEE_DOT_DIR}"/*-dbml.md 2>/dev/null || true
    rm -f "${YUNHEE_DOT_DIR}"/LOCAL_DB.json 2>/dev/null || true
    rm -f "${YUNHEE_DOT_DIR}"/YUNHEE_DB.json 2>/dev/null || true
    rm -f "${YUNHEE_DOT_DIR}/${SCHEMA_ENV}.json" 2>/dev/null || true
    rm -f "${TARGET_DIR}"/*-dbml.md 2>/dev/null || true
    rm -rf "${DOCS_AS_IS}/db" 2>/dev/null || true

    echo -e "${GREEN}✅ 현재 working 폴더의 DB 관련 자료가 삭제되었습니다.${NC}"
}

# ------------------------------------------------------------------------------
# 3. SRC 관련 조사 자료 삭제 (현재 working 디렉터리 기준)
# ------------------------------------------------------------------------------
delete_src_data() {
    local silent="${1:-false}"
    load_env_vars

    if [ "$silent" != "true" ]; then
        echo -e "\n${YELLOW}현재 working 폴더(${TARGET_DIR})의 SRC 관련 자료들이 삭제됩니다:${NC}"
        echo -e "  - ${DOCS_AS_IS}/menus.tsv"
        echo -e "  - ${DOCS_AS_IS}/src (화면 및 호출경로 색인 마크다운 전체)"
        read -rp "정말 삭제하시겠습니까? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo -e "${CYAN}삭제가 취소되었습니다.${NC}"
            return 0
        fi
    fi

    echo -e "${YELLOW}>> 현재 working 폴더의 SRC 관련 자료 삭제 중...${NC}"
    rm -f "${DOCS_AS_IS}/menus.tsv" 2>/dev/null || true
    rm -rf "${DOCS_AS_IS}/src" 2>/dev/null || true

    echo -e "${GREEN}✅ 현재 working 폴더의 SRC 관련 자료가 삭제되었습니다.${NC}"
}

# ------------------------------------------------------------------------------
# 4. DB 관련 자료 준비 (.yunhee 및 docs/as-is/db 에 생성)
# ------------------------------------------------------------------------------
prepare_db_data() {
    load_env_vars
    ensure_yunhee_project || return 1

    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${BLUE} 🚀 DB 관련 자료 준비 시작 (Working Dir: ${TARGET_DIR})${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}"

    if [ -z "$DB_DSN" ]; then
        echo -e "${RED}[ERROR] DB 접속 환경변수(${SCHEMA_ENV} 또는 LOCAL_DB)가 설정되지 않았습니다.${NC}"
        echo -e "  .env.local 또는 ~/.yunhee/.env.yunhee에 PostgreSQL 접속 URL을 등록하세요."
        return 1
    fi

    local target_dbml="${YUNHEE_DOT_DIR}/${SCHEMA_ENV}-dbml.md"
    echo -e "\n${CYAN}>> [1/2] DB 카탈로그 스키마 스냅샷 및 DBML 추출...${NC}"
    echo -e "  - 저장 위치: ${target_dbml}"
    $YUNHEE_CMD make-dbml "$SCHEMA_ENV" -o "$target_dbml"

    echo -e "\n${CYAN}>> [2/2] DBML을 도메인·함수별 소형 파일로 분할 색인 (index-db)...${NC}"
    echo -e "  - 대상 DBML: ${target_dbml}"
    echo -e "  - 출력 위치: ${DOCS_AS_IS}/db"
    $YUNHEE_CMD index-db "$target_dbml" -t "${DOCS_AS_IS}/db"

    echo -e "\n${GREEN}✅ DB 관련 자료 준비가 성공적으로 완료되었습니다!${NC}"
}

# ------------------------------------------------------------------------------
# 5. SRC 관련 자료 준비 (docs/as-is/ 에 생성)
# ------------------------------------------------------------------------------
prepare_src_data() {
    load_env_vars
    ensure_yunhee_project || return 1

    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${BLUE} 🚀 SRC 관련 자료 준비 시작 (Working Dir: ${TARGET_DIR})${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}"

    if [ -z "$ASIS_SRC_DIR" ] || [ ! -d "$ASIS_SRC_DIR" ]; then
        echo -e "${RED}[ERROR] AS-IS 소스 디렉터리를 찾을 수 없습니다: ${ASIS_SRC_DIR:-미설정}${NC}"
        echo -e "  .env.local 또는 ~/.yunhee/.env.yunhee의 YUNHEE_ASIS_SRC_DIR 설정을 확인하세요."
        return 1
    fi

    echo -e "\n${CYAN}>> [1/2] AS-IS 소스 호출경로 및 UI/이벤트 색인 생성 (index-src)...${NC}"
    echo -e "  - 메뉴 TSV: ${DOCS_AS_IS}/menus.tsv"
    echo -e "  - 출력 위치: ${DOCS_AS_IS}/src"
    
    mkdir -p "${DOCS_AS_IS}"
    if [ -n "$DB_DSN" ]; then
        echo -e "  (DB의 sys06_menu에서 menus.tsv를 자동 갱신하며 색인합니다)"
        $YUNHEE_CMD index-src -t "${DOCS_AS_IS}/src" --menus "${DOCS_AS_IS}/menus.tsv" --menus-from-db "$SCHEMA_ENV" --db-index "${DOCS_AS_IS}/db"
    else
        echo -e "  (DB 미접속 상태: 기존 menus.tsv가 있으면 활용하여 색인합니다)"
        $YUNHEE_CMD index-src -t "${DOCS_AS_IS}/src" --menus "${DOCS_AS_IS}/menus.tsv" --db-index "${DOCS_AS_IS}/db"
    fi

    echo -e "\n${CYAN}>> [2/2] AS-IS MyBatis 매퍼 XML SQLite 인덱스 빌드 (parse_mapper.py)...${NC}"
    (cd "$SCRIPT_DIR" && $RUN_CMD tools/parse_mapper.py)

    echo -e "\n${GREEN}✅ SRC 관련 자료 준비가 성공적으로 완료되었습니다!${NC}"
}

# ------------------------------------------------------------------------------
# 6. 모든 자료들 삭제 (현재 working 디렉터리 기준)
# ------------------------------------------------------------------------------
delete_all_data() {
    load_env_vars
    echo -e "\n${YELLOW}${BOLD}⚠ 경고: 현재 working 폴더(${TARGET_DIR})의 DB 및 SRC 관련 조사 자료가 삭제됩니다.${NC}"
    read -rp "정말 모두 삭제하시겠습니까? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${CYAN}삭제가 취소되었습니다.${NC}"
        return 0
    fi

    delete_db_data "true"
    delete_src_data "true"

    if [ -d "$DOCS_AS_IS" ] && [ -z "$(ls -A "$DOCS_AS_IS" 2>/dev/null)" ]; then
        rm -rf "$DOCS_AS_IS" 2>/dev/null || true
    fi

    echo -e "\n${GREEN}✅ 현재 working 폴더의 모든 조사 자료가 완전히 삭제되었습니다.${NC}"
}

# ------------------------------------------------------------------------------
# 7. 모든 자료들 재 설치
# ------------------------------------------------------------------------------
reinstall_all_data() {
    load_env_vars
    ensure_yunhee_project || return 1

    echo -e "\n${YELLOW}${BOLD}현재 working 폴더(${TARGET_DIR})의 기존 자료를 모두 삭제한 후, DB 및 SRC 관련 자료를 완전 재구축합니다.${NC}"
    read -rp "계속 진행하시겠습니까? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${CYAN}재설치가 취소되었습니다.${NC}"
        return 0
    fi

    delete_db_data "true"
    delete_src_data "true"

    prepare_db_data
    prepare_src_data

    echo -e "\n${GREEN}${BOLD}🎉 모든 자료의 재설치가 완료되었습니다! 최신 현황을 출력합니다.${NC}"
    show_status
}

# ------------------------------------------------------------------------------
# 99. 도움말
# ------------------------------------------------------------------------------
show_help() {
    cat << 'EOF'

======================================================================
 📖 yunhee 자료 준비 도구 도움말 (data-setup.sh)
======================================================================

1. 동작 위치 및 격리 원칙
   - 이 스크립트가 조작하는 모든 산출물(.yunhee 및 docs/as-is)은
     스크립트를 실행한 "현재 working 폴더(pwd)"를 기준으로 격리됩니다.
   - 새 프로젝트(예: project1)를 만든 후 해당 디렉터리에서
     `data-setup.sh`를 실행하면 해당 폴더 내의 .yunhee/ 와 docs/as-is/ 에만
     자료가 생성/삭제되므로 다른 프로젝트에 영향을 주지 않습니다.

2. 각 자료의 역할과 생성 도구
   [DB 관련 자료]
   - make-dbml   : PostgreSQL 카탈로그 메타데이터를 추출하여 JSON 스냅샷과
                   DBML 마크다운을 로컬 `.yunhee/`에 저장합니다.
   - index-db    : 대용량 DBML을 도메인별 소형 파일(docs/as-is/db/tables/*.md)과
                   저장 프로시저(functions/*.md)로 분할 색인합니다.
   
   [SRC 관련 자료]
   - index-src   : GXT 화면의 UI/이벤트(E0~En)/그리드 스펙부터 RPC 서비스,
                   MyBatis XML, 대상 테이블까지의 호출 사슬을 `docs/as-is/src/`에 정적 색인합니다.
   - parse_mapper: 수백 개 MyBatis 매퍼를 파싱하여 SQLite 캐시(mapper_index)를 구축합니다.

3. 메뉴 가이드
   [1] 현재 상태       : 필수 환경설정 및 생성된 파일들의 현황 요약
   [2] DB 자료 삭제    : .yunhee/*-dbml.md, .yunhee/*.json, docs/as-is/db 제거
   [3] SRC 자료 삭제   : docs/as-is/menus.tsv, docs/as-is/src 폴더 제거
   [4] DB 자료 준비    : .yunhee 아래 make-dbml 및 docs/as-is/db 에 index-db 생성
   [5] SRC 자료 준비   : docs/as-is 아래 index-src 및 parse_mapper.py 실행
   [6] 모든 자료 삭제  : [2]와 [3]을 동시에 수행하여 완전 초기화
   [7] 모든 자료 재설치: 모든 자료를 깨끗이 삭제 후 [4]와 [5]를 순차 실행
   [0] 종료           : 스크립트 종료

======================================================================

EOF
}

# ------------------------------------------------------------------------------
# 대화형 메뉴 루프
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        echo -e "${BOLD}${MAGENTA}┌────────────────────────────────────────────────────────┐${NC}"
        echo -e "${BOLD}${MAGENTA}│        🛠️  yunhee 데이터 및 색인 관리 도구           │${NC}"
        echo -e "${BOLD}${MAGENTA}└────────────────────────────────────────────────────────┘${NC}"
        echo -e "  - 작업 대상(Working Dir): ${BLUE}${TARGET_DIR}${NC}"
        echo -e "  - 프로젝트 .yunhee 위치 : ${BLUE}${YUNHEE_DOT_DIR}${NC}"
        echo -e " --------------------------------------------------------"
        echo -e "  ${BOLD}1.${NC} 현재 상태"
        echo -e "  ${BOLD}2.${NC} db 관련 조사된 자료들을 삭제"
        echo -e "  ${BOLD}3.${NC} src 관련 조사된 자료들 삭제"
        echo -e "  ${BOLD}4.${NC} db 관련 자료들 준비"
        echo -e "  ${BOLD}5.${NC} src 관련 자료들 준비"
        echo -e "  ${BOLD}6.${NC} 모든 자료들 삭제"
        echo -e "  ${BOLD}7.${NC} 모든 자료들 재 설치"
        echo -e " --------------------------------------------------------"
        echo -e " ${BOLD}99.${NC} 도움말"
        echo -e "  ${BOLD}0.${NC} 종료"
        echo ""
        read -rp "선택 (0-7, 99): " choice

        case "$choice" in
            1) show_status ;;
            2) delete_db_data ;;
            3) delete_src_data ;;
            4) prepare_db_data ;;
            5) prepare_src_data ;;
            6) delete_all_data ;;
            7) reinstall_all_data ;;
            99) show_help ;;
            0) echo -e "${CYAN}종료합니다.${NC}"; exit 0 ;;
            *) echo -e "${RED}잘못된 입력입니다. 0~7 또는 99를 선택하세요.${NC}" ;;
        esac

        echo ""
        read -rp "엔터를 누르면 메뉴로 돌아갑니다..." _dummy
        echo ""
    done
}

# 인자가 주어진 경우 비대화형 실행 지원
if [ $# -gt 0 ]; then
    case "$1" in
        status|1) show_status ;;
        clean-db|2) delete_db_data "true" ;;
        clean-src|3) delete_src_data "true" ;;
        prepare-db|4) prepare_db_data ;;
        prepare-src|5) prepare_src_data ;;
        clean-all|6) delete_all_data ;;
        reinstall|7) reinstall_all_data ;;
        help|99) show_help ;;
        *) echo "사용법: $0 [status|clean-db|clean-src|prepare-db|prepare-src|clean-all|reinstall|help]" ; exit 1 ;;
    esac
else
    main_menu
fi
