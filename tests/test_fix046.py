from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import api_client, outliner, page_style
from yunhee.tools.as_is import mapper_runner, sql_checker
from yunhee.tools.trace import crud as trace_crud_mod
from yunhee.tools.trace.screen import ScreenDoc
from yunhee.tools.trace.tobe import (
    ApiFn,
    Endpoint,
    MapperStatement,
    TobeIndex,
    TobeLayout,
    TsxInfo,
)

runner = CliRunner()


# ==============================================================================
# §1. api / compare -p %25 이중 인코딩 방지
# ==============================================================================


@pytest.mark.parametrize(
    ("raw_input", "expected_norm", "expected_encoded"),
    [
        ("%", "%", "%25"),
        ("%25", "%", "%25"),
        ("%2", "%2", "%252"),
        ("%ZZ", "%ZZ", "%25ZZ"),
        ("a%25b", "a%b", "a%25b"),
        ("한글", "한글", "%ED%95%9C%EA%B8%80"),
        ("김 철수&x", "김 철수&x", "%EA%B9%80%20%EC%B2%A0%EC%88%98%26x"),
    ],
)
def test_fix046_query_param_encoding_table(
    raw_input: str, expected_norm: str, expected_encoded: str
) -> None:
    assert api_client.normalize_query_param_value(raw_input) == expected_norm
    assert api_client.encode_query_param_value(raw_input) == expected_encoded


def test_fix046_query_param_raw_escape_hatch() -> None:
    # --raw-param(raw=True)이면 %25를 디코딩하지 않고 그대로 두어 %2525로 인코딩되게 한다
    assert api_client.normalize_query_param_value("%25", raw=True) == "%25"
    assert api_client.encode_query_param_value("%25", raw=True) == "%2525"


