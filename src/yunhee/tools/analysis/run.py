"""실행 결과(stdout/json/tests) 분석 도구."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.store import run_tracker

NAME = "run"
DESCRIPTION = "실행 결과에서 필요한 값(stdout, json, tests) 추출 및 분석"
TARGET_HELP = "[last|<run_id>]"
FORMATS = ("md", "json")
EXAMPLES = [
    "yunhee analysis run last --stdout",
    "yunhee analysis run last --json --keys errs,msgs,roles,roleUsers",
    "yunhee analysis run last --tests",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """대상 실행 기록 및 로그 파일을 로드한다."""
    target_id = target.strip() if target else "last"

    if target_id == "last":
        run_record = run_tracker.get_last_run()
    else:
        run_record = run_tracker.get_run(target_id)

    if not run_record:
        raise ValueError(f"실행 기록을 찾을 수 없습니다: {target_id}")

    log_path_str = run_record.get("log_path") or run_record.get("log_file") or ""
    log_path = Path(log_path_str)
    log_text = ""
    if log_path.is_file():
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    # STDOUT 파싱
    stdout_text = ""
    if "--- STDOUT ---" in log_text:
        parts = log_text.split("--- STDOUT ---", 1)
        if len(parts) > 1:
            rest = parts[1]
            stdout_text = rest.split("--- STDERR ---", 1)[0].strip()
    else:
        stdout_text = log_text

    return {
        "run_record": run_record,
        "log_path": log_path,
        "stdout": stdout_text,
        "log_text": log_text,
    }


def _parse_tests(work_dir: Path, log_text: str) -> dict[str, Any]:
    """gradle/mvn 테스트 결과를 XML 또는 로그에서 파싱한다."""
    # 1. XML 탐색 (build/test-results/test/*.xml)
    xml_files = list(work_dir.glob("**/build/test-results/test/*.xml"))
    if not xml_files:
        xml_files = list(work_dir.glob("**/target/surefire-reports/*.xml"))

    if xml_files:
        total = 0
        failures = 0
        skipped = 0
        failed_classes = []

        for xf in xml_files:
            try:
                tree = ET.parse(xf)
                root = tree.getroot()
                t = int(root.attrib.get("tests", 0))
                f = int(root.attrib.get("failures", 0)) + int(root.attrib.get("errors", 0))
                s = int(root.attrib.get("skipped", 0))
                total += t
                failures += f
                skipped += s
                if f > 0:
                    cls_name = root.attrib.get("name", xf.stem)
                    failed_cases = []
                    for tc in root.findall("testcase"):
                        fail_node = tc.find("failure") or tc.find("error")
                        if fail_node is not None:
                            case_name = tc.attrib.get("name", "unknown")
                            failed_cases.append(f"{cls_name} > {case_name}")
                    if failed_cases:
                        failed_classes.extend(failed_cases)
                    else:
                        failed_classes.append(cls_name)
            except Exception:  # noqa: BLE001, S110
                pass

        return {
            "source": "xml",
            "total": total,
            "failures": failures,
            "skipped": skipped,
            "failed_cases": failed_classes,
        }

    # 2. 로그 정규식 탐색
    # Gradle: "76 tests completed, 0 failed, 0 skipped"
    m_gradle = re.search(r"(\d+)\s+tests? completed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?", log_text, re.IGNORECASE)
    if m_gradle:
        tot = int(m_gradle.group(1))
        fail = int(m_gradle.group(2))
        skip = int(m_gradle.group(3) or 0)
        return {"source": "log", "total": tot, "failures": fail, "skipped": skip, "failed_cases": []}

    # Maven: "Tests run: 76, Failures: 0, Errors: 0, Skipped: 0"
    m_mvn = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", log_text)
    if m_mvn:
        tot = int(m_mvn.group(1))
        fail = int(m_mvn.group(2)) + int(m_mvn.group(3))
        skip = int(m_mvn.group(4))
        return {"source": "log", "total": tot, "failures": fail, "skipped": skip, "failed_cases": []}

    return {"source": "none", "total": 0, "failures": 0, "skipped": 0, "failed_cases": []}


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    stdout_opt = opts.get("stdout", False)
    json_opt = opts.get("json", False)
    tests_opt = opts.get("tests", False)
    keys_filter = opts.get("keys")

    stdout_text = obj["stdout"]
    log_text = obj["log_text"]
    run_rec = obj["run_record"]

    # 1. --stdout
    if stdout_opt:
        return stdout_text

    # 2. --tests
    if tests_opt:
        test_info = _parse_tests(config.WORK_DIR, log_text)
        tot = test_info["total"]
        fail = test_info["failures"]
        skip = test_info["skipped"]
        failed_cases = test_info["failed_cases"]

        if fmt == "json":
            return json.dumps(test_info, ensure_ascii=False, indent=2)

        lines = [f"전체 {tot} · 실패 {fail} · 건너뜀 {skip}"]
        if failed_cases:
            lines.append("실패한 테스트:")
            for fc in failed_cases:
                lines.append(f"  ❌ {fc}")
        return "\n".join(lines)

    # 3. --json
    if json_opt:
        # 마지막 JSON 라인 탐색
        json_obj = None
        for line in reversed(stdout_text.splitlines()):
            line_s = line.strip()
            if line_s.startswith("{") and line_s.endswith("}"):
                try:
                    json_obj = json.loads(line_s)
                    break
                except json.JSONDecodeError:
                    continue

        if json_obj is None:
            return "{}"

        # keys 필터링
        filtered: dict[str, Any] = {}
        target_keys = [k.strip() for k in keys_filter.split(",")] if keys_filter else list(json_obj.keys())
        for k in target_keys:
            if k in json_obj:
                val = json_obj[k]
                # 배열 요약 (errs, msgs는 전체 유지, 그 외는 길이 + 앞3개)
                if isinstance(val, list) and k not in ("errs", "msgs", "errors", "messages"):
                    filtered[k] = len(val) if len(val) > 3 else val
                else:
                    filtered[k] = val

        return json.dumps(filtered, ensure_ascii=False)

    # 기본 요약
    r_id = run_rec.get("id") or run_rec.get("run_id") or "unknown"
    r_log = run_rec.get("log_path") or run_rec.get("log_file") or ""
    lines = [
        f"### Run {r_id} (`{run_rec['command']}`)",
        f"- **Exit Code**: {run_rec['exit_code']}",
        f"- **소요 시간**: {run_rec['duration_ms']}ms",
        f"- **로그 파일**: `{r_log}`",
    ]
    if run_rec.get("summary"):
        lines.append(f"- **요약**: {run_rec['summary']}")

    return "\n".join(lines)
