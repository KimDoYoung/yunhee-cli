#!/usr/bin/env python3
"""PreToolUse(Bash) 훅 검사 스크립트.

AS-IS 원본·색인과 TOBE 소스를 cat/sed/head/tail/less/more/awk나 grep 문맥 출력(-A/-B/-C)으로 직접 읽거나
psql을 직접 실행하는 명령을 정밀 차단한다.

따옴표 안 문자열, heredoc 본문, echo/git commit -m 등의 인자는 검사에서 제외하며,
오직 실제 셸 명령 위치의 명령어만 검사한다.
"""

import json
import re
import sys


def strip_heredocs(cmd: str) -> str:
    """heredoc (<<'EOF' ... EOF 또는 <<-EOF ... EOF) 본문을 공백 라인으로 치환한다."""
    lines = cmd.splitlines(keepends=True)
    out_lines = []
    in_heredoc = False
    delimiter = None
    hd_start_re = re.compile(r"<<-?[ \t]*['\"]?([A-Za-z0-9_]+)['\"]?")

    for l in lines:
        if in_heredoc:
            if l.strip() == delimiter:
                in_heredoc = False
                out_lines.append("\n")
            continue
        m = hd_start_re.search(l)
        if m:
            in_heredoc = True
            delimiter = m.group(1)
            out_lines.append(l)
        else:
            out_lines.append(l)
    return "".join(out_lines)


def mask_string_literals(text: str) -> str:
    """따옴표('...', \"...\") 내부의 문자열을 공백으로 치환하여 셸 명령어 검사에서 제외한다."""
    chars = list(text)
    in_q = None
    escape = False
    for i, c in enumerate(chars):
        if escape:
            escape = False
            chars[i] = " "
            continue
        if in_q:
            if c == "\\":
                escape = True
                chars[i] = " "
            elif c == in_q:
                in_q = None
            else:
                chars[i] = " "
        elif c in ("'", '"'):
            in_q = c
    return "".join(chars)


def split_shell_commands(cmd: str) -> list[tuple[str, bool, str]]:
    """명령어를 세미콜론, &&, ||, 파이프, 줄바꿈 단위로 분리한다.

    반환: list of (원본_세그먼트, 파이프_오른쪽_여부, 마스킹_세그먼트)
    """
    clean = strip_heredocs(cmd)
    masked = mask_string_literals(clean)

    # 마스킹된 문자열에서 분리자 위치 찾기
    sep_pattern = re.compile(r"(\n|;|&&|\|\||\|)")
    splits = []
    last_idx = 0
    is_pipe = False

    for m in sep_pattern.finditer(masked):
        start, end = m.span()
        seg_raw = clean[last_idx:start]
        seg_mask = masked[last_idx:start]
        splits.append((seg_raw.strip(), is_pipe, seg_mask.strip()))

        sep = m.group(1)
        is_pipe = (sep == "|")
        last_idx = end

    if last_idx < len(clean):
        seg_raw = clean[last_idx:]
        seg_mask = masked[last_idx:]
        splits.append((seg_raw.strip(), is_pipe, seg_mask.strip()))

    return [(r, p, m) for r, p, m in splits if r]


PROT_PATHS_RE = re.compile(
    r"(oms-data/src|backend/src/main/java|backend/src/main/resources/mapper|backend/src/test/java|frontend/src|docs/as-is/|docs/[0-9]+-)"
)

PSQL_RE = re.compile(
    r"(^|[;&|(`]\s*|&&\s*)(sudo\s+([^;&|]*\s)?)?(psql|pg_dump|pg_restore)(\s|$)|(docker|podman)\s+(compose\s+)?exec\s[^;&|]*\s(psql|pg_dump)(\s|$)"
)


