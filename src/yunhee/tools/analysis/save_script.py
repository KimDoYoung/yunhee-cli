"""서버 저장 메서드의 쓰기 SQL들을 순서대로 추출하여 실행 스크립트를 생성하는 도구."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.mybatis_render import get_all_statements
from yunhee.tools.as_is.mybatis_render import render as mr_render
from yunhee.tools.as_is.src_indexer import find_app, paren_end

NAME = "save-script"
DESCRIPTION = "서버 저장 메서드의 쓰기 SQL들을 파라미터 대입하여 단일 롤백 스크립트로 생성"
TARGET_HELP = "<ns.Class.method>"
FORMATS = ("sql", "md")
EXAMPLES = [
    "yunhee analysis save-script apr.Apr90_DisposalList.updateAppr --param disposalCode=20 --param confirmEmpId=1 --param companyId=28000 --param disposalListId=202512109205061 --param apprId=202508189001993",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    target = target.strip()
    if "." not in target:
        raise ValueError(f"올바른 형식(<패키지>.<클래스>.<메서드>)으로 입력하세요: {target}")

    parts = target.split(".")
    if len(parts) >= 3:
        pkg = ".".join(parts[:-2])
        cls_name = parts[-2]
        meth_name = parts[-1]
    else:
        pkg = ""
        cls_name, meth_name = parts[0], parts[1]

    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    app = find_app(src_root) or src_root

    # 클래스 파일 찾기
    cand_files: list[Path] = []
    if pkg:
        pkg_path = Path(*pkg.split("."))
        for base in [app / "server" / pkg_path, app / pkg_path]:
            f = base / f"{cls_name}.java"
            if f.is_file():
                cand_files.append(f)

    if not cand_files:
        for f in (app / "server").rglob(f"{cls_name}.java"):
            if "target" not in f.parts and f not in cand_files:
                cand_files.append(f)

    if not cand_files:
        raise ValueError(f"클래스 소스 파일을 찾을 수 없습니다: {cls_name}.java")

    java_file = cand_files[0]
    raw_java = java_file.read_text(encoding="utf-8", errors="replace")

    # mapperName 찾기
    m_mapper = re.search(r'String\s+mapperName\s*=\s*["\']([^"\']+)["\']', raw_java)
    if m_mapper:
        default_mapper_name = m_mapper.group(1)
    else:
        # 클래스명의 스네이크 케이스
        s = re.sub(r"(?<!^)(?<!_)(?=[A-Z])", "_", cls_name).lower()
        default_mapper_name = re.sub(r"_+", "_", s)

    # 메서드 블록 찾기
    from yunhee.tools.analysis.method import _find_method_blocks
    blocks = _find_method_blocks(raw_java, meth_name)
    if not blocks:
        raise ValueError(f"{cls_name}에서 메서드 '{meth_name}'을 찾을 수 없습니다.")

    _, _, _, body = blocks[0]

    # CLI 파라미터 파싱
    cli_params: dict[str, Any] = {}
    for p in opts.get("param", []):
        if "=" in p:
            k, v = p.split("=", 1)
            cli_params[k.strip()] = v.strip()

    # CLI branch 파싱
    cli_branches: dict[str, str] = {}
    for b in opts.get("branch", []):
        if "=" in b:
            k, v = b.split("=", 1)
            cli_branches[k.strip()] = v.strip()

    # 메서드 내부 변수 및 분기 분석
    statements = get_all_statements(src_root)

    return {
        "target": target,
        "class": cls_name,
        "method": meth_name,
        "java_file": java_file,
        "mapper_name": default_mapper_name,
        "body": body,
        "cli_params": cli_params,
        "cli_branches": cli_branches,
        "statements": statements,
    }


def render(obj: dict[str, Any], fmt: str = "sql", opts: dict[str, Any] | None = None) -> str:
    body = obj["body"]
    mapper_name = obj["mapper_name"]
    cli_params = dict(obj["cli_params"])
    cli_branches = dict(obj["cli_branches"])
    statements = obj["statements"]

    # disposalCode, confirmYn 등 파라미터 값 추정
    disposal_code = cli_branches.get("disposalCode") or cli_params.get("disposalCode", "")
    confirm_yn = "false" if disposal_code == "99" else "true"

    today_str = datetime.now(tz=UTC).date().isoformat()
    base_params = {
        "confirmYn": confirm_yn,
        "regDate": today_str,
        "confirmDate": cli_params.get("confirmDate") or today_str,
    }
    # empId, regEmpId 매핑
    if "confirmEmpId" in cli_params:
        base_params["empId"] = cli_params["confirmEmpId"]
        base_params["regEmpId"] = cli_params["confirmEmpId"]

    # 복합 파라미터 병합
    for k, v in cli_params.items():
        base_params[k] = v
    for k, v in cli_branches.items():
        base_params[k] = v

    # 루프 변수 분할 (예: disposalListId=1,2)
    loop_param_keys = [k for k, v in cli_params.items() if isinstance(v, str) and "," in v]
    num_iterations = 1
    if loop_param_keys:
        num_iterations = max(len(cli_params[k].split(",")) for k in loop_param_keys)

    lines = body.splitlines()
    in_if = False
    if_cond_matched = True

    rendered_sqls: list[str] = []

    # 쓰기 SQL 호출 패턴
    sql_call_re = re.compile(
        r'sqlSession\.(insert|update|delete)\s*\(\s*([^,\)]+)(?:,\s*([^,\)]+))?\s*\)'
    )

    for i in range(num_iterations):
        # 이번 반복의 파라미터 생성
        curr_params = dict(base_params)
        for k in loop_param_keys:
            parts = [s.strip() for s in cli_params[k].split(",")]
            if i < len(parts):
                curr_params[k] = parts[i]

        in_if = False
        if_cond_matched = True

        for line in lines:
            line_str = line.strip()

            # if 조건문 감지
            m_if = re.search(r'\bif\s*\(', line_str)
            if m_if:
                p_open = line_str.find("(", m_if.start())
                p_close = paren_end(line_str, p_open)
                cond = line_str[p_open + 1:p_close].strip() if p_close > p_open else line_str[p_open + 1:]
                in_if = True
                # 조건 판정: disposalCode.equals("20") 등
                m_eq = re.search(r'(\w+)\.equals\(\s*["\']([^"\']+)["\']\s*\)', cond)
                if m_eq:
                    var, val = m_eq.group(1), m_eq.group(2)
                    actual = curr_params.get(var) or cli_branches.get(var)
                    if_cond_matched = (str(actual) == val)
                else:
                    m_ne = re.search(r'(\w+)\s*==\s*["\']([^"\']+)["\']', cond)
                    if m_ne:
                        var, val = m_ne.group(1), m_ne.group(2)
                        actual = curr_params.get(var) or cli_branches.get(var)
                        if_cond_matched = (str(actual) == val)
                    else:
                        if_cond_matched = True

            # 중괄호 닫힘으로 if 종료 감지
            if in_if and "}" in line_str:
                in_if = False
                if_cond_matched = True

            if in_if and not if_cond_matched:
                continue

            # sqlSession 호출 검사
            m_call = sql_call_re.search(line_str)
            if m_call:
                _, target_expr, param_expr = m_call.group(1), m_call.group(2).strip(), (m_call.group(3) or "").strip()

                # SQL ID 복원
                target_sql = target_expr
                if "mapperName" in target_sql:
                    target_sql = target_sql.replace("mapperName", f'"{mapper_name}"')
                target_sql = target_sql.replace('"', '').replace("'", '').replace(" ", "").replace("+", "")

                # 단일 인자 모델 호출 매핑 (예: model.getApprId() -> apprId)
                call_params = dict(curr_params)
                if param_expr and ("getApprId" in param_expr or param_expr == "apprId") and "apprId" in curr_params:
                    call_params["apprId"] = curr_params["apprId"]

                try:
                    sql_text, _ = mr_render(target_sql, params=call_params, mode="params", statements=statements)
                    rendered_sqls.append(sql_text.strip().rstrip(";") + ";")
                except Exception as e:  # noqa: BLE001
                    rendered_sqls.append(f"-- SQL 렌더링 실패: {target_sql} ({e});")

        if not loop_param_keys:
            break

    header = "-- yunhee sql -f 로 --rollback 실행\n"
    return header + "\n\n".join(rendered_sqls) + "\n"
