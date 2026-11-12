"""로컬 DB 안전 쓰기 도구 (`biz-db-write`).

localhost DB에 한하여 안전 가드(WHERE 필수, DDL 차단, 원격 차단)와
자동 백업, 원자적 트랜잭션(하나라도 실패 시 전체 롤백)을 거쳐 SQL을 실행한다.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from yunhee.tools.sql_runner import get_connection_string

_DDL_PATTERN = re.compile(r"^\s*(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b", re.IGNORECASE)
_MUTATION_PATTERN = re.compile(r"^\s*(DELETE\s+FROM|UPDATE)\b", re.IGNORECASE)


def check_db_write_allowed(db_url: str) -> bool:
    """DB 쓰기가 안전하게 허용된 환경인지 검증한다."""
    if os.getenv("YUNHEE_DB_WRITE") != "1":
        raise ValueError("오류: DB 쓰기가 비활성화되어 있습니다. YUNHEE_DB_WRITE=1 환경변수를 설정하세요.")

    parsed = urlparse(db_url)
    host = parsed.hostname or "localhost"

    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    extra_hosts = os.getenv("YUNHEE_DB_WRITE_HOSTS", "")
    if extra_hosts:
        allowed_hosts.update(h.strip() for h in extra_hosts.split(",") if h.strip())

    if host not in allowed_hosts:
        raise ValueError(f"오류: 원격 DB 쓰기는 허용되지 않습니다 ({host}). 로컬 환경에서만 실행 가능합니다.")

    dbname = parsed.path.lstrip("/")
    allowed_dbs = {db.strip() for db in os.getenv("YUNHEE_DB_WRITE_ALLOW", "asseterpdb").split(",") if db.strip()}

    if dbname not in allowed_dbs:
        raise ValueError(f"오류: 허용되지 않은 DB 대상입니다 ({dbname}). 허용 목록: {', '.join(allowed_dbs)}")

    return True


def guard_write_statement(stmt: str, allow_ddl: bool = False) -> None:
    """단일 SQL 문장이 안전 규칙을 만족하는지 검사한다."""
    clean = stmt.strip()
    if not clean:
        return

    # 1. DDL 검사
    if _DDL_PATTERN.match(clean) and not allow_ddl:
        raise ValueError(f"오류: DDL 문장은 --allow-ddl 옵션이 필요합니다: {clean[:40]}")

    # 2. WHERE 없는 전체 DELETE / UPDATE 검사
    if (
        _MUTATION_PATTERN.match(clean)
        and not re.search(r"\bWHERE\b", clean, re.IGNORECASE)
        and not allow_ddl
    ):
        raise ValueError(f"오류: WHERE 절이 없는 전체 DELETE/UPDATE는 허용되지 않습니다: {clean[:40]}")


def _split_statements(sql_text: str) -> list[str]:
    """SQL 스크립트를 세미콜론 기준으로 문장별로 분리한다."""
    # 주석 제거 (-- 및 /* */)
    no_line_comments = re.sub(r"--[^\n]*", "", sql_text)
    no_block_comments = re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)

    raw_stmts = no_block_comments.split(";")
    stmts: list[str] = []
    for s in raw_stmts:
        c = s.strip()
        if c:
            stmts.append(c)
    return stmts


def run_backup(db_url: str) -> str:
    """DB 백업을 실행하고 백업 파일 경로를 반환한다."""
    parsed = urlparse(db_url)
    dbname = parsed.path.lstrip("/") or "asseterpdb"

    # 1. 프로젝트 내 db_dump_backup.sh 확인
    sh_path = Path.cwd() / "tools" / "db_dump_backup.sh"
    if not sh_path.is_file():
        # 상위 디렉터리 확인
        sh_path = Path.cwd().parent / "tools" / "db_dump_backup.sh"

    backup_cmd = os.getenv("YUNHEE_DB_BACKUP_CMD")

    if sh_path.is_file() and not backup_cmd:
        res = subprocess.run(["bash", str(sh_path)], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise ValueError(f"백업 스크립트 실행 실패: {res.stderr.strip() or res.stdout.strip()}")
        # 백업 출력에서 경로 추출
        m = re.search(r"→\s*([^\n]+\.dump)", res.stdout)
        return m.group(1).strip() if m else "tools/db_dump_backup.sh 실행 완료"

    if backup_cmd:
        res = subprocess.run(backup_cmd, shell=True, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise ValueError(f"백업 명령 실행 실패: {res.stderr.strip() or res.stdout.strip()}")
        return backup_cmd

    # 2. fallback pg_dump -Fc
    cache_dir = Path.home() / ".cache" / "yunhee" / "backup"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
    dump_file = cache_dir / f"{dbname}-{ts}.dump"

    cmd = ["pg_dump", "-Fc", "-d", db_url, "-f", str(dump_file)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise ValueError(f"pg_dump 백업 실패: {res.stderr.strip()}")
    return str(dump_file)


def _log_write_history(summary_line: str) -> None:
    """~/.cache/yunhee/db-write.log 에 실행 이력을 남긴다."""
    try:
        log_dir = Path.home() / ".cache" / "yunhee"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "db-write.log"
        ts = datetime.datetime.now(tz=datetime.UTC).isoformat()
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"{ts} | {summary_line}\n")
    except Exception:  # noqa: BLE001, S110
        pass


def execute_db_write(
    sql_text: str | None = None,
    file_path: Path | str | None = None,
    db_name: str | None = None,
    dry_run: bool = False,
    no_backup: bool = False,
    allow_ddl: bool = False,
) -> tuple[list[str], str | None]:
    """로컬 DB에 SQL 문장들을 안전하게 실행하고 트랜잭션 커밋 또는 롤백한다."""
    import psycopg

    db_url = get_connection_string(db_name)
    if not db_url:
        raise ValueError("DB 연결 정보를 찾을 수 없습니다 (YUNHEE_DB).")

    # 1. 안전 환경 검사
    check_db_write_allowed(db_url)

    # 2. SQL 문장 준비
    raw_content = ""
    target_desc = ""
    if file_path:
        p = Path(file_path)
        if not p.is_file():
            raise ValueError(f"SQL 파일을 찾을 수 없습니다: {file_path}")
        raw_content = p.read_text(encoding="utf-8", errors="replace")
        target_desc = f"file:{p.name}"
    elif sql_text:
        raw_content = sql_text
        target_desc = f"expr:{sql_text[:30]}"
    else:
        raise ValueError("실행할 SQL 문장(-e) 또는 파일(-f)을 지정하세요.")

    stmts = _split_statements(raw_content)
    if not stmts:
        raise ValueError("실행할 유효한 SQL 문장이 없습니다.")

    # 3. 모든 문장 사전 안전 가드 검사
    for s in stmts:
        guard_write_statement(s, allow_ddl=allow_ddl)

    # 4. 백업 수행
    backup_path: str | None = None
    if not dry_run and not no_backup:
        backup_path = run_backup(db_url)

    # 5. 트랜잭션 실행
    output_lines: list[str] = []
    affected_counts: list[str] = []

    with psycopg.connect(db_url, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                for idx, stmt in enumerate(stmts):
                    cur.execute(stmt)
                    row_cnt = cur.rowcount
                    verb = stmt.split()[0].upper()
                    cnt_str = f"{row_cnt}" if isinstance(row_cnt, int) and row_cnt >= 0 else str(row_cnt)
                    output_lines.append(f"문장 {idx + 1}: {verb} {cnt_str}")
                    affected_counts.append(f"{verb}:{cnt_str}")

            if dry_run:
                conn.rollback()
                output_lines.append("드라이런 완료 (롤백됨)")
            else:
                conn.commit()
                b_info = f"백업 {backup_path}" if backup_path else "백업 생략"
                restore_hint = f"pg_restore -d {urlparse(db_url).path.lstrip('/')} < {backup_path}" if backup_path and backup_path.endswith(".dump") else ""
                restore_str = f" · 되돌리기: {restore_hint}" if restore_hint else ""
                output_lines.append(f"커밋됨 · {b_info}{restore_str}")

                # 실행 이력 로깅
                _log_write_history(f"{target_desc} | {', '.join(affected_counts)} | {backup_path or 'no-backup'}")
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"DB 실행 오류로 전체 롤백되었습니다: {exc}") from exc

    return output_lines, backup_path