def inspect_command(cmd: str) -> tuple[bool, str, str]:
    """명령어를 검사하여 차단 여부, 차단 트리거 토큰, 차단 사유를 반환한다."""
    if not cmd or not cmd.strip():
        return False, "", ""

    # 1. psql 직접 실행 검사
    clean_no_hd = strip_heredocs(cmd)
    masked_for_psql = mask_string_literals(clean_no_hd)
    # echo, printf, yunhee, curl, git commit 제거 후 psql 탐지
    check_psql = re.sub(r"yunhee\s+(run\s+.*|[^;&|]*)", "", masked_for_psql)
    check_psql = re.sub(r"\b(echo|printf|curl)\b[^;&|\n]*", "", check_psql)
    check_psql = re.sub(r"\bgit\s+commit\b[^;&|\n]*", "", check_psql)

    if PSQL_RE.search(check_psql):
        m = PSQL_RE.search(check_psql)
        trigger = m.group(0).strip()
        psql_reason = (
            "psql 직접 실행은 비밀번호 대기로 멈춘다(터미널 없음). 읽기 쿼리는 yunhee를 쓴다(05 §7):\n"
            "- 조회·행 수·중복: yunhee sql \"<SELECT>\" [-n 행수] [--timeout 초]  (읽기 전용 강제, 기본 5행, 결과는 마크다운 표)\n"
            "- 쓰기 SQL 시험: yunhee sql -f x.sql --rollback  (항상 ROLLBACK)\n"
            "- 테이블 구조: yunhee table <이름>  /  스키마 문서: yunhee dbml\n"
            "- 파일로 받기(예: menus.tsv): yunhee sql … -n 2000 → 표를 변환.\n"
            "DDL·DML을 실제로 실행해야 하면 사용자에게 `! psql …`로 직접 실행해 달라고 요청한다."
        )
        return True, trigger, psql_reason

    # 2. 소스/색인 직접 읽기 도구 검사
    segments = split_shell_commands(cmd)
    read_reason = (
        "AS-IS 원본·색인과 TOBE 소스를 cat/sed/head/tail/awk나 grep 문맥 출력(-A/-B/-C)으로 직접 읽지 않는다(05 §7, 사용자 지시 2026-10-12). 대신:\n"
        "- AS-IS: yunhee analysis screen <화면> --class <클래스> --section …, analysis method <클래스>.<메서드> [-o code], analysis grid <클래스>, analysis sql <ns.id>, yunhee table <테이블>\n"
        "- TOBE: yunhee outline <파일…> 또는 yunhee analysis tobe <파일> → 필요한 줄만 Read(offset/limit)\n"
        "- 메뉴 찾기(docs/as-is/**/menus.md·menus.tsv)의 grep은 된다\n"
        "yunhee로 정말 안 되면 작업기록에 사유를 쓰지 말고 yunhee 수정사항으로 제안할 것."
    )

    for seg_raw, is_pipe, seg_mask in segments:
        # yunhee 명령어는 안전
        if re.match(r"^yunhee\b", seg_mask):
            continue
        # echo, printf 등 단순 출력은 안전
        if re.match(r"^(echo|printf)\b", seg_mask):
            continue
        # python, bash 인터프리터 호출은 안전 (내부 코드는 heredoc 또는 인자로 마스킹됨)
        if re.match(r"^(python3?|bash|sh|node)\b", seg_mask):
            continue

        # 파일 쓰기 예외 (cat > file, cat >> file, cat <<EOF > file, sed -i)
        if re.search(r"\bcat\b.*?(>|>>)", seg_mask) or re.search(r"\bcat\s*(>|>>)", seg_mask):
            continue
        if re.search(r"\bsed\b.*(-i|--in-place)", seg_mask):
            continue

        # 명령 위치의 도구 추출
        m_tool = re.match(r"^(sudo\s+)?(cat|sed|head|tail|less|more|awk|bat|grep|rg)\b", seg_mask)
        if not m_tool:
            continue
        tool = m_tool.group(2)

        # 파이프 뒤의 단순 줄 수 제한(ls | tail -3 등)은 보호 파일 인자가 없으면 통과
        if is_pipe and not PROT_PATHS_RE.search(seg_raw):
            continue

        # 보호 대상 파일 경로가 포함되어 있는지 검사
        if PROT_PATHS_RE.search(seg_raw):
            # 메뉴 파일(menus.md, menus.tsv)은 grep 허용
            if "menus.md" in seg_raw or "menus.tsv" in seg_raw:
                cleaned = re.sub(r"[^ \t]*menus\.(md|tsv)", "", seg_raw)
                if not PROT_PATHS_RE.search(cleaned):
                    continue

            # grep / rg인 경우
            if tool in ("grep", "rg"):
                # 문맥 옵션(-A, -B, -C, --context)이 있거나 색인 화면 파일인 경우 차단
                has_ctx = bool(re.search(r"(-[a-zA-Z]*[ABC][0-9]*|--(after|before)?-?context)", seg_mask))
                is_idx_screen = "docs/as-is/" in seg_raw
                if has_ctx or is_idx_screen:
                    trig = seg_raw.splitlines()[0][:80]
                    return True, trig, read_reason
                continue

            # 그 외 cat/sed/head/tail/less/more/awk/bat은 차단
            trig = seg_raw.splitlines()[0][:80]
            return True, trig, read_reason

    return False, "", ""


def main() -> None:
    raw_input = sys.stdin.read()
    try:
        data = json.loads(raw_input)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command", "")
    blocked, trigger, reason = inspect_command(cmd)
    if blocked:
        prefix = "⚠ 이 명령은 실행되지 않았습니다(앞 명령 포함).\n"
        msg = f"{prefix}[차단 원인: {trigger}] {reason}" if trigger else f"{prefix}{reason}"
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": msg,
            }
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
