#!/usr/bin/env bash

ENV_FILE=".env.local"

if [ ! -f "$ENV_FILE" ]; then
    echo "오류: $ENV_FILE 파일을 찾을 수 없습니다."
    exit 1
fi

# .env.local 로드
export $(grep -v '^#' "$ENV_FILE" | xargs)

if [ -z "$TEST_DB" ] || [ -z "$LOCAL_DB" ]; then
    echo "오류: $ENV_FILE 파일에 TEST_DB 또는 LOCAL_DB 설정이 누락되었습니다."
    exit 1
fi

echo "작업선택"
echo "    1. 조회"
echo "    2. 복사"
echo "    q. 종료"
read -rp "    선택> " ACTION_CHOICE

case "$ACTION_CHOICE" in
    q|Q)
        echo "스크립트를 종료합니다."
        exit 0
        ;;

    1)
        # ==================== 1. 조회 ====================
        echo ""
        echo "대상DB"
        echo "    1. TEST_DB"
        echo "    2. LOCAL_DB"
        read -rp "    > 선택: " DB_CHOICE

        case "$DB_CHOICE" in
            1) TARGET_DB="$TEST_DB" ;;
            2) TARGET_DB="$LOCAL_DB" ;;
            *) echo "잘못된 선택입니다."; exit 1 ;;
        esac

        echo ""
        echo "OBJECT"
        echo "    1. 테이블 스키마"
        echo "    2. 테이블 데이터(10)"
        echo "    3. 시퀜스"
        echo "    4. 함수"
        echo "    5. 프로시져"
        read -rp "    > 선택: " OBJ_CHOICE

        echo ""
        read -rp "NAME : " OBJ_NAME

        if [ -z "$OBJ_NAME" ]; then
            echo "오류: 이름을 입력해야 합니다."
            exit 1
        fi

        echo ""
        echo "----------------- [조회 결과] -----------------"
        case "$OBJ_CHOICE" in
            1)
                # 테이블 스키마
                psql "$TARGET_DB" -c "\d+ $OBJ_NAME"
                ;;
            2)
                # 데이터 상위 10건
                psql "$TARGET_DB" -c "SELECT * FROM $OBJ_NAME LIMIT 10;"
                ;;
            3)
                # 시퀀스 상세 정보
                psql "$TARGET_DB" -c "\d+ $OBJ_NAME"
                ;;
            4)
                # 함수 소스코드
                psql "$TARGET_DB" -c "\df+ $OBJ_NAME"
                psql "$TARGET_DB" -c "SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = '$OBJ_NAME' AND prokind = 'f';"
                ;;
            5)
                # 프로시저 소스코드
                psql "$TARGET_DB" -c "\df+ $OBJ_NAME"
                psql "$TARGET_DB" -c "SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = '$OBJ_NAME' AND prokind = 'p';"
                ;;
            *)
                echo "잘못된 OBJECT 선택입니다."
                exit 1
                ;;
        esac
        ;;

    2)
        # ==================== 2. 복사 (TEST_DB -> LOCAL_DB) ====================
        echo ""
        echo "OBJECT"
        echo "    1. 테이블 스키마"
        echo "    2. 테이블 데이터(10)"
        echo "    3. 시퀜스"
        echo "    4. 함수"
        echo "    5. 프로시져"
        read -rp "    > 선택: " OBJ_CHOICE

        echo ""
        read -rp "NAME : " OBJ_NAME

        if [ -z "$OBJ_NAME" ]; then
            echo "오류: 이름을 입력해야 합니다."
            exit 1
        fi

        echo ""
        echo "[$OBJ_NAME] 복사 진행 중 (TEST_DB -> LOCAL_DB)..."

        case "$OBJ_CHOICE" in
            1)
                # 테이블 스키마 복사 (데이터 제외)
                pg_dump "$TEST_DB" --schema-only --table="$OBJ_NAME" --no-owner --no-privileges | psql "$LOCAL_DB"
                echo "-> 검증: 로컬 테이블 확인"
                psql "$LOCAL_DB" -c "\d $OBJ_NAME"
                ;;
            2)
                # 테이블 데이터 10건 복사
                psql "$TEST_DB" -c "\copy (SELECT * FROM $OBJ_NAME LIMIT 10) TO STDOUT WITH BINARY" \
                | psql "$LOCAL_DB" -c "\copy $OBJ_NAME FROM STDIN WITH BINARY"
                echo "-> 검증: 로컬 데이터 건수"
                psql "$LOCAL_DB" -c "SELECT COUNT(*) FROM $OBJ_NAME;"
                ;;
            3)
                # 시퀀스 정의 및 현재값 복사
                pg_dump "$TEST_DB" --table="$OBJ_NAME" --no-owner --no-privileges | psql "$LOCAL_DB"
                echo "-> 검증: 로컬 시퀀스 확인"
                psql "$LOCAL_DB" -c "\d $OBJ_NAME"
                ;;
            4|5)
                # 함수 / 프로시저 정의 추출 후 로컬 적재
                DEF_SQL=$(psql "$TEST_DB" -t -A -c "SELECT pg_get_functiondef(oid) || ';' FROM pg_proc WHERE proname = '$OBJ_NAME';")
                if [ -n "$DEF_SQL" ]; then
                    echo "$DEF_SQL" | psql "$LOCAL_DB"
                    echo "-> 검증: 로컬 함수/프로시저 확인"
                    psql "$LOCAL_DB" -c "\df $OBJ_NAME"
                else
                    echo "오류: 원격 DB에서 해당 함수/프로시저 정의를 찾지 못했습니다."
                fi
                ;;
            *)
                echo "잘못된 OBJECT 선택입니다."
                exit 1
                ;;
        esac
        ;;

    *)
        echo "잘못된 작업 선택입니다."
        exit 1
        ;;
esac

echo ""
echo "작업이 완료되어 스크립트를 종료합니다."
exit 0