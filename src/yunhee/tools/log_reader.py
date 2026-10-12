"""서버 로그 분석 및 요청/SQL/에러 요약 도구 (yunhee log)."""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer

from yunhee import config

KST = timezone(timedelta(hours=9))

LINE_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) \[([^\]]*)\] \[([^\]]*)\] \[([^\]]*)\] \[([^\]]*)\] \[([^\]]+)\] (TRACE|DEBUG|INFO|WARN|ERROR)\s+(\S+) - (.*)$"
)


@dataclass
class LogRecord:
    ts_raw: str
    ts: datetime
    trace: str
    tenant: str
    user: str
    ip: str
    thread: str
    level: str
    logger: str
    msg: str
    extra_lines: list[str] = field(default_factory=list)
    raw_text: str = ""


# 매퍼 XML 캐시 (workspace 내)
_MAPPER_CACHE: dict[str, list[tuple[str, str]]] | None = None  # id -> list of (simple_cls, full_ns)


def _load_mapper_cache() -> dict[str, list[tuple[str, str]]]:
    global _MAPPER_CACHE
    if _MAPPER_CACHE is not None:
        return _MAPPER_CACHE

    cache: dict[str, list[tuple[str, str]]] = {}
    work_dir = config.WORK_DIR
    for xml_file in work_dir.glob("**/src/main/resources/mapper/*.xml"):
        try:
            content = xml_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m_ns = re.search(r'<mapper\s+namespace="([^"]+)"', content)
        if not m_ns:
            continue
        ns = m_ns.group(1)
        simple_cls = ns.split(".")[-1]
        for m_id in re.finditer(r'<[a-zA-Z]+\b[^>]*\bid="([^"]+)"', content):
            sid = m_id.group(1)
            if sid not in cache:
                cache[sid] = []
            cache[sid].append((simple_cls, ns))

    _MAPPER_CACHE = cache
    return cache


def recover_mapper_name(logger_str: str) -> str:
    """logger (예: k.c.k.a.b.e.m.E.selectOthers)에서 매퍼 이름(EmpOthersMapper.selectOthers) 복원."""
    parts = logger_str.split(".")
    if len(parts) < 2:
        return logger_str
    stmt_id = parts[-1]
    cls_initial = parts[-2]

    cache = _load_mapper_cache()
    candidates = cache.get(stmt_id, [])
    matched = [c[0] for c in candidates if c[0].startswith(cls_initial)]
    if len(matched) == 1:
        return f"{matched[0]}.{stmt_id}"
    return logger_str


