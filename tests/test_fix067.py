import ast
from pathlib import Path

from yunhee.tools.test.batch_compare import parse_tsv_line, run_batch_compare
from yunhee.tools.test.gen_mapper import _to_java_literal
from yunhee.tools.test.params import format_params_output, resolve_params_for_statement
from yunhee.tools.test.scenario_skel import generate_scenario_code
from yunhee.tools.test.signature import get_method_signature


def test_signature_basic():
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return
    sig = get_method_signature(
        "kr.co.kfs.asseterp.biz.emp.mapper.EmpDeductMapper",
        "insertAddDeductTypes",
        src_root=real_root,
    )
    assert sig is not None
    assert sig.param_map["deductId"].pg_type == "numeric"
    assert sig.param_map["startDate"].pg_type == "date"
    assert sig.param_map["itemTypeCodeName"].pg_type == "text"


def test_params_and_format():
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return
    xml_path = real_root / "backend/src/main/resources/mapper/EmpDeductMapper.xml"
    res = resolve_params_for_statement(f"{xml_path}#insertAddDeductTypes", company="28000")
    assert res.ok
    args_out = format_params_output(res.data, fmt="args")
    assert "-p companyId=28000" in args_out
    assert "-p deductId=" in args_out


def test_to_java_literal():
    assert _to_java_literal("Long", "28000") == "28000L"
    assert _to_java_literal("LocalDate", "2026-11-16") == 'LocalDate.parse("2026-11-16")'
    assert _to_java_literal("List<Long>", "123") == "List.of(123L)"
    assert _to_java_literal("String", "test") == '"test"'


def test_scenario_skel_code_and_ast():
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return
    res = generate_scenario_code("PAY-BZ-0005", src_root=real_root)
    assert res.ok
    code = res.data["code"]
    assert "def pay_bz_0005(emp):" in code
    # AST 검증
    parsed = ast.parse(code)
    assert isinstance(parsed, ast.Module)


def test_batch_compare_tsv_parse():
    sample = "정상조회\tGET /api/v1/sys/roles\tsys04_role.selectByName\troleNm=%\t--grid Sys04Grid"
    parsed = parse_tsv_line(sample)
    assert parsed is not None
    assert parsed["name"] == "정상조회"
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/api/v1/sys/roles"
    assert parsed["sql_id"] == "sys04_role.selectByName"
    assert parsed["params"]["roleNm"] == "%"
    assert parsed["grid"] == "Sys04Grid"


def test_batch_compare_execution(tmp_path: Path):
    tsv_content = (
        "# 이름\tMETHOD path\tAS-IS SQL ID\t파라미터\t옵션\n"
        "틀린SQL\tGET /api/v1/sys/roles\tsys04_role.wrong_sql_id\troleNm=%\t\n"
    )
    f = tmp_path / "test.tsv"
    f.write_text(tsv_content, encoding="utf-8")
    res = run_batch_compare(f, output_format="tsv")
    assert not res.ok  # 1건 fail
    assert res.data["fail_cnt"] == 1
    assert "틀린SQL\tfail" in res.data["tsv"]
