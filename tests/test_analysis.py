"""yunhee analysis 도구 및 서브모듈 단위 테스트."""

import json
from pathlib import Path

import pytest

from yunhee.tools import analysis
from yunhee.tools.analysis import (
    method,
    run,
    tobe,
)
from yunhee.tools.analysis.common import AmbiguousTargetError


def test_registry_list_types():
    types_list = analysis.list_types()
    names = [t["name"] for t in types_list]
    for expected in ["method", "sql", "model", "grid", "screen", "ui", "tobe", "run"]:
        assert expected in names


def test_analysis_method_resolve_and_render(tmp_path: Path):
    src_dir = tmp_path / "src"
    client_dir = src_dir / "client" / "vi" / "emp"
    client_dir.mkdir(parents=True, exist_ok=True)

    java_file = client_dir / "Emp01_Tab.java"
    java_file.write_text("""
package test;

public class Emp01_Tab {
    public void retrieve() {
        if (selected == null) {
            new SimpleMessage("사원을 선택해주세요");
            return;
        }
        ServiceRequest req = new ServiceRequest("emp.Emp01.search");
        req.addParam("companyId", "1000");
    }

    public void retrieve(String text) {
        // overload
    }
}
""", encoding="utf-8")

    opts = {"src": src_dir}

    # 1. 모호한 타겟 -> AmbiguousTargetError (Exit 2 조건)
    with pytest.raises(AmbiguousTargetError) as exc_info:
        method.resolve("Emp01_Tab.retrieve", opts)
    assert len(exc_info.value.candidates) == 2

    # 2. 번호 선택 (#1)
    res = method.resolve("Emp01_Tab.retrieve#1", opts)
    assert res["cls"] == "Emp01_Tab"
    assert res["method"] == "retrieve"

    # 3. md 렌더링
    md_out = method.render(res, fmt="md")
    assert "Emp01_Tab.retrieve()" in md_out
    assert 'SimpleMessage "사원을 선택해주세요"' in md_out
    assert "emp.Emp01.search" in md_out

    # 4. code 렌더링
    code_out = method.render(res, fmt="code")
    assert "Emp01_Tab.java:" in code_out
    assert "public void retrieve() {" in code_out


def test_analysis_tobe_resolve_and_render(tmp_path: Path):
    tsx_file = tmp_path / "Sys01_Tab_Company.tsx"
    tsx_file.write_text("""
// 화면번호: SYS01
// AS-IS: Sys01_Tab_Company.java
import React, { useState } from 'react';

export const Sys01_Tab_Company: React.FC = () => {
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const crud = useGridCrud({
        idField: 'companyId',
        search: sysApi.getCompanies,
        save: sysApi.saveCompany,
    });

    // [E1] 조회 버튼 클릭
    const handleSearch = () => {
        sysApi.getCompanies();
    };

    return (
        <Splitter vertical>
            <Panel>
                <SingleGrid />
            </Panel>
            <Panel>
                <Tabs />
            </Panel>
        </Splitter>
    );
};
""", encoding="utf-8")

    res = tobe.resolve(str(tsx_file), {})
    assert len(res["files"]) == 1
    f_info = res["files"][0]
    assert any("Sys01_Tab_Company" in exp[0] for exp in f_info["exports"])
    assert any("useGridCrud" in h for h in f_info["hooks"])

    md_out = tobe.render(res, fmt="md")
    assert "Sys01_Tab_Company.tsx" in md_out
    assert "useGridCrud" in md_out
    assert "[E1] 조회 버튼 클릭" in md_out


def test_analysis_run_render_json_and_tests(tmp_path: Path):
    log_file = tmp_path / "run_test.log"
    log_content = """=== Command: ./gradlew test ===
=== Exit Code: 0 ===
--- STDOUT ---
{"errs": [], "msgs": ["성공"], "items": [1, 2, 3, 4, 5]}
--- STDERR ---
"""
    log_file.write_text(log_content, encoding="utf-8")

    obj = {
        "run_record": {
            "id": "run_01",
            "command": "./gradlew test",
            "exit_code": 0,
            "duration_ms": 1200,
            "log_path": str(log_file),
            "summary": "성공",
        },
        "log_path": log_file,
        "stdout": '{"errs": [], "msgs": ["성공"], "items": [1, 2, 3, 4, 5]}',
        "log_text": log_content,
    }

    # 1. --stdout
    out_stdout = run.render(obj, opts={"stdout": True})
    assert '{"errs": [], "msgs": ["성공"]' in out_stdout

    # 2. --json with keys
    out_json = run.render(obj, opts={"json": True, "keys": "errs,msgs,items"})
    data = json.loads(out_json)
    assert data["errs"] == []
    assert data["msgs"] == ["성공"]
    assert data["items"] == 5  # 길이를 요약