def mask_sensitive(text: str, enabled: bool = True) -> tuple[str, int]:
    """개인정보(주민등록번호, 비밀번호, JWT) 마스킹 수행."""
    if not enabled:
        return text, 0

    count = 0

    # 1. 주민등록번호 / 외국인등록번호: 6자리-1~8로시작하는7자리
    def repl_rrn(m: re.Match) -> str:
        nonlocal count
        count += 1
        return "******-*******"

    text, _ = re.subn(r"\b\d{6}-?[1-8]\d{6}\b", repl_rrn, text)

    # 2. JWT
    def repl_jwt(m: re.Match) -> str:
        nonlocal count
        count += 1
        return "eyJ…(JWT)"

    text, _ = re.subn(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", repl_jwt, text)

    # 3. Spring Security generated password: Using generated security password: <UUID>
    def repl_sec_pwd(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}****"

    text, _ = re.subn(r"(Using generated security password:\s*)\S+", repl_sec_pwd, text)

    return text, count


def get_first_non_empty_line(msg: str, extra_lines: list[str] | None = None) -> str:
    """msg 또는 extra_lines에서 첫 번째 비어있지 않은 줄을 반환한다."""
    for line in msg.splitlines():
        s = line.strip()
        if s:
            return s
    if extra_lines:
        for line in extra_lines:
            s = line.strip()
            if s:
                return s
    return "(빈 메시지)"


def deduplicate_records(records: list[LogRecord]) -> list[LogRecord]:
    """중복 레코드 제거 (ts_raw, trace, thread, level, logger, msg) 및 시각 순 정렬."""
    seen: set[tuple[str, str, str, str, str, str]] = set()
    deduped: list[LogRecord] = []
    for r in records:
        key = (r.ts_raw, r.trace, r.thread, r.level, r.logger, r.msg)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    deduped.sort(key=lambda r: r.ts)
    return deduped


def parse_log_records(raw_text: str, deduplicate: bool = True) -> list[LogRecord]:
    """로그 본문을 파싱하여 LogRecord 리스트로 반환 (멀티라인 continuation 병합 및 중복 제거)."""
    records: list[LogRecord] = []
    lines = raw_text.splitlines()

    for line in lines:
        m = LINE_RE.match(line)
        if m:
            ts_str, trace, tenant, user, ip, thread, level, logger, msg = m.groups()
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")  # noqa: DTZ007
            except ValueError:
                try:
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                except ValueError:
                    dt = datetime.min.replace(tzinfo=None)  # noqa: DTZ901
            rec = LogRecord(
                ts_raw=ts_str,
                ts=dt,
                trace=trace,
                tenant=tenant,
                user=user,
                ip=ip,
                thread=thread,
                level=level,
                logger=logger,
                msg=msg,
                raw_text=line,
            )
            records.append(rec)
        else:
            if records:
                records[-1].extra_lines.append(line)
                records[-1].raw_text += "\n" + line

    if deduplicate:
        return deduplicate_records(records)
    return records


class DockerExecError(Exception):
    pass


def count_archived_files(
    source_type: str,
    docker_container: str | None,
    log_dir: str,
    app: str,
) -> int:
    """보관된 압축 로그 파일 수 조회."""
    if source_type == "docker" and docker_container:
        cmd = [
            "docker", "exec", docker_container,
            "sh", "-c",
            f"ls -1 {log_dir}/archived/*/{app}*.log.gz 2>/dev/null | wc -l",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out.isdigit():
                return int(out)
        return 0
    elif source_type == "local":
        p = Path(log_dir)
        return len(list(p.glob(f"archived/*/{app}*.log.gz")))
    return 0


def get_dates_in_range(start_date: date, end_date: date) -> list[date]:
    """시작일부터 종료일까지의 날짜 목록 반환 (포함)."""
    if start_date > end_date:
        return []
    days = (end_date - start_date).days
    return [start_date + timedelta(days=i) for i in range(days + 1)]


def read_logs_docker(
    container: str,
    log_dir: str,
    app: str,
    trace_id: str | None = None,
    tail_lines: int = 20000,
    include_error: bool = True,
    error_only: bool = False,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    archived: bool = False,
    user_range_specified: bool = False,
    log_tz: str = "UTC",
) -> str:
    """Docker 컨테이너 안의 로그 파일을 읽는다."""
    info_file = f"{log_dir}/{app}-info.log"
    error_file = f"{log_dir}/{app}-error.log"

    if trace_id:
        sh_cmd = f'grep -F -h "[{trace_id}]" {info_file} {error_file if include_error else ""} 2>/dev/null || true'
        if archived:
            sh_cmd += f'; zgrep -F -h "[{trace_id}]" {log_dir}/archived/*/{app}*.log.gz 2>/dev/null || true'
        cmd = [
            "docker", "exec", container,
            "sh", "-c",
            sh_cmd,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or f"docker exec 종료 코드 {proc.returncode}"
            raise DockerExecError(f"docker exec 실패 ({container}): {err_msg}")
        return proc.stdout

    target_file = error_file if error_only else info_file

    archived_out = ""
    today_date = datetime.now(UTC).date() if log_tz.upper() == "UTC" else datetime.now(KST).date()

    if archived and user_range_specified:
        start_date = start_dt.date() if start_dt else today_date
        end_date = end_dt.date() if end_dt else today_date
        dates = get_dates_in_range(start_date, end_date)
        patterns = []
        for d in dates:
            ym = d.strftime("%Y-%m")
            ymd = d.strftime("%Y-%m-%d")
            if error_only:
                patterns.append(f"{log_dir}/archived/{ym}/{app}-error-{ymd}.*.log.gz")
            elif include_error:
                patterns.append(f"{log_dir}/archived/{ym}/{app}-info-{ymd}.*.log.gz")
                patterns.append(f"{log_dir}/archived/{ym}/{app}-error-{ymd}.*.log.gz")
            else:
                patterns.append(f"{log_dir}/archived/{ym}/{app}-info-{ymd}.*.log.gz")
        if patterns:
            pat_str = " ".join(patterns)
            sh_cmd = f'for f in {pat_str}; do [ -f "$f" ] && zcat "$f" 2>/dev/null; done'
            cmd = ["docker", "exec", container, "sh", "-c", sh_cmd]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and proc.stdout:
                archived_out = proc.stdout

    read_today = True
    if archived and user_range_specified:
        end_date = end_dt.date() if end_dt else today_date
        if end_date < today_date:
            read_today = False

    out = ""
    if read_today:
        current_lines = tail_lines
        prev_len = None
        while True:
            cmd = [
                "docker", "exec", container,
                "sh", "-c",
                f'tail -n {current_lines} {target_file}'
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"docker exec 종료 코드 {proc.returncode}"
                raise DockerExecError(f"docker exec 실패 ({container}): {err_msg}")

            out = proc.stdout
            if not start_dt or current_lines >= 200000:
                break
            if prev_len is not None and len(out) == prev_len:
                break
            prev_len = len(out)

            # 첫 번째 라인의 시각 확인
            first_line = next((l for l in out.splitlines() if LINE_RE.match(l)), None)
            if not first_line:
                break
            m = LINE_RE.match(first_line)
            if m:
                try:
                    first_dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")  # noqa: DTZ007
                except ValueError:
                    first_dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                if first_dt <= start_dt:
                    break
                current_lines = min(current_lines * 2, 200000)
            else:
                break

        if include_error and not error_only:
            # error.log도 가져와 병합
            cmd_err = [
                "docker", "exec", container,
                "sh", "-c",
                f'tail -n {current_lines} {error_file} 2>/dev/null || true'
            ]
            proc_err = subprocess.run(cmd_err, capture_output=True, text=True, check=False)
            if proc_err.returncode == 0 and proc_err.stdout:
                out = f"{out}\n{proc_err.stdout}"

    if archived_out and out:
        return f"{archived_out}\n{out}"
    if archived_out:
        return archived_out
    return out


def read_logs_local(
    log_dir: Path,
    app: str,
    trace_id: str | None = None,
    tail_lines: int = 20000,
    include_error: bool = True,
    error_only: bool = False,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    archived: bool = False,
    user_range_specified: bool = False,
    log_tz: str = "KST",
) -> str:
    """로컬 파일시스템에서 로그 파일을 읽는다."""
    info_file = log_dir / f"{app}-info.log"
    error_file = log_dir / f"{app}-error.log"

    if trace_id:
        if error_only:
            files = [error_file]
        elif include_error:
            files = [info_file, error_file]
        else:
            files = [info_file]

        texts = []
        for f in files:
            if f.is_file():
                try:
                    texts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass

        if archived:
            import gzip
            for gz_file in log_dir.glob(f"archived/*/{app}*.log.gz"):
                try:
                    with gzip.open(gz_file, "rt", encoding="utf-8", errors="replace") as gf:
                        for line in gf:
                            if f"[{trace_id}]" in line:
                                texts.append(line)
                except OSError:
                    pass

        combined = "\n".join(texts)
        lines = [l for l in combined.splitlines() if f"[{trace_id}]" in l]
        return "\n".join(lines)

    today_date = datetime.now(UTC).date() if log_tz.upper() == "UTC" else datetime.now(KST).date()

    texts = []
    if archived and user_range_specified:
        start_date = start_dt.date() if start_dt else today_date
        end_date = end_dt.date() if end_dt else today_date
        dates = get_dates_in_range(start_date, end_date)
        import gzip
        for d in dates:
            ym = d.strftime("%Y-%m")
            ymd = d.strftime("%Y-%m-%d")
            globs = []
            if error_only:
                globs.append(f"archived/{ym}/{app}-error-{ymd}.*.log.gz")
            elif include_error:
                globs.append(f"archived/{ym}/{app}-info-{ymd}.*.log.gz")
                globs.append(f"archived/{ym}/{app}-error-{ymd}.*.log.gz")
            else:
                globs.append(f"archived/{ym}/{app}-info-{ymd}.*.log.gz")
            for pat in globs:
                for gz_file in sorted(log_dir.glob(pat)):
                    try:
                        with gzip.open(gz_file, "rt", encoding="utf-8", errors="replace") as gf:
                            texts.append(gf.read())
                    except OSError:
                        pass

    read_today = True
    if archived and user_range_specified:
        end_date = end_dt.date() if end_dt else today_date
        if end_date < today_date:
            read_today = False

    if read_today:
        if error_only:
            files = [error_file]
        elif include_error:
            files = [info_file, error_file]
        else:
            files = [info_file]

        for f in files:
            if f.is_file():
                try:
                    texts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass

    combined = "\n".join(texts)
    if archived and user_range_specified:
        return combined

    lines = combined.splitlines()
    return "\n".join(lines[-tail_lines:])


def parse_duration(s: str) -> timedelta:
    """30s, 10m, 1h, 2d 문자열을 timedelta로 변환."""
    s = s.strip()
    if s.endswith("s"):
        return timedelta(seconds=float(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=float(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=float(s[:-1]))
    if s.endswith("d"):
        return timedelta(days=float(s[:-1]))
    raise ValueError(f"지원하지 않는 기간 형식입니다: {s} (예: 30s, 10m, 1h, 1d)")


def parse_user_time(t_str: str, host_now: datetime) -> datetime:
    """사용자가 입력한 시각(KST 또는 명시적 타임존)을 datetime으로 변환."""
    t_str = t_str.strip()
    # 1. ISO 포맷
    if "T" in t_str:
        clean = t_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt

    # 2. "YYYY-MM-DD HH:MM:SS" 또는 "YYYY-MM-DD HH:MM"
    m_date = re.match(r"^(\d{4}-\d\d-\d\d)\s+(\d\d:\d\d(?::\d\d)?)$", t_str)
    if m_date:
        d_part = m_date.group(1)
        time_part = m_date.group(2)
        fmt = "%Y-%m-%d %H:%M:%S" if len(time_part) == 8 else "%Y-%m-%d %H:%M"
        dt = datetime.strptime(f"{d_part} {time_part}", fmt).replace(tzinfo=KST)
        return dt

    # 3. "HH:MM:SS" 또는 "HH:MM"
    m_time = re.match(r"^(\d\d:\d\d(?::\d\d)?)$", t_str)
    if m_time:
        time_part = m_time.group(1)
        fmt = "%H:%M:%S" if len(time_part) == 8 else "%H:%M"
        t_parsed = datetime.strptime(time_part, fmt).time()  # noqa: DTZ007
        dt = datetime.combine(host_now.date(), t_parsed, tzinfo=KST)
        if dt > host_now:
            dt = dt - timedelta(days=1)
        return dt

    raise ValueError(f"인식할 수 없는 시각 형식입니다: {t_str}")


def format_header(
    source_type: str,
    file_path: str | None,
    docker_container: str | None,
    log_dir: str,
    app: str,
    tz_str: str,
    mask_count: int = 0,
    extra_tag: str = "",
) -> str:
    mask_part = f" · 마스킹 {mask_count}" if mask_count > 0 else ""
    extra_part = f" {extra_tag}" if extra_tag else ""
    if file_path:
        return f"[log · file:{file_path}{mask_part}{extra_part}]"
    if source_type == "docker":
        return f"[log · docker:{docker_container} · {log_dir} · {app} · {tz_str}{mask_part}{extra_part}]"
    return f"[log · local · {log_dir} · {app} · {tz_str}{mask_part}{extra_part}]"


def format_time_pair(dt_log: datetime, log_tz_is_utc: bool) -> str:
    """로그 시각과 변환된 로컬 KST 시각을 나란히 포맷팅한다."""
    if log_tz_is_utc:
        today_date = datetime.now(UTC).date()
        dt_utc = dt_log.replace(tzinfo=UTC)
        dt_kst = dt_utc.astimezone(KST)
        if dt_log.date() != today_date:
            return f"{dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC ({dt_kst.strftime('%m-%d %H:%M:%S')} KST)"
        return f"{dt_utc.strftime('%H:%M:%S')} UTC ({dt_kst.strftime('%H:%M:%S')} KST)"
    today_date = datetime.now(KST).date()
    if dt_log.date() != today_date:
        return f"{dt_log.strftime('%Y-%m-%d %H:%M:%S')}"
    return f"{dt_log.strftime('%H:%M:%S')}"


def find_deploy_time_docker(container: str, log_dir: str, app: str) -> datetime:
    info_file = f"{log_dir}/{app}-info.log"
    cmd = ["docker", "exec", container, "sh", "-c", f"grep -E 'Started \\w+ in [0-9.]+ seconds' {info_file} | tail -n 1"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err_msg = proc.stderr.strip() or f"종료 코드 {proc.returncode}"
        raise DockerExecError(f"docker exec 실패 ({container}): {err_msg}")
    out = proc.stdout.strip()
    if not out:
        sys.stderr.write("오늘 로그에 배포(앱 시작) 기록 없음 — --archived 또는 --from\n")
        raise typer.Exit(1)
    m = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d{3})?)", out)
    if not m:
        sys.stderr.write("오늘 로그에 배포(앱 시작) 기록 없음 — --archived 또는 --from\n")
        raise typer.Exit(1)
    ts_str = m.group(1)
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in ts_str else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(ts_str, fmt)  # noqa: DTZ007


def find_deploy_time_local(file_path: Path) -> datetime:
    if not file_path.is_file():
        sys.stderr.write("오늘 로그에 배포(앱 시작) 기록 없음 — --archived 또는 --from\n")
        raise typer.Exit(1)
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        sys.stderr.write("오늘 로그에 배포(앱 시작) 기록 없음 — --archived 또는 --from\n")
        raise typer.Exit(1)
    matches = list(re.finditer(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d{3})?).*Started \w+ in [\d.]+ seconds", content, re.MULTILINE))
    if not matches:
        sys.stderr.write("오늘 로그에 배포(앱 시작) 기록 없음 — --archived 또는 --from\n")
        raise typer.Exit(1)
    ts_str = matches[-1].group(1)
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in ts_str else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(ts_str, fmt)  # noqa: DTZ007


def find_run_time(since_run: str) -> tuple[str, str, datetime]:
    from yunhee.store import run_tracker
    run_id_req = None if since_run == "last" else since_run
    if run_id_req:
        run = run_tracker.get_run(run_id_req)
    else:
        run = run_tracker.get_last_run()
    if not run:
        sys.stderr.write(f"run 기록을 찾을 수 없습니다: {since_run}\n")
        raise typer.Exit(1)
    run_id = run["id"]
    cmd = run["command"]
    created_at_str = run["created_at"]
    try:
        dt = datetime.fromisoformat(created_at_str)
    except ValueError:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return run_id, cmd, dt


def resolve_time_range(
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    since_deploy: bool = False,
    since_run: str | None = None,
    default_since: str | None = None,
    log_tz: str = "UTC",
    deploy_getter: Any = None,
) -> tuple[datetime | None, datetime | None, str]:
    """공통 시간 범위 해석 함수."""
    start_flags = [bool(since), bool(from_time), bool(since_deploy), bool(since_run)]
    if sum(start_flags) > 1:
        sys.stderr.write("오류: 시작 시각 옵션은 하나만 지정할 수 있습니다 (--since, --from, --since-deploy, --since-run 중 하나만)\n")
        raise typer.Exit(2)

    is_utc = (log_tz.upper() == "UTC")
    host_now = datetime.now(KST)

    start_log: datetime | None = None
    header_tag = ""

    if since:
        dur = parse_duration(since)
        start_host = host_now - dur
        start_log = start_host.astimezone(UTC).replace(tzinfo=None) if is_utc else start_host.replace(tzinfo=None)
        header_tag = f"최근 {since}"
    elif from_time:
        start_host = parse_user_time(from_time, host_now)
        start_log = start_host.astimezone(UTC).replace(tzinfo=None) if is_utc else start_host.replace(tzinfo=None)
        header_tag = ""
    elif since_deploy:
        if deploy_getter:
            deploy_dt_log = deploy_getter()
            start_log = deploy_dt_log
            if is_utc:
                kst_dt = deploy_dt_log.replace(tzinfo=UTC).astimezone(KST)
                header_tag = f"· 배포 {deploy_dt_log.strftime('%H:%M:%S')} UTC ({kst_dt.strftime('%H:%M:%S')} KST)"
            else:
                header_tag = f"· 배포 {deploy_dt_log.strftime('%H:%M:%S')}"
    elif since_run:
        run_id, cmd, dt_utc = find_run_time(since_run)
        dt_kst = dt_utc.astimezone(KST)
        header_tag = f"· run {run_id} ({cmd}) 시작 {dt_kst.strftime('%H:%M:%S')} KST 이후"
        start_log = dt_utc.astimezone(UTC).replace(tzinfo=None) if is_utc else dt_kst.replace(tzinfo=None)
    elif default_since:
        dur = parse_duration(default_since)
        start_host = host_now - dur
        start_log = start_host.astimezone(UTC).replace(tzinfo=None) if is_utc else start_host.replace(tzinfo=None)
        header_tag = f"최근 {default_since}"

    end_log: datetime | None = None
    if to_time:
        end_host = parse_user_time(to_time, host_now)
        end_log = end_host.astimezone(UTC).replace(tzinfo=None) if is_utc else end_host.replace(tzinfo=None)

    if from_time or to_time:
        if is_utc:
            s_str = start_log.strftime("%Y-%m-%d %H:%M:%S") if start_log else ""
            e_str = end_log.strftime("%Y-%m-%d %H:%M:%S") if end_log else ""
            s_kst = start_log.replace(tzinfo=UTC).astimezone(KST).strftime("%H:%M") if start_log else ""
            e_kst = end_log.replace(tzinfo=UTC).astimezone(KST).strftime("%H:%M") if end_log else ""
            header_tag = f"· 범위 {s_str} ~ {e_str} UTC ({s_kst} ~ {e_kst} KST)"
        else:
            s_str = start_log.strftime("%Y-%m-%d %H:%M:%S") if start_log else ""
            e_str = end_log.strftime("%Y-%m-%d %H:%M:%S") if end_log else ""
            header_tag = f"· 범위 {s_str} ~ {e_str}"

    return start_log, end_log, header_tag


def get_trace_summary(
    trace_id: str,
    file_path: str | None = None,
    source: str | None = None,
    docker_container: str | None = None,
    log_dir: str | None = None,
    app: str | None = None,
    log_tz: str | None = None,
    raw: bool = False,
    show_sql: bool = False,
    archived: bool = False,
    mask: bool = True,
) -> str:
    """단일 trace의 실행 요약 또는 원문 반환."""
    if not re.fullmatch(r"[0-9a-fA-F]{8,32}", trace_id):
        sys.stderr.write("오류: trace ID는 16진수 (8~32자)\n")
        raise typer.Exit(2)

    docker = docker_container if docker_container is not None else config.LOG_DOCKER
    if source == "local":
        docker = ""
    elif source == "docker" and not docker:
        docker = "t3600-tomcat"

    dir_str = log_dir or config.LOG_DIR
    app_str = app or config.LOG_APP
    tz_str = log_tz or ("UTC" if docker else "KST")
    log_is_utc = tz_str.upper() == "UTC"

    if file_path:
        f = Path(file_path)
        if not f.is_file():
            sys.stderr.write(f"로그 파일을 찾을 수 없습니다: {file_path}\n")
            raise typer.Exit(1)
        if str(file_path).endswith(".gz"):
            import gzip
            raw_text = gzip.decompress(f.read_bytes()).decode("utf-8", errors="replace")
        else:
            raw_text = f.read_text(encoding="utf-8", errors="replace")
        all_recs = parse_log_records(raw_text)
        records = [r for r in all_recs if r.trace == trace_id]
        src_type = "file"
    elif docker:
        src_type = "docker"
        try:
            log_text = read_logs_docker(docker, dir_str, app_str, trace_id=trace_id, archived=archived)
        except DockerExecError as e:
            sys.stderr.write(f"{e}\n")
            raise typer.Exit(2) from e
        records = parse_log_records(log_text)
    else:
        src_type = "local"
        log_text = read_logs_local(Path(dir_str), app_str, trace_id=trace_id, archived=archived)
        records = parse_log_records(log_text)

    if not records:
        if archived:
            n_gz = count_archived_files(src_type, docker, dir_str, app_str)
            sys.stderr.write(f"trace {trace_id}: 로그에 없음 (오늘 파일 + archived gz {n_gz}개 검색)\n")
        else:
            sys.stderr.write(f"trace {trace_id}: 로그에 없음 (오늘 파일만 봄 — 지난 날은 --archived)\n")
        raise typer.Exit(1)

    total_masks = 0
    if mask:
        for r in records:
            r.msg, c = mask_sensitive(r.msg, enabled=True)
            total_masks += c
            new_extras = []
            for el in r.extra_lines:
                mel, cel = mask_sensitive(el, enabled=True)
                new_extras.append(mel)
                total_masks += cel
            r.extra_lines = new_extras
            r.raw_text, _ = mask_sensitive(r.raw_text, enabled=True)

    header = format_header(
        source_type=src_type,
        file_path=file_path,
        docker_container=docker,
        log_dir=dir_str,
        app=app_str,
        tz_str=tz_str,
        mask_count=total_masks,
    )

    if raw:
        raw_body = "\n".join(r.raw_text for r in records)
        return f"{header}\n{raw_body.strip()}"

    # 접근 로그 탐색
    access_rec = next((r for r in records if r.logger == "kr.co.kfs.asseterp.access"), None)
    req_line = ""
    if access_rec:
        m_acc = re.match(r"^(\w+)\s+(\S+)\s+(\d{3})\s+(\d+)ms$", access_rec.msg)
        if m_acc:
            meth, path, st_code, el_ms = m_acc.groups()
            context = config.LOG_CONTEXT
            if context and path.startswith(context):
                path = path[len(context):]
            time_part = format_time_pair(access_rec.ts, log_is_utc)
            req_line = f"요청: {meth} {path} → {st_code} ({el_ms}ms) · {access_rec.user} · {access_rec.ip} · {time_part} · trace {trace_id}"
    if not req_line:
        req_line = "요청: (접근 로그 없음 — 진행 중이거나 제외 경로)"

    # SQL 그룹 파싱
    sql_groups: list[dict[str, Any]] = []
    curr_sql: dict[str, Any] | None = None

    for r in records:
        if "==>  Preparing:" in r.msg:
            m_prep = re.search(r"==>\s+Preparing:\s*(.*)$", r.msg)
            sql_text = m_prep.group(1).strip() if m_prep else ""
            curr_sql = {
                "logger": r.logger,
                "sql": sql_text,
                "params": "",
                "result": "",
            }
        elif curr_sql and "==> Parameters:" in r.msg:
            m_p = re.search(r"==>\s+Parameters:\s*(.*)$", r.msg)
            curr_sql["params"] = m_p.group(1).strip() if m_p else ""
        elif curr_sql and ("<==      Total:" in r.msg or "<==    Updates:" in r.msg):
            m_t = re.search(r"<==\s+(Total|Updates):\s*(\d+)", r.msg)
            if m_t:
                curr_sql["result"] = f"{m_t.group(1)} {m_t.group(2)}"
            sql_groups.append(curr_sql)
            curr_sql = None

    def parse_params(raw_p: str) -> str:
        if not raw_p:
            return ""
        items = [p.strip() for p in raw_p.split(",")]
        clean_items = []
        for it in items:
            c = re.sub(r"\([A-Za-z]+\)$", "", it)
            if len(c) > 60:
                c = c[:57] + "…"
            clean_items.append(c)
        if len(clean_items) <= 6:
            return ", ".join(clean_items)
        return f"{', '.join(clean_items[:4])}, … {len(clean_items)}개"

    rendered_sqls: list[tuple[str, str, str]] = []
    consec_count = 1
    for i, g in enumerate(sql_groups):
        stmt_name = recover_mapper_name(g["logger"])
        param_str = parse_params(g["params"])
        p_desc = f"({param_str})" if param_str else "()"
        res_str = f"→ {g['result']}" if g["result"] else ""
        line_item = f"{stmt_name} {p_desc} {res_str}".strip()

        if i + 1 < len(sql_groups):
            next_g = sql_groups[i + 1]
            if next_g["logger"] == g["logger"] and next_g["params"] == g["params"] and next_g["result"] == g["result"]:
                consec_count += 1
                continue

        count_suffix = f" ×{consec_count}" if consec_count > 1 else ""
        consec_count = 1
        rendered_sqls.append((line_item + count_suffix, g["sql"], g["params"]))

    sql_section_lines = [f"SQL {len(sql_groups)}:"]
    for idx, (s_line, prep_sql, raw_params) in enumerate(rendered_sqls, 1):
        sql_section_lines.append(f"  {idx}. {s_line}")
        if show_sql and prep_sql:
            param_vals = [re.sub(r"\([A-Za-z]+\)$", "", p.strip()) for p in raw_params.split(",") if p.strip()]
            sub_sql = prep_sql
            for pv in param_vals:
                if pv == "null":
                    rep = "NULL"
                elif pv.isdigit():
                    rep = pv
                else:
                    rep = f"'{pv}'"
                sub_sql = sub_sql.replace("?", rep, 1)
            is_dml = any(sub_sql.lstrip().upper().startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "WITH"))
            if is_dml:
                sql_section_lines.append(f"     -- (DML: 실행하지 마세요)\n     {sub_sql}")
            else:
                sql_section_lines.append(f"     {sub_sql}")

    err_recs = [r for r in records if r.level in ("WARN", "ERROR")]
    err_lines = []
    if not err_recs:
        err_lines.append("WARN/ERROR: 없음")
    else:
        err_lines.append(f"WARN/ERROR {len(err_recs)}:")
        for er in err_recs:
            msg_first = get_first_non_empty_line(er.msg, er.extra_lines)
            today_date = datetime.now(UTC).date() if log_is_utc else datetime.now(KST).date()
            t_str = er.ts.strftime("%m-%d %H:%M:%S") if er.ts.date() != today_date else er.ts.strftime("%H:%M:%S")
            err_lines.append(f"  {t_str} {er.level} {er.logger} - {msg_first}")
            if er.extra_lines:
                cb = next((el.strip() for el in reversed(er.extra_lines) if "Caused by:" in el), None)
                if cb:
                    err_lines.append(f"    {cb}")

    out = [
        header,
        req_line,
        "\n".join(sql_section_lines),
        "\n".join(err_lines),
        f"원문: yunhee log trace {trace_id} --raw{' --archived' if archived else ''}",
    ]
    return "\n".join(out)


def get_req_summary(
    method: str,
    path_pattern: str,
    last: int = 5,
    show_trace: bool = False,
    file_path: str | None = None,
    source: str | None = None,
    docker_container: str | None = None,
    log_dir: str | None = None,
    app: str | None = None,
    log_tz: str | None = None,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    since_deploy: bool = False,
    since_run: str | None = None,
    archived: bool = False,
    mask: bool = True,
) -> str:
    """접근 로그를 필터링하여 최근 요청 목록 반환."""
    docker = docker_container if docker_container is not None else config.LOG_DOCKER
    if source == "local":
        docker = ""
    elif source == "docker" and not docker:
        docker = "t3600-tomcat"

    dir_str = log_dir or config.LOG_DIR
    app_str = app or config.LOG_APP
    tz_str = log_tz or ("UTC" if docker else "KST")

    if file_path:
        deploy_getter = lambda: find_deploy_time_local(Path(file_path))
    elif docker:
        deploy_getter = lambda: find_deploy_time_docker(docker, dir_str, app_str)
    else:
        deploy_getter = lambda: find_deploy_time_local(Path(dir_str) / f"{app_str}-info.log")

    user_range_specified = bool(since or from_time or since_deploy or since_run)

    start_dt, end_dt, header_tag = resolve_time_range(
        since=since,
        from_time=from_time,
        to_time=to_time,
        since_deploy=since_deploy,
        since_run=since_run,
        default_since="24h" if not file_path else None,
        log_tz=tz_str,
        deploy_getter=deploy_getter,
    )

    if file_path:
        f = Path(file_path)
        if not f.is_file():
            sys.stderr.write(f"로그 파일을 찾을 수 없습니다: {file_path}\n")
            raise typer.Exit(1)
        raw_text = f.read_text(encoding="utf-8", errors="replace")
        src_type = "file"
    elif docker:
        src_type = "docker"
        try:
            raw_text = read_logs_docker(
                docker,
                dir_str,
                app_str,
                include_error=False,
                start_dt=start_dt,
                end_dt=end_dt,
                archived=archived,
                user_range_specified=user_range_specified,
                log_tz=tz_str,
            )
        except DockerExecError as e:
            sys.stderr.write(f"{e}\n")
            raise typer.Exit(2) from e
    else:
        src_type = "local"
        raw_text = read_logs_local(
            Path(dir_str),
            app_str,
            include_error=False,
            start_dt=start_dt,
            end_dt=end_dt,
            archived=archived,
            user_range_specified=user_range_specified,
            log_tz=tz_str,
        )

    records = parse_log_records(raw_text)

    # 접근 로그 필터링
    matches: list[tuple[LogRecord, str, int, int]] = []  # rec, path, status, elapsed_ms
    for r in records:
        if r.logger != "kr.co.kfs.asseterp.access":
            continue
        if start_dt and r.ts < start_dt:
            continue
        if end_dt and r.ts >= end_dt:
            continue

        m_acc = re.match(r"^(\w+)\s+(\S+)\s+(\d{3})\s+(\d+)ms$", r.msg)
        if not m_acc:
            continue
        meth, full_path, st_str, el_str = m_acc.groups()
        if meth.upper() != method.upper():
            continue

        context = config.LOG_CONTEXT
        path = full_path[len(context):] if context and full_path.startswith(context) else full_path
        if path_pattern not in path and path_pattern not in full_path:
            continue

        matches.append((r, path, int(st_str), int(el_str)))

    # 최근 순 정렬
    matches.sort(key=lambda x: x[0].ts, reverse=True)
    selected = matches[:last]

    total_masks = 0
    header = format_header(
        source_type=src_type,
        file_path=file_path,
        docker_container=docker,
        log_dir=dir_str,
        app=app_str,
        tz_str=tz_str,
        mask_count=total_masks,
        extra_tag=header_tag if header_tag.startswith("· ") else "",
    )

    out = [header]
    if archived and not user_range_specified:
        out.append("(--archived: 범위가 오늘이라 지난 파일을 읽지 않음)")

    today_date = datetime.now(UTC).date() if tz_str.upper() == "UTC" else datetime.now(KST).date()

    out.append(f"{method.upper()} {path_pattern} 최근 {len(selected)}:")
    for rec, p, st, el in selected:
        t_str = rec.ts.strftime("%m-%d %H:%M:%S") if rec.ts.date() != today_date else rec.ts.strftime("%H:%M:%S")
        out.append(f"  {t_str} {tz_str}  {st:3d}  {el:4d}ms  {rec.user}  trace {rec.trace}")

    if selected:
        latest_trace = selected[0][0].trace
        out.append(f"→ 가장 최근 요약: yunhee log trace {latest_trace}")
        if show_trace:
            trace_body = get_trace_summary(
                trace_id=latest_trace,
                file_path=file_path,
                source=source,
                docker_container=docker,
                log_dir=log_dir,
                app=app,
                log_tz=log_tz,
                archived=archived,
                mask=mask,
            )
            # 머리 줄 제외
            t_lines = trace_body.splitlines()
            out.append("\n" + "\n".join(t_lines[1:] if len(t_lines) > 1 else t_lines))
        if not archived and start_dt:
            earliest_dt = records[0].ts if records else None
            if earliest_dt and start_dt < earliest_dt:
                out.append(f"  (오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived)")
            elif not earliest_dt and start_dt.date() < today_date:
                out.append("  (오늘 파일은 기록 없음 — 그 전은 --archived)")
    else:
        out.append("  (일치하는 요청 없음)")
        if not archived and start_dt:
            earliest_dt = records[0].ts if records else None
            if earliest_dt and start_dt < earliest_dt:
                out.append(f"  오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived")
            elif not earliest_dt and start_dt.date() < today_date:
                out.append("  오늘 파일은 기록 없음 — 그 전은 --archived")

    return "\n".join(out)


def get_errors_summary(
    file_path: str | None = None,
    source: str | None = None,
    docker_container: str | None = None,
    log_dir: str | None = None,
    app: str | None = None,
    log_tz: str | None = None,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    since_deploy: bool = False,
    since_run: str | None = None,
    ignore_loggers: list[str] | None = None,
    explain: bool = False,
    archived: bool = False,
    mask: bool = True,
) -> str:
    """WARN/ERROR 로그 그룹화 요약 반환."""
    docker = docker_container if docker_container is not None else config.LOG_DOCKER
    if source == "local":
        docker = ""
    elif source == "docker" and not docker:
        docker = "t3600-tomcat"

    dir_str = log_dir or config.LOG_DIR
    app_str = app or config.LOG_APP
    tz_str = log_tz or ("UTC" if docker else "KST")

    if file_path:
        deploy_getter = lambda: find_deploy_time_local(Path(file_path))
    elif docker:
        deploy_getter = lambda: find_deploy_time_docker(docker, dir_str, app_str)
    else:
        deploy_getter = lambda: find_deploy_time_local(Path(dir_str) / f"{app_str}-info.log")

    user_range_specified = bool(since or from_time or since_deploy or since_run)

    start_dt, end_dt, header_tag = resolve_time_range(
        since=since,
        from_time=from_time,
        to_time=to_time,
        since_deploy=since_deploy,
        since_run=since_run,
        default_since="1h" if not file_path else None,
        log_tz=tz_str,
        deploy_getter=deploy_getter,
    )

    if file_path:
        f = Path(file_path)
        if not f.is_file():
            sys.stderr.write(f"로그 파일을 찾을 수 없습니다: {file_path}\n")
            raise typer.Exit(1)
        raw_text = f.read_text(encoding="utf-8", errors="replace")
        src_type = "file"
    elif docker:
        src_type = "docker"
        try:
            raw_text = read_logs_docker(
                docker,
                dir_str,
                app_str,
                error_only=True,
                start_dt=start_dt,
                end_dt=end_dt,
                archived=archived,
                user_range_specified=user_range_specified,
                log_tz=tz_str,
            )
        except DockerExecError as e:
            sys.stderr.write(f"{e}\n")
            raise typer.Exit(2) from e
    else:
        src_type = "local"
        raw_text = read_logs_local(
            Path(dir_str),
            app_str,
            error_only=True,
            start_dt=start_dt,
            end_dt=end_dt,
            archived=archived,
            user_range_specified=user_range_specified,
            log_tz=tz_str,
        )

    records = parse_log_records(raw_text)

    # WARN / ERROR 필터링
    filtered: list[LogRecord] = []
    for r in records:
        if r.level not in ("WARN", "ERROR"):
            continue
        if start_dt and r.ts < start_dt:
            continue
        if end_dt and r.ts >= end_dt:
            continue
        if ignore_loggers and any(ig in r.logger for ig in ignore_loggers):
            continue
        filtered.append(r)

    total_masks = 0
    if mask:
        for r in filtered:
            r.msg, c = mask_sensitive(r.msg, enabled=True)
            total_masks += c
            new_extras = []
            for el in r.extra_lines:
                mel, cel = mask_sensitive(el, enabled=True)
                new_extras.append(mel)
                total_masks += cel
            r.extra_lines = new_extras
            r.raw_text, _ = mask_sensitive(r.raw_text, enabled=True)

    # 묶기: 키 = (level, logger, norm_msg[:80])
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in filtered:
        msg_first = get_first_non_empty_line(r.msg, r.extra_lines)
        # 숫자·UUID·16진 ID를 '#'으로 치환
        norm = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "#", msg_first)
        norm = re.sub(r"\b[0-9a-fA-F]{8,}\b", "#", norm)
        norm = re.sub(r"\b\d+\b", "#", norm)
        norm_key = norm[:80]
        key = (r.level, r.logger, norm_key)

        if key not in groups:
            groups[key] = {
                "level": r.level,
                "logger": r.logger,
                "sample_rec": r,
                "norm_msg": norm,
                "count": 0,
                "min_ts": r.ts,
                "max_ts": r.ts,
                "traces": set(),
            }
        g = groups[key]
        g["count"] += 1
        g["min_ts"] = min(g["min_ts"], r.ts)
        g["max_ts"] = max(g["max_ts"], r.ts)
        if r.trace not in ("SYSTEM", "-", ""):
            g["traces"].add(r.trace)

    sorted_groups = sorted(groups.values(), key=lambda x: x["count"], reverse=True)

    header = format_header(
        source_type=src_type,
        file_path=file_path,
        docker_container=docker,
        log_dir=dir_str,
        app=app_str,
        tz_str=tz_str,
        mask_count=total_masks,
        extra_tag=header_tag if header_tag.startswith("· ") else "",
    )

    out = [header]
    if archived and not user_range_specified:
        out.append("(--archived: 범위가 오늘이라 지난 파일을 읽지 않음)")
    time_desc = header_tag if header_tag and not header_tag.startswith("· ") else "선택 범위"
    out.append(f"WARN/ERROR {time_desc}: {len(filtered)}줄, {len(sorted_groups)}종")

    for g in sorted_groups:
        sample_r: LogRecord = g["sample_rec"]
        msg_sample = g["norm_msg"] if g["count"] > 1 else get_first_non_empty_line(sample_r.msg, sample_r.extra_lines)
        if mask:
            msg_sample, _ = mask_sensitive(msg_sample, enabled=True)

        trace_part = ""
        if g["traces"]:
            t_list = sorted(g["traces"])
            t_str = f"trace {', '.join(t_list[:3])}{'…' if len(t_list) > 3 else ''}"
            time_span = f"{g['min_ts'].strftime('%H:%M')}~{g['max_ts'].strftime('%H:%M')}" if g["min_ts"].strftime('%H:%M') != g["max_ts"].strftime('%H:%M') else g["min_ts"].strftime('%H:%M')
            trace_part = f"  ({time_span}, {t_str})"

        out.append(f"  ×{g['count']:>2} {g['level']:<5} {g['logger']} - {msg_sample}{trace_part}")

        # Caused by 탐색
        if sample_r.extra_lines:
            cb = next((el.strip() for el in reversed(sample_r.extra_lines) if "Caused by:" in el), None)
            if cb:
                if mask:
                    cb, _ = mask_sensitive(cb, enabled=True)
                out.append(f"    {cb}")

        # --explain 지원
        if explain:
            from yunhee.ollama_client import chat
            prompt = (
                "다음 에러 스택 트레이스를 분석하여 원인을 한국어로 정확히 1줄로 요약해줘.\n\n"
                f"{sample_r.msg}\n" + "\n".join(sample_r.extra_lines[:40])
            )
            try:
                res_exp = chat([{"role": "user", "content": prompt}], max_tokens=150)
                exp_lines = res_exp.strip().splitlines()
                exp_line = exp_lines[0] if exp_lines else "(설명 없음)"
                out.append(f"    ↳ 원인: {exp_line}")
            except Exception:  # noqa: BLE001, S110
                pass

    today_date = datetime.now(UTC).date() if tz_str.upper() == "UTC" else datetime.now(KST).date()
    if not sorted_groups:
        out.append("  (기록 없음)")
        if not archived and start_dt:
            earliest_dt = records[0].ts if records else None
            if earliest_dt and start_dt < earliest_dt:
                out.append(f"  오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived")
            elif not earliest_dt and start_dt.date() < today_date:
                out.append("  오늘 파일은 기록 없음 — 그 전은 --archived")
    elif not archived and start_dt:
        earliest_dt = records[0].ts if records else None
        if earliest_dt and start_dt < earliest_dt:
            out.append(f"  (오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived)")
        elif not earliest_dt and start_dt.date() < today_date:
            out.append("  (오늘 파일은 기록 없음 — 그 전은 --archived)")

    return "\n".join(out)


def get_tail_summary(
    level: str | None = None,
    grep_pattern: str | None = None,
    trace_only: bool = False,
    show_all: bool = False,
    file_path: str | None = None,
    source: str | None = None,
    docker_container: str | None = None,
    log_dir: str | None = None,
    app: str | None = None,
    log_tz: str | None = None,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    since_deploy: bool = False,
    since_run: str | None = None,
    archived: bool = False,
    mask: bool = True,
) -> str:
    """최근 로그를 요청(trace) 단위로 접어서 요약 반환."""
    docker = docker_container if docker_container is not None else config.LOG_DOCKER
    if source == "local":
        docker = ""
    elif source == "docker" and not docker:
        docker = "t3600-tomcat"

    dir_str = log_dir or config.LOG_DIR
    app_str = app or config.LOG_APP
    tz_str = log_tz or ("UTC" if docker else "KST")

    if file_path:
        deploy_getter = lambda: find_deploy_time_local(Path(file_path))
    elif docker:
        deploy_getter = lambda: find_deploy_time_docker(docker, dir_str, app_str)
    else:
        deploy_getter = lambda: find_deploy_time_local(Path(dir_str) / f"{app_str}-info.log")

    user_range_specified = bool(since or from_time or since_deploy or since_run)

    start_dt, end_dt, header_tag = resolve_time_range(
        since=since,
        from_time=from_time,
        to_time=to_time,
        since_deploy=since_deploy,
        since_run=since_run,
        default_since="10m" if not file_path else None,
        log_tz=tz_str,
        deploy_getter=deploy_getter,
    )

    if file_path:
        f = Path(file_path)
        if not f.is_file():
            sys.stderr.write(f"로그 파일을 찾을 수 없습니다: {file_path}\n")
            raise typer.Exit(1)
        raw_text = f.read_text(encoding="utf-8", errors="replace")
        src_type = "file"
    elif docker:
        src_type = "docker"
        try:
            raw_text = read_logs_docker(
                docker,
                dir_str,
                app_str,
                include_error=True,
                start_dt=start_dt,
                end_dt=end_dt,
                archived=archived,
                user_range_specified=user_range_specified,
                log_tz=tz_str,
            )
        except DockerExecError as e:
            sys.stderr.write(f"{e}\n")
            raise typer.Exit(2) from e
    else:
        src_type = "local"
        raw_text = read_logs_local(
            Path(dir_str),
            app_str,
            include_error=True,
            start_dt=start_dt,
            end_dt=end_dt,
            archived=archived,
            user_range_specified=user_range_specified,
            log_tz=tz_str,
        )

    records = parse_log_records(raw_text)

    # 시간 범위 필터
    filtered = [
        r for r in records
        if (start_dt is None or r.ts >= start_dt) and (end_dt is None or r.ts < end_dt)
    ]

    total_masks = 0
    if mask:
        for r in filtered:
            r.msg, c = mask_sensitive(r.msg, enabled=True)
            total_masks += c
            new_extras = []
            for el in r.extra_lines:
                mel, cel = mask_sensitive(el, enabled=True)
                new_extras.append(mel)
                total_masks += cel
            r.extra_lines = new_extras
            r.raw_text, _ = mask_sensitive(r.raw_text, enabled=True)

    # trace 그룹핑
    traces_map: dict[str, list[LogRecord]] = {}
    standalone_records: list[LogRecord] = []

    for r in filtered:
        if r.trace not in ("SYSTEM", "-", ""):
            traces_map.setdefault(r.trace, []).append(r)
        else:
            standalone_records.append(r)

    # grep 필터 (Item 4: trace 내 어느 줄이라도 일치하면 trace 전체 보존)
    if grep_pattern:
        filtered_traces = {}
        for tid, recs in traces_map.items():
            if any(
                grep_pattern in r.msg
                or grep_pattern in r.logger
                or any(grep_pattern in el for el in r.extra_lines)
                for r in recs
            ):
                filtered_traces[tid] = recs
        traces_map = filtered_traces

        standalone_records = [
            r for r in standalone_records
            if grep_pattern in r.msg
            or grep_pattern in r.logger
            or any(grep_pattern in el for el in r.extra_lines)
        ]

    # level 필터 (Item 3: trace 내 해당 레벨 이상 레코드가 하나라도 있는 경우만 보존)
    if level:
        lvl_upper = level.upper()
        if lvl_upper == "ERROR":
            valid_levels = {"ERROR"}
        elif lvl_upper == "WARN":
            valid_levels = {"WARN", "ERROR"}
        elif lvl_upper == "INFO":
            valid_levels = {"INFO", "WARN", "ERROR"}
        elif lvl_upper == "DEBUG":
            valid_levels = {"DEBUG", "INFO", "WARN", "ERROR"}
        elif lvl_upper == "TRACE":
            valid_levels = {"TRACE", "DEBUG", "INFO", "WARN", "ERROR"}
        else:
            valid_levels = {lvl_upper}

        filtered_traces = {}
        for tid, recs in traces_map.items():
            if any(r.level in valid_levels for r in recs):
                filtered_traces[tid] = recs
        traces_map = filtered_traces

        standalone_records = [
            r for r in standalone_records
            if r.level in valid_levels
        ]

    # 요약 통계 계산
    sql_count = 0
    warn_count = 0
    error_count = 0

    for recs in traces_map.values():
        for r in recs:
            if "==>  Preparing:" in r.msg:
                sql_count += 1
            if r.level == "WARN":
                warn_count += 1
            elif r.level == "ERROR":
                error_count += 1

    for r in standalone_records:
        if "==>  Preparing:" in r.msg:
            sql_count += 1
        if r.level == "WARN":
            warn_count += 1
        elif r.level == "ERROR":
            error_count += 1

    # 요청(trace) 목록 구성
    hidden_non_http = 0
    hidden_ws = 0
    req_items: list[tuple[datetime, str]] = []  # (ts, line_str)

    today_date = datetime.now(UTC).date() if tz_str.upper() == "UTC" else datetime.now(KST).date()

    for tid, recs in traces_map.items():
        access_r = next((r for r in recs if r.logger == "kr.co.kfs.asseterp.access"), None)
        t_sql_cnt = sum(1 for r in recs if "==>  Preparing:" in r.msg)
        first_r = recs[0]
        ts = access_r.ts if access_r else first_r.ts
        t_str = ts.strftime("%m-%d %H:%M:%S") if ts.date() != today_date else ts.strftime("%H:%M:%S")

        # trace 내 WARN/ERROR 요약 (Item 5)
        err_recs = [r for r in recs if r.level in ("WARN", "ERROR")]
        warn_err_suffix = ""
        if err_recs:
            best_err = next((r for r in err_recs if r.level == "ERROR"), err_recs[0])
            msg_first = get_first_non_empty_line(best_err.msg, best_err.extra_lines)
            if len(msg_first) > 60:
                msg_first = msg_first[:57] + "…"
            warn_err_suffix = f"  ⚠{best_err.level} {msg_first}"

        if access_r:
            m_acc = re.match(r"^(\w+)\s+(\S+)\s+(\d{3})\s+(\d+)ms$", access_r.msg)
            if m_acc:
                meth, full_path, st, el = m_acc.groups()
                context = config.LOG_CONTEXT
                path = full_path[len(context):] if context and full_path.startswith(context) else full_path

                # WebSocket 노이즈 숨김 (Item 7-4): WARN/ERROR가 없는 /ws 또는 st == 101
                is_ws = (st == "101" or path == "/ws" or path.startswith("/ws/"))
                if not show_all and is_ws and not err_recs:
                    hidden_ws += 1
                    continue

                line = f"  {t_str}  {meth:<4}  {path:<40}  {st}  {el:>4}ms  SQL {t_sql_cnt}  trace {tid[:8]}…{warn_err_suffix}"
                req_items.append((ts, line))
            else:
                line = f"  {t_str}  {access_r.msg}  SQL {t_sql_cnt}  trace {tid[:8]}…{warn_err_suffix}"
                req_items.append((ts, line))
        else:
            # 비-HTTP 요청 숨김 (Item 7-4): WARN/ERROR가 없는 경우만 숨김
            if not show_all and not err_recs:
                hidden_non_http += 1
                continue
            if not trace_only:
                line = f"  {t_str}  (비-HTTP 요청)  SQL {t_sql_cnt}  trace {tid[:8]}…{warn_err_suffix}"
                req_items.append((ts, line))

    # standalone 에러 추가
    if not trace_only:
        for er in standalone_records:
            if er.level in ("WARN", "ERROR"):
                t_str = er.ts.strftime("%m-%d %H:%M:%S") if er.ts.date() != today_date else er.ts.strftime("%H:%M:%S")
                msg_first = get_first_non_empty_line(er.msg, er.extra_lines)
                if len(msg_first) > 60:
                    msg_first = msg_first[:57] + "…"
                line = f"  {er.level} {t_str} {er.logger} - {msg_first}"
                req_items.append((er.ts, line))

    req_items.sort(key=lambda x: x[0], reverse=True)

    header = format_header(
        source_type=src_type,
        file_path=file_path,
        docker_container=docker,
        log_dir=dir_str,
        app=app_str,
        tz_str=tz_str,
        mask_count=total_masks,
        extra_tag=header_tag if header_tag.startswith("· ") else "",
    )

    out = [header]
    if archived and not user_range_specified:
        out.append("(--archived: 범위가 오늘이라 지난 파일을 읽지 않음)")

    time_desc = header_tag if header_tag and not header_tag.startswith("· ") else "선택 범위"
    summary_line = f"{time_desc}: 요청 {len(traces_map)}, SQL {sql_count}, WARN {warn_count}, ERROR {error_count}"

    hidden_info = []
    if hidden_non_http > 0:
        hidden_info.append(f"비-HTTP {hidden_non_http}")
    if hidden_ws > 0:
        hidden_info.append(f"/ws {hidden_ws}")
    if hidden_info:
        summary_line += f" ({', '.join(hidden_info)} 숨김 — --all)"

    out.append(summary_line)
    for _, item_str in req_items:
        out.append(item_str)

    if not req_items:
        out.append("  (기록 없음)")
        if not archived and start_dt:
            earliest_dt = records[0].ts if records else None
            if earliest_dt and start_dt < earliest_dt:
                out.append(f"  오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived")
            elif not earliest_dt and start_dt.date() < today_date:
                out.append("  오늘 파일은 기록 없음 — 그 전은 --archived")
    elif not archived and start_dt:
        earliest_dt = records[0].ts if records else None
        if earliest_dt and start_dt < earliest_dt:
            out.append(f"  (오늘 파일은 {earliest_dt.strftime('%H:%M')}부터 — 그 전은 --archived)")
        elif not earliest_dt and start_dt.date() < today_date:
            out.append("  (오늘 파일은 기록 없음 — 그 전은 --archived)")

    return "\n".join(out)
