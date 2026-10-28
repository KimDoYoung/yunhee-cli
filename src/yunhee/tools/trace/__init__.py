"""trace-* business exploration commands registry and stubs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from yunhee.tools.trace.render import TraceResult, limit, render
from yunhee.tools.trace.stub import format_trace_stub

SideOption = Annotated[
    str,
    typer.Option("--side", help="분석 대상 (asis, tobe, both)"),
]
FormatOption = Annotated[
    str,
    typer.Option("--format", "-o", help="출력 형식 (md 또는 json)"),
]
MaxOption = Annotated[
    int | None,
    typer.Option("--max", help="출력 항목 상한"),
]
TobeOption = Annotated[
    Path | None,
    typer.Option("--tobe", help="TOBE 프로젝트 루트 또는 frontend/src (기본: 작업 폴더)"),
]
SrcOption = Annotated[
    Path | None,
    typer.Option("--src", help="AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
]
SrcIndexOption = Annotated[
    Path | None,
    typer.Option("--src-index", help="index-src 색인 폴더 (기본: YUNHEE_SRC_INDEX_DIR 또는 docs/as-is/src)"),
]


def _emit(
    build: Callable[..., TraceResult | tuple[TraceResult, int]], side: str, fmt: str, max_n: int | None, src: Path | None, src_index: Path | None
) -> None:
    """색인을 읽어 결과를 만들고 출력한다. 모호한 대상은 종료 코드 2, 찾지 못하면 1.

    build가 `(결과, 종료 코드)`를 돌려주면 출력한 뒤 그 코드로 끝낸다 (trace-rule verify가 깨진 근거를 알릴 때).
    """
    from yunhee.tools.analysis.common import AmbiguousTargetError
    from yunhee.tools.trace.resolve import TargetNotFoundError, load_context

    try:
        ctx = load_context(side, src=src, src_index=src_index)
        built = build(ctx)
    except AmbiguousTargetError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    except TargetNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    result, code = built if isinstance(built, tuple) else (built, 0)
    typer.echo(render(limit(result, max_n), fmt))
    if code:
        raise typer.Exit(code)


def register_trace_commands(app: typer.Typer) -> None:
    """Register all 18 trace-* exploration commands on the main Typer app."""

    # -------------------------------------------------------------------------
    # 1. 탐색 계층 (Navigation / Exploration)
    # -------------------------------------------------------------------------

    @app.command(name="trace-map")
    def trace_map_cmd(
        domain: Annotated[str | None, typer.Option("--domain", "-d", help="특정 업무 영역 (예: sys, fnd, emp)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태 요약"""
        out = format_trace_stub(
            cmd_name="trace-map",
            desc="업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태 요약",
            params={"domain": domain},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-menu")
    def trace_menu_cmd(
        menu_path: Annotated[str | None, typer.Argument(help="메뉴 경로 또는 검색어 (예: '시스템관리 > 권한관리')")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API 추적"""
        out = format_trace_stub(
            cmd_name="trace-menu",
            desc="메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API 추적",
            params={"menu_path": menu_path},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-screen")
    def trace_screen_cmd(
        screen_id: Annotated[str, typer.Argument(help="화면 클래스명, 접두사, 또는 메뉴 번호 (예: Emp00_Tab_TransInfo, Emp00, #1029)")],
        class_name: Annotated[str | None, typer.Option("--class", "-c", help="하위 클래스의 UI·서비스 상세 (예: Emp02_TabPage_Others)")] = None,
        tobe: Annotated[Path | None, typer.Option("--tobe", help="TOBE 프로젝트 루트 또는 frontend/src (기본: 작업 폴더)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """화면 팩트 시트 (필드·라벨, 그리드 컬럼, 버튼, 이벤트, RPC/API, SQL, 테이블, DB 함수)"""
        from yunhee.tools.trace.screen import trace_screen

        _emit(lambda ctx: trace_screen(screen_id, ctx, class_name, tobe), side, format, max, src, src_index)

    # -------------------------------------------------------------------------
    # 2. 데이터 중심 계층 (Data Centric)
    # -------------------------------------------------------------------------

    @app.command(name="trace-table")
    def trace_table_cmd(
        table_name: Annotated[str, typer.Argument(help="테이블명 (예: sys06_menu) 또는 스키마.테이블")],
        stats: Annotated[bool, typer.Option("--stats", help="DB에 접속해 행 수를 조회 (읽기 전용)")] = False,
        db: Annotated[str | None, typer.Option("--db", help="스키마 스냅샷 이름 (기본: YUNHEE_SCHEMA_ENV)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """컬럼·코멘트, C/R/U/D SQL과 화면, 같은 이름의 컬럼을 가진 테이블, 행 수"""
        from yunhee.tools.trace.table import trace_table

        _emit(lambda ctx: trace_table(table_name, ctx, db, stats), side, format, max, src, src_index)

    @app.command(name="trace-column")
    def trace_column_cmd(
        col_ref: Annotated[str, typer.Argument(help="테이블.컬럼 (예: sys01_company.company_id)")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """컬럼 읽기/쓰기/WHERE 사용 SQL, 표시 화면 라벨, 값 분포"""
        out = format_trace_stub(
            cmd_name="trace-column",
            desc="이 컬럼을 읽는/쓰는/WHERE에 쓰는 SQL, 표시되는 화면 라벨, 값 분포",
            params={"col_ref": col_ref},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-code")
    def trace_code_cmd(
        code_group: Annotated[str, typer.Argument(help="코드 그룹명 또는 코드 ID (예: LinkCode, USE_YN)")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """공통 코드값·명칭, 사용처 (콤보, SQL 리터럴, Java/TS 상수 비교)"""
        out = format_trace_stub(
            cmd_name="trace-code",
            desc="코드값과 명칭, 사용처(콤보, SQL 리터럴, Java/TS 상수 비교)",
            params={"code_group": code_group},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-state")
    def trace_state_cmd(
        col_ref: Annotated[str, typer.Argument(help="테이블.컬럼 (예: apr01_appr.apr01_status_cd)")],
        tobe: TobeOption = None,
        db: Annotated[str | None, typer.Option("--db", help="스키마 스냅샷 이름 (기본: YUNHEE_SCHEMA_ENV)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """컬럼에 값을 쓰는 모든 INSERT/UPDATE의 대입 값과 WHERE 조건 (상태 전이 재료)"""
        from yunhee.tools.trace.state import trace_state

        _emit(lambda ctx: trace_state(col_ref, ctx, tobe, db), side, format, max, src, src_index)

    @app.command(name="trace-crud")
    def trace_crud_cmd(
        domain: Annotated[str | None, typer.Option("--domain", "-d", help="업무 영역 필터")] = None,
        screen: Annotated[str | None, typer.Option("--screen", "-s", help="화면 필터")] = None,
        table: Annotated[str | None, typer.Option("--table", "-t", help="테이블 필터")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """CRUD 매트릭스 도출"""
        out = format_trace_stub(
            cmd_name="trace-crud",
            desc="CRUD 매트릭스 도출",
            params={"domain": domain, "screen": screen, "table": table},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    # -------------------------------------------------------------------------
    # 3. 규칙 위치 계층 (Rule Location)
    # -------------------------------------------------------------------------

    @app.command(name="trace-flow")
    def trace_flow_cmd(
        screen_id: Annotated[str, typer.Argument(help="화면 클래스명, 접두사, 또는 메뉴 번호 (예: Emp00_Tab_TransInfo, #1029)")],
        event: Annotated[str | None, typer.Option("--event", "-e", help="이벤트 번호 (예: E3). 생략하면 이벤트 목록")] = None,
        class_name: Annotated[str | None, typer.Option("--class", "-c", help="하위 클래스의 이벤트 (예: Emp02_TabPage_Others)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """이벤트 하나의 끝까지 이어진 사슬: 이벤트 → 핸들러 → 서비스(RPC) → 서버 → SQL → 테이블"""
        from yunhee.tools.trace.flow import trace_flow

        _emit(lambda ctx: trace_flow(screen_id, ctx, event, class_name), side, format, max, src, src_index)

    @app.command(name="trace-branch")
    def trace_branch_cmd(
        target: Annotated[str, typer.Argument(help="화면 클래스명·메뉴 번호, 또는 mapper id (예: Emp00_Tab_TransInfo, #1029, emp00_trans_info.selectByText)")],
        tobe: Annotated[Path | None, typer.Option("--tobe", help="TOBE 프로젝트 루트 또는 frontend/src (기본: 작업 폴더)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """조건 지점 전체 목록 (이벤트 조건, if/switch/throw, 활성·표시 조건, <if test>, CASE WHEN, TSX 조건부 렌더링)"""
        from yunhee.tools.trace.branch import trace_branch

        _emit(lambda ctx: trace_branch(target, ctx, tobe), side, format, max, src, src_index)

    @app.command(name="trace-dblogic")
    def trace_dblogic_cmd(
        name: Annotated[str | None, typer.Argument(help="함수/프로시저/트리거 이름")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """DB 함수·프로시저·트리거 본문과 이를 호출하는 SQL"""
        out = format_trace_stub(
            cmd_name="trace-dblogic",
            desc="함수·프로시저·트리거 본문과 이를 호출하는 SQL",
            params={"name": name},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    # -------------------------------------------------------------------------
    # 4. ASIS↔TOBE 대조 계층 (Comparison)
    # -------------------------------------------------------------------------

    @app.command(name="trace-pair")
    def trace_pair_cmd(
        screen_id: Annotated[str, typer.Argument(help="ASIS 화면 클래스명, 접두사, 또는 메뉴 번호 (예: Emp00_Tab_TransInfo, #1029)")],
        tobe: TobeOption = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """ASIS↔TOBE 짝지어진 항목과 매칭 근거 (AS-IS 주석, 같은 테이블 조합, 같은 이름)"""
        from yunhee.tools.trace.pair import trace_pair

        _emit(lambda ctx: trace_pair(screen_id, ctx, tobe), "asis", format, max, src, src_index)

    @app.command(name="trace-diff")
    def trace_diff_cmd(
        target: Annotated[str, typer.Argument(help="화면 클래스명·메뉴 번호, 또는 ASIS mapper id (예: #1029, emp00_trans_info.selectByText)")],
        sql: Annotated[bool, typer.Option("--sql", help="SQL 정규화 diff")] = False,
        branch: Annotated[bool, typer.Option("--branch", help="분기 대응표")] = False,
        ui: Annotated[bool, typer.Option("--ui", help="UI 필드·버튼·이벤트 대응표")] = False,
        tobe: TobeOption = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """SQL 정규화 diff, 분기 대응표, UI 필드 대응표 (옵션을 하나도 안 주면 셋 다)"""
        from yunhee.tools.trace.diff import trace_diff

        _emit(lambda ctx: trace_diff(target, ctx, tobe, sql, branch, ui), "asis", format, max, src, src_index)

    @app.command(name="trace-gap")
    def trace_gap_cmd(
        domain: Annotated[str | None, typer.Option("--domain", "-d", help="업무 영역 (예: emp, sys, fnd). 생략하면 전체")] = None,
        tobe: TobeOption = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 전체"""
        from yunhee.tools.trace.gap import trace_gap

        _emit(lambda ctx: trace_gap(ctx, tobe, domain), "asis", format, max, src, src_index)

    # -------------------------------------------------------------------------
    # 5. 카탈로그 및 가이드 계층 (Catalog & Guide)
    # -------------------------------------------------------------------------

    @app.command(name="trace-rule")
    def trace_rule_cmd(
        action: Annotated[str, typer.Argument(help="동작 (add, list, show, update, verify)")],
        target: Annotated[str | None, typer.Argument(help="add·list: 대상 화면·클래스·mapper id / show·update·verify: 규칙 ID (예: R-001)")] = None,
        note: Annotated[str | None, typer.Option("--note", help="규칙 내용 또는 변경 사유")] = None,
        verdict: Annotated[str | None, typer.Option("--verdict", "-v", help="판정 (일치, 누락, 변경, 의도적 변경)")] = None,
        evidence: Annotated[list[str] | None, typer.Option("--evidence", "-E", help="근거 위치 (반복 가능): 파일:줄, 파일, mapper id")] = None,
        accept: Annotated[bool, typer.Option("--accept", help="verify R-NNN: MOVED·STALE 근거를 현재 내용으로 갱신")] = False,
        tobe: TobeOption = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """에이전트 규칙 저장·조회 (add/list/show/update) 및 근거 검증 (verify — 깨진 근거가 있으면 종료 코드 1)"""
        from yunhee.tools.trace.rule import run_rule

        _emit(lambda ctx: run_rule(action, target, ctx, tobe, note, verdict, evidence, accept), side, format, max, src, src_index)

    @app.command(name="trace-term")
    def trace_term_cmd(
        term: Annotated[str | None, typer.Argument(help="검색할 용어/라벨/컬럼명")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """용어 교차 참조 (화면 라벨 ↔ DB 컬럼 ↔ 공통 코드명)"""
        out = format_trace_stub(
            cmd_name="trace-term",
            desc="용어 교차 참조: 화면 라벨 ↔ 컬럼 ↔ 코드명",
            params={"term": term},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-doc")
    def trace_doc_cmd(
        domain: Annotated[str, typer.Argument(help="업무 영역 (예: sys, fnd, emp)")],
        tobe: TobeOption = None,
        db: Annotated[str | None, typer.Option("--db", help="스키마 스냅샷 이름 (기본: YUNHEE_SCHEMA_ENV)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
        src: SrcOption = None,
        src_index: SrcIndexOption = None,
    ) -> None:
        """카탈로그와 팩트를 신규 인원용 문서 골격으로 조립 (서술 자리는 `서술(에이전트)` 표지로 남김)"""
        from yunhee.tools.trace.doc import trace_doc

        _emit(lambda ctx: trace_doc(domain, ctx, tobe, db), side, format, max, src, src_index)

    @app.command(name="trace-guide")
    def trace_guide_cmd(
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """에이전트용 업무파악 워크플로우 지침"""
        out = format_trace_stub(
            cmd_name="trace-guide",
            desc="에이전트용 업무파악 워크플로우 지침 (agent-guide의 업무파악판)",
            params={},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)
