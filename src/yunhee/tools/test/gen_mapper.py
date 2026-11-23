"""test-gen-mapper: 매퍼 스모크 시험(JUnit5 @MybatisTest) 뼈대 자동 생성 도구."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.base import ToolResult
from yunhee.tools.test.params import resolve_params_for_statement
from yunhee.tools.test.signature import (
    parse_dto_fields,
    parse_mapper_java_file,
)


@dataclass
class StatementGenResult:
    method_name: str
    return_type: str
    is_disabled: bool
    disabled_reason: str
    args_code: str
    assert_code: str


@dataclass
class MapperGenResult:
    mapper_name: str
    domain: str
    java_file: Path
    xml_file: Path | None
    test_file_path: Path
    statements: list[StatementGenResult]
    is_existing: bool = False
    written: bool = False


def _to_java_literal(java_type: str, val: Any) -> str:
    """값을 Java 리터럴 표현식으로 변환."""
    if val is None or val == "?" or val == "":
        return "null"

    val_str = str(val).strip()

    if java_type in ("Long", "long"):
        digits = "".join(c for c in val_str if c.isdigit() or c == "-")
        return f"{digits or '0'}L"
    if java_type in ("Integer", "int", "Short", "short"):
        digits = "".join(c for c in val_str if c.isdigit() or c == "-")
        return digits or "0"
    if java_type in ("Double", "double"):
        return f"{val_str}D"
    if java_type == "BigDecimal":
        return f'new BigDecimal("{val_str}")'
    if java_type in ("Boolean", "boolean"):
        return "true" if val_str.lower() in ("true", "t", "y", "1") else "false"
    if java_type == "LocalDate":
        return f'LocalDate.parse("{val_str}")'
    if java_type == "LocalDateTime":
        if "T" not in val_str:
            val_str += "T00:00:00"
        return f'LocalDateTime.parse("{val_str}")'
    if java_type.startswith(("List<", "Collection<", "Set<")):
        # List.of(...)
        inner_m = java_type.split("<")[-1].rstrip(">")
        inner_lit = _to_java_literal(inner_m, val_str)
        return f"List.of({inner_lit})"

    # 기본 String
    if any(c in val_str for c in ("+", "?", ":", "(", ")")) or "null" in val_str:
        return '""'
    escaped = val_str.replace('"', '\\"')
    return f'"{escaped}"'


def _find_mapper_pairs(
    target_arg: str,
    src_root: Path | None = None,
) -> list[tuple[Path, Path | None]]:
    """target_arg (Mapper이름 또는 도메인명)에 해당하는 (Java파일, XML파일) 목록 반환."""
    roots = [
        src_root,
        getattr(config, "TOBE_SRC_DIR", None),
        config.WORK_DIR,
        Path.cwd(),
    ]
    base_java: Path | None = None
    for r in roots:
        if not r:
            continue
        c1 = r / "backend/src/main/java"
        c2 = r / "src/main/java"
        if c1.is_dir():
            base_java = c1
            break
        if c2.is_dir():
            base_java = c2
            break

    if not base_java:
        base_java = config.WORK_DIR

    mapper_files: list[Path] = []
    # 1. 단일 매퍼 지정 (예: AttCommuteMapper)
    clean_name = target_arg.replace(".java", "").replace(".xml", "")
    if clean_name.endswith("Mapper"):
        for f in base_java.rglob(f"{clean_name}.java"):
            mapper_files.append(f)
            break
    else:
        # 2. 도메인 지정 (예: att)
        domain_dir = base_java / "kr/co/kfs/asseterp/biz" / clean_name.lower() / "mapper"
        if domain_dir.is_dir():
            mapper_files = sorted(domain_dir.glob("*Mapper.java"))
        else:
            # 전체에서 biz/<domain>/mapper 탐색
            for d in base_java.rglob(clean_name.lower()):
                m_dir = d / "mapper"
                if m_dir.is_dir():
                    mapper_files.extend(sorted(m_dir.glob("*Mapper.java")))

    pairs: list[tuple[Path, Path | None]] = []
    for jf in mapper_files:
        # XML 탐색
        xml_name = f"{jf.stem}.xml"
        xml_file: Path | None = None
        for r in roots:
            if not r:
                continue
            for xf in r.rglob(xml_name):
                if xf.is_file():
                    xml_file = xf.resolve()
                    break
            if xml_file:
                break
        pairs.append((jf.resolve(), xml_file))

    return pairs


def generate_smoke_test_for_mapper(
    java_file: Path,
    xml_file: Path | None,
    company: str | None = None,
    out_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> MapperGenResult:
    """단일 매퍼에 대한 SmokeDbTest 클래스 분석 및 생성."""
    sigs = parse_mapper_java_file(java_file)
    mapper_name = java_file.stem
    # 도메인 추출: kr.co.kfs.asseterp.biz.<domain>.mapper -> <domain>
    parts = list(java_file.parts)
    domain = "biz"
    if "biz" in parts:
        b_idx = parts.index("biz")
        if b_idx + 1 < len(parts):
            domain = parts[b_idx + 1]

    # 테스트 파일 대상 경로
    base_out = out_dir or (config.WORK_DIR / "backend/src/test/java")
    if not base_out.is_absolute():
        base_out = (config.WORK_DIR / base_out).resolve()

    test_pkg_dir = base_out / "kr/co/kfs/asseterp/biz" / domain
    test_file_path = test_pkg_dir / f"{mapper_name}SmokeDbTest.java"

    is_existing = test_file_path.is_file()

    stmts_gen: list[StatementGenResult] = []

    for sid, sig in sigs.items():
        is_disabled = False
        dis_reason = ""

        # test-params 추론
        resolved_dict: dict[str, Any] = {}
        if xml_file and xml_file.is_file():
            target_str = f"{xml_file}#{sid}"
            p_res = resolve_params_for_statement(target_str, company=company)
            if p_res.ok and p_res.data and "params" in p_res.data:
                for p_item in p_res.data["params"]:
                    resolved_dict[p_item.name] = p_item.value

        # 인자별 코드 생성
        args_lits: list[str] = []
        missing_p: list[str] = []

        # 시그니처 파라미터 순회
        # 주의: record/DTO 파라미터는 객체 생성자로 채움
        for p in sig.params:
            if p.source and p.source.startswith("record:"):
                # DTO 구성요소 모으기
                dto_name = p.source.split(":")[-1]
                dto_fields = parse_dto_fields(dto_name, java_file)
                f_lits: list[str] = []
                for f in dto_fields:
                    val = resolved_dict.get(f.name, resolved_dict.get(f"{p.name}.{f.name}"))
                    if val is None or val == "?":
                        missing_p.append(f.name)
                        f_lits.append(_to_java_literal(f.java_type, "?"))
                    else:
                        f_lits.append(_to_java_literal(f.java_type, val))
                args_lits.append(f"new {dto_name}({', '.join(f_lits)})")
            elif p.source == "param":
                val = resolved_dict.get(p.name)
                if val is None or val == "?":
                    missing_p.append(p.name)
                    args_lits.append(_to_java_literal(p.java_type, "?"))
                else:
                    args_lits.append(_to_java_literal(p.java_type, val))

        if missing_p:
            is_disabled = True
            dis_reason = f"값을 못 정함: {', '.join(missing_p)} — test-params 참고"

        # 롤백 밖 커밋 의심 (REQUIRES_NEW 등)
        if "requires_new" in sid.lower() or "commit" in sid.lower():
            is_disabled = True
            dis_reason = "롤백 밖 커밋 의심"

        # Assert 문장
        ret = sig.return_type
        is_dml = any(sid.lower().startswith(pfx) for pfx in ("insert", "update", "delete"))
        if is_dml and ret in ("int", "Integer"):
            assert_code = "assertThat(n).isGreaterThanOrEqualTo(0);"
            call_code = f"int n = mapper.{sid}({', '.join(args_lits)});"
        elif ret == "void":
            call_code = f"mapper.{sid}({', '.join(args_lits)});"
            assert_code = "// void 실행 오류 없음 검증"
        elif ret in ("int", "Integer"):
            call_code = f"int n = mapper.{sid}({', '.join(args_lits)});"
            assert_code = "assertThat(n).isGreaterThanOrEqualTo(0);"
        elif ret in ("long", "Long") and is_dml:
            call_code = f"long n = mapper.{sid}({', '.join(args_lits)});"
            assert_code = "assertThat(n).isGreaterThanOrEqualTo(0L);"
        elif ret.startswith(("List<", "Collection<", "Set<")):
            call_code = f"var rows = mapper.{sid}({', '.join(args_lits)});"
            assert_code = "assertThat(rows).isNotNull();          // 스모크: 오류 없이 돈다"
        else:
            call_code = f"var res = mapper.{sid}({', '.join(args_lits)});"
            assert_code = "// 스모크: 오류 없이 돈다 (단일 값 조회, 없으면 null 허용)"

        stmts_gen.append(
            StatementGenResult(
                method_name=sid,
                return_type=ret,
                is_disabled=is_disabled,
                disabled_reason=dis_reason,
                args_code=call_code,
                assert_code=assert_code,
            )
        )

    # Java 소스 코드 렌더링
    today_str = datetime.date.today().strftime("%Y-%m-%d")  # noqa: DTZ011
    comp_tag = company or "28000"

    base_pkg = config.JAVA_BASE_PACKAGE
    src_lines = [
        f"package {base_pkg}.biz.{domain};",
        "",
        f"import {base_pkg}.biz.{domain}.mapper.{mapper_name};",
        "import org.junit.jupiter.api.Disabled;",
        "import org.junit.jupiter.api.Test;",
        "import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;",
        "import org.springframework.beans.factory.annotation.Autowired;",
        "import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;",
        "",
        "import java.math.BigDecimal;",
        "import java.time.LocalDate;",
        "import java.time.LocalDateTime;",
        "import java.util.List;",
        "",
        "import static org.assertj.core.api.Assertions.assertThat;",
        "",
        "@MybatisTest",
        "@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)",
        f"class {mapper_name}SmokeDbTest {{",
        f"    @Autowired {mapper_name} mapper;",
        "",
        f"    /** 자동 생성(yunhee test-gen-mapper {today_str}) — 값: test-params(회사 {comp_tag}). 손으로 고치면 맨 위 표시를 지운다. */",
    ]

    for sg in stmts_gen:
        if sg.is_disabled:
            src_lines.append(f'    @Disabled("{sg.disabled_reason}")')
        src_lines.append(f"    @Test void {sg.method_name}() {{")
        src_lines.append(f"        {sg.args_code}")
        src_lines.append(f"        {sg.assert_code}")
        src_lines.append("    }")
        src_lines.append("")

    src_lines.append("}")
    full_source = "\n".join(src_lines) + "\n"

    written = False
    if not dry_run and (not is_existing or force):
        test_pkg_dir.mkdir(parents=True, exist_ok=True)
        test_file_path.write_text(full_source, encoding="utf-8")
        written = True

    return MapperGenResult(
        mapper_name=mapper_name,
        domain=domain,
        java_file=java_file,
        xml_file=xml_file,
        test_file_path=test_file_path,
        statements=stmts_gen,
        is_existing=is_existing,
        written=written,
    )


def run_test_gen_mapper(
    target: str,
    company: str | None = None,
    out_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> ToolResult:
    """test-gen-mapper 진입 함수."""
    pairs = _find_mapper_pairs(target)
    if not pairs:
        return ToolResult(ok=False, error=f"대상 매퍼 또는 도메인을 찾을 수 없습니다: {target}")

    results: list[MapperGenResult] = []
    for jf, xf in pairs:
        res = generate_smoke_test_for_mapper(
            jf,
            xf,
            company=company,
            out_dir=out_dir,
            dry_run=dry_run,
            force=force,
        )
        results.append(res)

    total_mappers = len(results)
    total_stmts = sum(len(r.statements) for r in results)
    total_filled = sum(sum(1 for s in r.statements if not s.is_disabled) for r in results)
    total_disabled = total_stmts - total_filled
    dis_missing = sum(sum(1 for s in r.statements if s.is_disabled and "값을 못 정함" in s.disabled_reason) for r in results)
    dis_commit = sum(sum(1 for s in r.statements if s.is_disabled and "커밋 의심" in s.disabled_reason) for r in results)

    lines: list[str] = []
    for r in results:
        status_tag = ""
        if dry_run:
            status_tag = " (dry-run)"
        elif r.is_existing and not force:
            status_tag = " (이미 있음 — --force)"
        elif r.written:
            status_tag = " (생성됨)"

        lines.append(f"{r.mapper_name}SmokeDbTest.java{status_tag}:")
        for s in r.statements:
            if s.is_disabled:
                lines.append(f"  - {s.method_name} ⚠ Disabled ({s.disabled_reason})")
            else:
                lines.append(f"  - {s.method_name} ✅ 값 채움")

    lines.append("")
    summary_line = f"매퍼 {total_mappers} · 문장 {total_stmts} · 채움 {total_filled} · Disabled {total_disabled}(값 없음 {dis_missing}, 커밋 의심 {dis_commit})"
    lines.append(summary_line)

    return ToolResult(
        ok=True,
        data={
            "summary": "\n".join(lines),
            "total_mappers": total_mappers,
            "total_stmts": total_stmts,
            "total_filled": total_filled,
            "total_disabled": total_disabled,
            "results": results,
        },
    )
