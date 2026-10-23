"""
yunhee-cli Screen Scout & Migration Spec Generator
AS-IS GXT 화면 코드로부터 events, table, outline 정적 분석을 일괄 수행하여
종합 마이그레이션 기술 명세서(docs/migration/<화면>_spec.md)를 자동 생성하는 도구.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from yunhee import config

logger = logging.getLogger(__name__)


def find_screen_java_file(screen_code: str) -> Path | None:
    """ASIS 소스 루트에서 해당 화면 코드와 일치하는 대표 Java 파일을 찾습니다."""
    asis_dir = Path(config.ASIS_SRC_DIR)
    if not asis_dir.is_dir():
        return None

    norm = screen_code.strip().lower()

    # 1. 완벽 일치 우선 탐색 (예: Sys01_Company.java 또는 sys01_company.java)
    candidates: list[Path] = []
    for p in asis_dir.rglob("*.java"):
        stem_lower = p.stem.lower()
        if stem_lower == norm:
            return p
        if norm in stem_lower:
            candidates.append(p)

    if not candidates:
        return None

    # 2. _Tab_ 이 포함된 메인 탭 화면 우선
    tab_candidates = [p for p in candidates if "_tab_" in p.stem.lower()]
    if tab_candidates:
        return tab_candidates[0]

    return candidates[0]


def build_screen_spec_markdown(screen_code: str) -> tuple[str, Path]:
    """
    화면 코드를 바탕으로 events, table, outline 결과를 집약한 마크다운 문서를 생성하고
    docs/migration/<screen_name>_spec.md 에 저장한 뒤 (마크다운문자열, 파일경로)를 반환합니다.
    """
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    clean_code = screen_code.strip()
    java_file = find_screen_java_file(clean_code)

    screen_name = java_file.stem if java_file else clean_code

    sections: list[str] = [
        f"# 📋 마이그레이션 기술 명세서: {screen_name}",
        f"- 생성 일시: {now_str}",
        "- 타깃 아키텍처: Spring Boot 3.4 (Java 21) + React 19 (AG Grid 36 / Ant Design 5)",
    ]

    if java_file:
        sections.append(f"- AS-IS 소스 파일: `{java_file}`\n")
    else:
        sections.append(f"- AS-IS 소스 파일: (직접 매칭 파일 없음, 화면 코드: `{clean_code}`)\n")

    sections.append("---\n")

    # 1. Events, Grid Spec, Buttons 추출
    sections.append("## 1. UI 컴포넌트, 그리드 스펙 & 버튼 목록")
    if java_file and java_file.is_file():
        try:
            from yunhee.tools.as_is.events import (
                extract_buttons,
                extract_events_and_methods,
                extract_grid_spec,
                get_source_label,
                render_events_markdown,
            )

            text = java_file.read_text(encoding="utf-8", errors="replace")
            total_lines = text.count("\n") + 1
            file_label = get_source_label(java_file, total_lines)
            ev_list, method_list = extract_events_and_methods(text, file_path=java_file)
            grid_spec = extract_grid_spec(text, file_path=java_file)
            buttons = extract_buttons(text, events=ev_list, file_path=java_file)
            events_md = render_events_markdown(file_label, ev_list, method_list, grid_spec=grid_spec, buttons=buttons)
            sections.append(events_md)
        except Exception as e:  # noqa: BLE001
            sections.append(f"> ⚠ 이벤트 및 그리드 분석 실패: {e}\n")
    else:
        sections.append("> ⚠ AS-IS 소스 Java 파일을 찾을 수 없어 UI/이벤트 분석을 건너뜁니다.\n")

    sections.append("\n---\n")

    # 2. 연관 DB 테이블 스키마 (DBML) 추출
    sections.append("## 2. 연관 DB 테이블 스키마 (DBML)")
    try:
        from yunhee.tools.page_schema import page_tables
        from yunhee.tools.schema_snapshot import load_snapshot, slice_tables

        # 화면 코드(접두사 3~5글자) 기준 테이블 추출
        code_prefix = clean_code.split("_")[0]
        schema_res = page_tables(code_prefix)
        if schema_res.ok and schema_res.data:
            if isinstance(schema_res.data, list):
                snapshot = load_snapshot(config.SCHEMA_ENV)
                if snapshot.ok and snapshot.data:
                    sliced = slice_tables(snapshot.data, schema_res.data)
                    info = sliced.data
                    if info and info.get("dbml"):
                        sections.append("```dbml")
                        sections.append(info["dbml"].strip())
                        sections.append("```\n")
                    else:
                        sections.append(f"> 참조 테이블: {', '.join(schema_res.data)}\n")
                else:
                    sections.append(f"> 참조 테이블: {', '.join(schema_res.data)}\n")
            else:
                sections.append("```dbml")
                sections.append(str(schema_res.data).strip())
                sections.append("```\n")
        else:
            sections.append(f"> 연관 테이블 정보 없음: {schema_res.error or '조회 결과 없음'}\n")
    except Exception as e:  # noqa: BLE001
        sections.append(f"> ⚠ DB 테이블 스키마 조회 실패: {e}\n")

    sections.append("\n---\n")

    # 3. 소스 구조 (Outline) 추출
    sections.append("## 3. AS-IS 클래스 및 메서드 시그니처 (Outline)")
    if java_file and java_file.is_file():
        try:
            from yunhee.tools import outliner

            lines = outliner.outline_file(java_file)
            if lines:
                sections.append("```java")
                sections.extend(lines[:50])
                if len(lines) > 50:
                    sections.append(f"... (외 {len(lines) - 50}줄 생략)")
                sections.append("```\n")
            else:
                sections.append("> 추출된 시그니처가 없습니다.\n")
        except Exception as e:  # noqa: BLE001
            sections.append(f"> ⚠ Outline 파싱 실패: {e}\n")
    else:
        sections.append("> 소스 파일이 지정되지 않아 Outline을 생략합니다.\n")

    full_md = "\n".join(sections)

    # docs/migration/ 디렉터리에 저장
    out_dir = Path(config.WORK_DIR) / "docs" / "migration"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{screen_name}_spec.md"
    out_path.write_text(full_md, encoding="utf-8")

    return full_md, out_path


def export_spec_tool(target: str, format: str = "markdown") -> str:
    """
    에이전트가 호출 가능한 산출물 발간 도구.
    화면 코드나 마크다운 파일을 받아 명세서 마크다운을 작성하거나 Gotenberg PDF로 발간합니다.
    """
    from yunhee.agent.tools.ext_gotenberg import (
        convert_markdown_to_pdf,
        export_pdf_from_file,
    )

    clean_target = target.strip()
    is_pdf = format.lower().strip() == "pdf"

    # 기존 마크다운 파일 경로인 경우
    target_path = Path(clean_target).resolve()
    if target_path.is_file() and target_path.suffix.lower() == ".md":
        if not is_pdf:
            return f"지정한 마크다운 파일 확인: {target_path}"
        pdf_out = Path(config.WORK_DIR) / "docs" / "pdf" / f"{target_path.stem}.pdf"
        ok, msg = export_pdf_from_file(target_path, pdf_out)
        return msg if ok else f"PDF 변환 실패: {msg}"

    # 화면 코드인 경우
    try:
        md_content, spec_path = build_screen_spec_markdown(clean_target)
        if not is_pdf:
            return f"✔ 마크다운 명세서 작성 완료: {spec_path}"
        pdf_out = Path(config.WORK_DIR) / "docs" / "pdf" / f"{spec_path.stem}.pdf"
        ok, msg = convert_markdown_to_pdf(
            md_content,
            pdf_out,
            title=f"마이그레이션 기술 명세서: {spec_path.stem}",
        )
        return msg if ok else f"PDF 변환 실패: {msg}"
    except Exception as e:  # noqa: BLE001
        return f"명세서 작성 중 오류 발생: {e}"
