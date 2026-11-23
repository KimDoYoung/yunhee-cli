"""test-compare: 조회 API vs AS-IS SQL 대조 일괄 시험 및 기계용(TSV/JUnit) 리포팅 도구."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from yunhee.tools.base import ToolResult
from yunhee.tools.comparator import compare_api_sql


@dataclass
class CompareItemResult:
    name: str
    method: str
    path: str
    sql_id: str
    status: str  # ok, fail, skip
    tobe_rows: int
    asis_rows: int
    memo: str
    duration: float = 0.0


def parse_tsv_line(line: str) -> dict[str, Any] | None:
    """이름\tMETHOD path\tAS-IS SQL ID\t파라미터\t옵션 한 줄 파싱."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    tokens = line.split("\t")
    if len(tokens) < 3:
        return None

    name = tokens[0].strip()
    method_path = tokens[1].strip()
    sql_id = tokens[2].strip()
    params_str = tokens[3].strip() if len(tokens) > 3 else ""
    opts_str = tokens[4].strip() if len(tokens) > 4 else ""

    mp_tokens = method_path.split(None, 1)
    if len(mp_tokens) == 2:
        method = mp_tokens[0].upper()
        path = mp_tokens[1]
    else:
        method = "GET"
        path = method_path

    # 파라미터 파싱
    params: dict[str, str] = {}
    if params_str:
        for k, v in parse_qs(params_str, keep_blank_values=True).items():
            params[k] = v[-1] if v else ""

    # 옵션 파싱 (예: --grid XxxGrid --total-sql Xxx.count)
    grid = None
    total_sql = None
    if opts_str:
        tokens_opt = opts_str.split()
        for i, opt in enumerate(tokens_opt):
            if opt == "--grid" and i + 1 < len(tokens_opt):
                grid = tokens_opt[i + 1]
            elif opt == "--total-sql" and i + 1 < len(tokens_opt):
                total_sql = tokens_opt[i + 1]

    return {
        "name": name,
        "method": method,
        "path": path,
        "sql_id": sql_id,
        "params": params,
        "grid": grid,
        "total_sql": total_sql,
    }


def run_batch_compare(
    tsv_path: Path,
    company: str | None = None,
    output_format: str = "tsv",
    out_dir: Path | None = None,
    db_name: str | None = None,
) -> ToolResult:
    """test-compare 진입 함수."""
    from yunhee import config

    db_name = db_name or config.DEFAULT_DB_NAME
    if not tsv_path.is_file():
        return ToolResult(ok=False, error=f"TSV 파일을 찾을 수 없습니다: {tsv_path}")

    lines = tsv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    items: list[dict[str, Any]] = []
    for line in lines:
        parsed = parse_tsv_line(line)
        if parsed:
            items.append(parsed)

    if not items:
        return ToolResult(ok=False, error=f"실행할 유효한 시험 항목이 없습니다: {tsv_path}")

    results: list[CompareItemResult] = []

    for item in items:
        t0 = time.time()
        try:
            res = compare_api_sql(
                method=item["method"],
                path=item["path"],
                sql_ref=item["sql_id"],
                api_params=item["params"],
                sql_params=item["params"],
                company=company,
                grid=item["grid"],
                sql_total_ref=item["total_sql"],
                db_name=db_name,
            )
            duration = time.time() - t0

            if not res.ok:
                results.append(
                    CompareItemResult(
                        name=item["name"],
                        method=item["method"],
                        path=item["path"],
                        sql_id=item["sql_id"],
                        status="fail",
                        tobe_rows=0,
                        asis_rows=0,
                        memo=res.error or "비교 실행 실패",
                        duration=duration,
                    )
                )
            else:
                data = res.data or {}
                tobe_rows = data.get("api_rows", data.get("tobe_rows", 0))
                asis_rows = data.get("sql_rows", data.get("asis_rows", 0))

                # 0=0은 skip(확인 못 함) 판정 (수정사항066 8절 원칙)
                if tobe_rows == 0 and asis_rows == 0:
                    status = "skip"
                    memo = "0=0 (확인 못 함)"
                elif data.get("rows_match", True) and not data.get("missing_cols"):
                    status = "ok"
                    memo = "일치"
                else:
                    status = "fail"
                    memo = data.get("summary", "결과 불일치").splitlines()[0]

                results.append(
                    CompareItemResult(
                        name=item["name"],
                        method=item["method"],
                        path=item["path"],
                        sql_id=item["sql_id"],
                        status=status,
                        tobe_rows=tobe_rows,
                        asis_rows=asis_rows,
                        memo=memo,
                        duration=duration,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            duration = time.time() - t0
            results.append(
                CompareItemResult(
                    name=item["name"],
                    method=item["method"],
                    path=item["path"],
                    sql_id=item["sql_id"],
                    status="fail",
                    tobe_rows=0,
                    asis_rows=0,
                    memo=str(exc),
                    duration=duration,
                )
            )

    ok_cnt = sum(1 for r in results if r.status == "ok")
    fail_cnt = sum(1 for r in results if r.status == "fail")
    skip_cnt = sum(1 for r in results if r.status == "skip")

    summary_counts = f"ok {ok_cnt} · fail {fail_cnt} · skip {skip_cnt}"

    # 1. JUnit XML 생성
    suite = ET.Element("testsuite")
    suite.set("name", "test-compare")
    suite.set("tests", str(len(results)))
    suite.set("failures", str(fail_cnt))
    suite.set("skipped", str(skip_cnt))
    suite.set("errors", "0")
    suite.set("time", f"{sum(r.duration for r in results):.3f}")

    for r in results:
        tc = ET.SubElement(suite, "testcase")
        tc.set("classname", "test-compare")
        tc.set("name", r.name)
        tc.set("time", f"{r.duration:.3f}")
        if r.status == "fail":
            fail_el = ET.SubElement(tc, "failure")
            fail_el.set("message", r.memo)
            fail_el.text = f"METHOD {r.method} {r.path}\nAS-IS {r.sql_id}\nTOBE {r.tobe_rows} rows / ASIS {r.asis_rows} rows\n{r.memo}"
        elif r.status == "skip":
            skip_el = ET.SubElement(tc, "skipped")
            skip_el.set("message", r.memo)

    junit_xml_str = ET.tostring(suite, encoding="utf-8").decode("utf-8")
    junit_xml_formatted = f'<?xml version="1.0" encoding="UTF-8"?>\n{junit_xml_str}'

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        xml_out_file = out_dir / "TEST-test-compare.xml"
        xml_out_file.write_text(junit_xml_formatted, encoding="utf-8")

    # 2. TSV 생성: 이름\tok|fail|skip\tTOBE행\tASIS행\t메모
    tsv_out_lines = ["name\tstatus\ttobe_rows\tasis_rows\tmemo"]
    for r in results:
        tsv_out_lines.append(f"{r.name}\t{r.status}\t{r.tobe_rows}\t{r.asis_rows}\t{r.memo}")
    tsv_formatted = "\n".join(tsv_out_lines)

    out_content = junit_xml_formatted if output_format == "junit" else tsv_formatted

    return ToolResult(
        ok=fail_cnt == 0,
        data={
            "summary": summary_counts + "\n" + out_content,
            "counts": summary_counts,
            "output": out_content,
            "ok_cnt": ok_cnt,
            "fail_cnt": fail_cnt,
            "skip_cnt": skip_cnt,
            "junit_xml": junit_xml_formatted,
            "tsv": tsv_formatted,
        },
        error=None if fail_cnt == 0 else f"{fail_cnt}건 실패",
    )