def test_fix046_request_api_normalizes_pct25(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_params: list[dict] = []

    def fake_request(method: str, url: str, **kwargs):
        captured_params.append(dict(kwargs.get("params") or {}))
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.text = '{"success": true, "data": [1, 2, 3, 4, 5]}'
        resp.json.return_value = {"success": True, "data": [1, 2, 3, 4, 5]}
        return resp

    monkeypatch.setattr(
        api_client, "resolve_user_credentials", lambda role: ("admin", "pw", {"company_id": 28000})
    )
    monkeypatch.setattr(
        api_client,
        "_load_session",
        lambda *a, **kw: {"cookies": {"JSESSIONID": "1"}, "headers": {}, "user_info": {"company_id": 28000}},
    )
    monkeypatch.setattr(api_client.httpx, "request", fake_request)

    res1 = api_client.request_api("GET", "v1/emp/benefits", params={"benefitCode": "%", "searchText": "김 철수&x"})
    res2 = api_client.request_api("GET", "v1/emp/benefits", params={"benefitCode": "%25", "searchText": "김 철수&x"})
    res3 = api_client.request_api("GET", "v1/emp/benefits", params={"benefitCode": "%25"}, raw_param=True)

    assert res1.ok and res2.ok and res3.ok
    assert captured_params[0] == {"benefitCode": "%", "searchText": "김 철수&x"}
    assert captured_params[1] == {"benefitCode": "%", "searchText": "김 철수&x"}
    assert captured_params[2] == {"benefitCode": "%25"}


def test_fix046_api_and_compare_help_mentions_like_percent() -> None:
    res_api = runner.invoke(cli.app, ["api", "--help"], env={"COLUMNS": "160"})
    assert res_api.exit_code == 0
    assert "LIKE용" in res_api.output
    assert "-p k=%" in res_api.output
    assert "--raw-param" in res_api.output

    res_cmp = runner.invoke(cli.app, ["compare", "--help"], env={"COLUMNS": "160"})
    assert res_cmp.exit_code == 0
    assert "LIKE용" in res_cmp.output
    assert "-p k=%" in res_cmp.output
    assert "--raw-param" in res_cmp.output


# ==============================================================================
# §2. sql-check --tobe record DTO 열 누락 오류 승격 및 <include> 프로퍼티 전개
# ==============================================================================


def _setup_tobe_project(tmp_path: Path) -> tuple[Path, Path]:
    java_root = tmp_path / "src" / "main" / "java" / "kr" / "co" / "kfs" / "dto"
    mapper_dir = tmp_path / "src" / "main" / "resources" / "mapper"
    java_root.mkdir(parents=True)
    mapper_dir.mkdir(parents=True)

    # 1. Java record DTO
    (java_root / "BenefitRes.java").write_text(
        """package kr.co.kfs.dto;
public record BenefitRes(Long benefitId, String accountName, String apprTitleName) {}
""",
        encoding="utf-8",
    )

    # 2. 일반 setter 클래스 DTO
    (java_root / "LegacyDto.java").write_text(
        """package kr.co.kfs.dto;
public class LegacyDto {
    private Long benefitId;
    private String accountName;
    public void setBenefitId(Long benefitId) { this.benefitId = benefitId; }
    public void setAccountName(String accountName) { this.accountName = accountName; }
}
""",
        encoding="utf-8",
    )
    return java_root, mapper_dir


def test_fix046_sql_check_tobe_record_vs_class(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, mapper_dir = _setup_tobe_project(tmp_path)
    monkeypatch.setattr(sql_checker, "explain", lambda sql, db, extra_env=None: None)

    # ① record + 열 부족 → ❌ 오류 및 ok=False
    (mapper_dir / "EmpBenefitMapper.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="kr.co.kfs.mapper.EmpBenefitMapper">
    <select id="selectByText" resultType="kr.co.kfs.dto.BenefitRes">
        SELECT 1 AS benefit_id, '품의' AS appr_title_name
    </select>
</mapper>
""",
        encoding="utf-8",
    )
    res_fail = sql_checker.check_tobe_sql(mapper_dir)
    assert res_fail.ok is False
    assert "selectByText ❌ record BenefitRes 열 누락: accountName" in res_fail.data["summary"]
    assert "Constructor auto-mapping" in res_fail.data["summary"]
    assert "NULL AS account_name" in res_fail.data["summary"]

    # ② record + 열 충분 (<sql>/<include> 및 property 포함, 남는 별칭 extra_col 무시) + ④ 스네이크/카멜 변환 → 통과
    (mapper_dir / "EmpBenefitMapper.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="kr.co.kfs.mapper.EmpBenefitMapper">
    <sql id="benefitColumns">
        1 AS benefit_id,
        NULL AS account_name,
        '품의' AS APPR_TITLE_NAME,
        999 AS extra_unused_col
    </sql>
    <sql id="wrappedQuery">
        SELECT <include refid="${cols}"/>
    </sql>
    <select id="selectByText" resultType="kr.co.kfs.dto.BenefitRes">
        SELECT <include refid="benefitColumns"/>
    </select>
    <select id="selectViaProp" resultType="kr.co.kfs.dto.BenefitRes">
        <include refid="wrappedQuery">
            <property name="cols" value="benefitColumns"/>
        </include>
    </select>
</mapper>
""",
        encoding="utf-8",
    )
    res_ok = sql_checker.check_tobe_sql(mapper_dir)
    assert res_ok.ok is True
    assert "selectByText ✅" in res_ok.data["summary"]
    assert "selectViaProp ✅" in res_ok.data["summary"]
    assert "⚠" not in res_ok.data["summary"]
    assert "미사용 별칭" not in res_ok.data["summary"]

    # ③ 일반(setter) 클래스 + 열 부족 → ⚠ 경고만 나오고 ok=True (종료코드 0)
    (mapper_dir / "EmpBenefitMapper.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="kr.co.kfs.mapper.EmpBenefitMapper">
    <select id="selectLegacy" resultType="kr.co.kfs.dto.LegacyDto">
        SELECT 1 AS benefit_id, 2 AS extra_col
    </select>
</mapper>
""",
        encoding="utf-8",
    )
    res_cls = sql_checker.check_tobe_sql(mapper_dir)
    assert res_cls.ok is True
    assert "selectLegacy ✅ ⚠ (필드 누락: accountName)" in res_cls.data["summary"]
    assert "미사용 별칭" not in res_cls.data["summary"]

    # 미해결 <include> → 거짓 ❌ 없이 '? include 미해결 — mapper-run으로 확인'
    (mapper_dir / "EmpBenefitMapper.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="kr.co.kfs.mapper.EmpBenefitMapper">
    <select id="selectUnresolved" resultType="kr.co.kfs.dto.BenefitRes">
        SELECT <include refid="missingFragment"/>, 1 AS benefit_id
    </select>
</mapper>
""",
        encoding="utf-8",
    )
    res_inc = sql_checker.check_tobe_sql(mapper_dir)
    assert res_inc.ok is True
    assert "include 미해결 — mapper-run으로 확인" in res_inc.data["summary"]
    assert "❌" not in res_inc.data["summary"]


# ==============================================================================
# §3. page-style 새 SID GGH 및 SG 선언 우선
# ==============================================================================


def test_fix046_page_style_ggh_and_sg_rules() -> None:
    assert "GGH" in page_style.DEFAULT_SIDS

    # ① 가로 Splitter + SearchBar(top_search) + 그리드 2개 → GGH
    sid1, _ = page_style.classify(
        {"grids": 2, "trees": 0, "layout": "horizontal", "top_search": True, "search": True}
    )
    assert sid1 == "GGH"

    # ② 세로 Splitter + 그리드 2개 → GG
    sid2, _ = page_style.classify(
        {"grids": 2, "trees": 0, "layout": "vertical", "top_search": True, "search": True}
    )
    assert sid2 == "GG"

    # ③ 가로 + 버튼 줄(SearchBar 아님) + 오른쪽 *_TabPage_* → GDP
    sid3, _ = page_style.classify(
        {
            "grids": 1,
            "trees": 0,
            "layout": "horizontal",
            "top_search": False,
            "search": False,
            "children": ["Sms02_TabPage_Detail"],
        }
    )
    assert sid3 == "GDP"

    # ④ 가로 + 트리 + 그리드 + top_search → SGT
    sid4, _ = page_style.classify(
        {"grids": 1, "trees": 1, "layout": "horizontal", "top_search": True, "search": True}
    )
    assert sid4 == "SGT"

    # ⑤ 선언 스타일: GGH + 가로 + 그리드 2개 → GGH
    sid5, _ = page_style.classify(
        {"grids": 2, "trees": 0, "layout": "horizontal", "top_search": False, "search": False},
        declared="GGH",
    )
    assert sid5 == "GGH"

    # ⑥ 선언 스타일: SG + 단일 셀 편집 그리드 + SearchBar (Pay50_Tab_ExpensePayWrite) → SG
    sid6, _ = page_style.classify(
        {
            "grids": 1,
            "trees": 0,
            "layout": "none",
            "top_search": True,
            "search": True,
            "editable_grid": True,
        },
        declared="SG",
    )
    assert sid6 == "SG"


# ==============================================================================
# §4. yunhee cat --head/--tail 및 yunhee grep
# ==============================================================================


def test_fix046_cat_head_tail_and_edge_cases(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("\n".join(f"line-{i}" for i in range(1, 31)), encoding="utf-8")

    # (a) --head 5 → 앞 5줄 + '… 25줄 더 있음 — 범위를 좁히세요'
    r_head = runner.invoke(cli.app, ["cat", str(sample), "--head", "5"])
    assert r_head.exit_code == 0
    assert "(L1-5) <==" in r_head.output
    assert "   5 | line-5" in r_head.output
    assert "line-6" not in r_head.output
    assert "… 25줄 더 있음 — 범위를 좁히세요" in r_head.output

    # (b) --tail 3 → 마지막 3줄 (L28-30)
    r_tail = runner.invoke(cli.app, ["cat", str(sample), "--tail", "3"])
    assert r_tail.exit_code == 0
    assert "(L28-30) <==" in r_tail.output
    assert "  28 | line-28" in r_tail.output
    assert "  30 | line-30" in r_tail.output
    assert "더 있음" not in r_tail.output

    # (c) 범위 + --tail 5 → 범위 안 마지막 5줄 (10-20 중 16-20)
    r_range_tail = runner.invoke(cli.app, ["cat", f"{sample}:10-20", "--tail", "5"])
    assert r_range_tail.exit_code == 0
    assert "(L16-20) <==" in r_range_tail.output
    assert "  16 | line-16" in r_range_tail.output
    assert "  20 | line-20" in r_range_tail.output

    # (h) --head 0, 파일 줄 수보다 큰 --head, --head와 --tail 동시 지정, 빈 파일, 개행 없는 파일
    r_head0 = runner.invoke(cli.app, ["cat", str(sample), "--head", "0"])
    assert r_head0.exit_code == 0
    assert "… 30줄 더 있음 — 범위를 좁히세요" in r_head0.output

    r_head_big = runner.invoke(cli.app, ["cat", str(sample), "--head", "100"])
    assert r_head_big.exit_code == 0
    assert "(L1-30) <==" in r_head_big.output
    assert "더 있음" not in r_head_big.output

    r_both = runner.invoke(cli.app, ["cat", str(sample), "--head", "5", "--tail", "5"])
    assert r_both.exit_code != 0
    assert "동시에 지정할 수 없습니다" in r_both.output

    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    r_empty = runner.invoke(cli.app, ["cat", str(empty_file), "--head", "5"])
    assert r_empty.exit_code == 0
    assert f"==> {empty_file} <==" in r_empty.output

    no_nl = tmp_path / "no_nl.txt"
    no_nl.write_bytes(b"first\nsecond")
    r_nonl = runner.invoke(cli.app, ["cat", str(no_nl), "--tail", "1"])
    assert r_nonl.exit_code == 0
    assert "   2 | second" in r_nonl.output


def test_fix046_grep_context_merge_and_cap(tmp_path: Path) -> None:
    target = tmp_path / "types.ts"
    lines = [f"line {i}" for i in range(1, 200)]
    lines[9] = "export interface BookFundFee {"  # L10
    lines[11] = "  bookFundFeeId: number; // match2"  # L12
    target.write_text("\n".join(lines), encoding="utf-8")

    # (d) -A 3
    r_after = runner.invoke(cli.app, ["grep", "interface BookFundFee", str(target), "-A", "3"])
    assert r_after.exit_code == 0
    out_lines = r_after.output.strip().splitlines()
    assert len(out_lines) == 4
    assert out_lines[0].endswith(":10: export interface BookFundFee {")
    assert out_lines[3].endswith(":13: line 13")

    # (h) -C 2 겹침 병합 (L10과 L12가 모두 매치될 때 L8~L14가 중복 없이 1번씩만 출력)
    r_overlap = runner.invoke(cli.app, ["grep", "BookFundFee|match2", str(target), "-C", "2"])
    assert r_overlap.exit_code == 0
    ov_lines = r_overlap.output.strip().splitlines()
    line_nums = [int(l.split(":")[1]) for l in ov_lines]
    assert line_nums == [8, 9, 10, 11, 12, 13, 14]

    # (e) 80줄 상한 및 '… 일치 N건 더 있음' (기본 --max 20 안에서도 -C 3 문맥 합산이 80줄을 넘으면 80줄에서 절단)
    spaced = tmp_path / "spaced.ts"
    spaced_lines = [
        f"import mod{i} from './mod{i}';" if i % 8 == 1 else f"const x{i} = {i};"
        for i in range(1, 200)
    ]
    spaced.write_text("\n".join(spaced_lines), encoding="utf-8")
    r_cap = runner.invoke(cli.app, ["grep", "import", str(spaced), "-C", "3"])
    assert r_cap.exit_code == 0
    cap_lines = r_cap.output.strip().splitlines()
    assert len(cap_lines) == outliner.GREP_MAX_LINES + 1
    assert cap_lines[-1].startswith("… 일치 ")
    assert cap_lines[-1].endswith("건 더 있음")

    # (f) 허용 범위 밖 경로 거절 (/etc/passwd)
    r_cat_etc = runner.invoke(cli.app, ["cat", "/etc/passwd"])
    assert r_cat_etc.exit_code != 0
    assert "허용 범위 밖 경로" in r_cat_etc.output

    r_grep_etc = runner.invoke(cli.app, ["grep", "root", "/etc/passwd"])
    assert r_grep_etc.exit_code != 0
    assert "허용 범위 밖 경로" in r_grep_etc.output


# ==============================================================================
# §5. trace-crud --screen 다른 화면 변환 표시 & mapper-run 파라미터 부족 결론
# ==============================================================================


def test_fix046_trace_crud_other_tobe_screens(tmp_path: Path) -> None:
    doc = ScreenDoc(
        name="Ast33_Tab_OfficeMngFundTrans",
        frontmatter={"shared_links": ["Act02_Grid_JournalFix"]},
    )
    layout = TobeLayout(
        root=tmp_path,
        frontend=tmp_path / "frontend/src",
        api_dir=tmp_path / "frontend/src/api",
        pages_dir=tmp_path / "frontend/src/pages",
        java_dir=tmp_path / "backend/src/main/java",
        mapper_dir=tmp_path / "backend/src/main/resources/mapper",
    )
    idx = TobeIndex(layout=layout)
    idx.tsx["Act02_Grid_JournalFix"] = TsxInfo(
        name="Act02_Grid_JournalFix",
        file="Act02_Grid_JournalFix.tsx",
        header_menu_nos=[],
        as_is_file="",
        api_calls=[("actApi", "searchJournalLines")],
        grid_cols=[],
        buttons=[],
        impl_events=set(),
        skipped_events=set(),
    )
    idx.tsx["Act02_Grid_History"] = TsxInfo(
        name="Act02_Grid_History",
        file="Act02_Grid_History.tsx",
        header_menu_nos=[],
        as_is_file="",
        api_calls=[("actApi", "searchHistory")],
        grid_cols=[],
        buttons=[],
        impl_events=set(),
        skipped_events=set(),
    )
    idx.api_fns[("actApi", "searchHistory")] = ApiFn(
        obj="actApi",
        name="searchHistory",
        verb="GET",
        url="/api/v1/act/history",
        file="act.ts",
        line=1,
    )
    ep = Endpoint(
        verb="GET",
        path="/api/v1/act/history",
        controller="ActController",
        method="history",
        file="ActController.java",
        line=1,
        service_calls=[("service", "history")],
    )
    idx.endpoints.append(ep)
    idx.service_fields["ActController"] = {"service": "ActService"}
    from yunhee.tools.trace.tobe import ServiceMethod

    idx.services[("ActService", "history")] = ServiceMethod(
        service="ActService",
        name="history",
        file="ActService.java",
        line=1,
        mapper_calls=[("mapper", "selectHistory")],
    )
    idx.mapper_fields["ActService"] = {"mapper": "ActMapper"}
    st = MapperStatement(
        namespace="kr.co.kfs.ActMapper",
        id="selectHistory",
        file="ActMapper.xml",
        line=1,
        kind="select",
    )
    idx.statements[st.key] = st
    ops_by_stmt = {st.key: {"ast01_class_tree": {"R"}}}

    other_tobe = trace_crud_mod._other_tobe_screens(
        doc, {"Ast33_Tab_OfficeMngFundTrans"}, idx, ops_by_stmt
    )
    lines = trace_crud_mod._compare(
        {"ast01_class_tree": {"R"}, "unconverted_tbl": {"R"}},
        {},
        other_tobe=other_tobe,
    )
    joined = "\n".join(lines)
    assert "ast01_class_tree: ASIS R / TOBE -  (다른 화면에 있음: Act02_Grid_JournalFix, Act02_Grid_History)" in joined
    assert "unconverted_tbl: ASIS R / TOBE -  ⚠ TOBE에 없음" in joined


def test_fix046_mapper_run_missing_params_conclusion(tmp_path: Path) -> None:
    mapper_file = tmp_path / "TestMapper.xml"
    mapper_file.write_text(
        """<mapper namespace="kr.co.kfs.TestMapper">
    <update id="updateFee">
        UPDATE test_tbl SET fee = #{r.fee}, note = #{r.note}, title = #{r.title} WHERE id = #{id}
    </update>
</mapper>""",
        encoding="utf-8",
    )
    res = mapper_runner.run_mapper_statement(
        f"{mapper_file}#updateFee", params={"id": "1"}, rollback=True
    )
    assert res.ok is False
    assert res.error is not None
    last_line = res.error.strip().splitlines()[-1]
    assert last_line.startswith("❌ 파라미터 부족 (3건):")
    assert "r.fee" in last_line
