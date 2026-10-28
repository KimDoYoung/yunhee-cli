"""trace-* business exploration commands registry and stubs."""

from __future__ import annotations

from typing import Annotated

import typer

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
        screen_id: Annotated[str, typer.Argument(help="화면 ID 또는 클래스명 (예: Fnd01_Tab_FundSearch, FND0101)")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """화면 팩트 시트 (필드·라벨, 그리드 컬럼, 버튼, 이벤트, RPC/API, SQL, 테이블, 코드)"""
        out = format_trace_stub(
            cmd_name="trace-screen",
            desc="화면 팩트 시트: 필드·라벨, 그리드 컬럼, 버튼, 이벤트, 호출 RPC/API, SQL, 테이블, 사용 코드 그룹",
            params={"screen_id": screen_id},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    # -------------------------------------------------------------------------
    # 2. 데이터 중심 계층 (Data Centric)
    # -------------------------------------------------------------------------

    @app.command(name="trace-table")
    def trace_table_cmd(
        table_name: Annotated[str, typer.Argument(help="테이블명 (예: sys01_company)")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """컬럼·코멘트, C/R/U/D SQL과 화면, 동명 컬럼 테이블, 행 수·최근 갱신일"""
        out = format_trace_stub(
            cmd_name="trace-table",
            desc="테이블 컬럼·코멘트, 이 테이블을 C/R/U/D 하는 SQL과 화면, 같은 이름 컬럼을 가진 테이블, 행 수·최근 갱신일",
            params={"table_name": table_name},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

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
        col_ref: Annotated[str, typer.Argument(help="테이블.컬럼 (예: fnd01_fund.stat_cd)")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """컬럼에 값을 쓰는 모든 INSERT/UPDATE 대입 값과 WHERE 조건 (상태 전이 재료)"""
        out = format_trace_stub(
            cmd_name="trace-state",
            desc="이 컬럼에 값을 쓰는 모든 INSERT/UPDATE, 대입 값, 그 SQL의 WHERE 조건 → 상태 전이를 그릴 재료",
            params={"col_ref": col_ref},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

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
        screen_id: Annotated[str, typer.Argument(help="화면 ID 또는 클래스명")],
        event: Annotated[str | None, typer.Option("--event", "-e", help="이벤트 번호 (예: E1, E3)")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """이벤트 하나의 끝까지 이어진 사슬: 버튼 → 핸들러 → RPC/API → 서비스 → mapper → SQL → 테이블"""
        out = format_trace_stub(
            cmd_name="trace-flow",
            desc="이벤트 하나의 끝까지 이어진 사슬: 버튼 → 핸들러 → RPC/API → 서비스 → mapper → SQL → 테이블",
            params={"screen_id": screen_id, "event": event},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-branch")
    def trace_branch_cmd(
        target: Annotated[str, typer.Argument(help="화면ID, 클래스명, 또는 mapper id")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """조건 지점 전체 목록 (if/switch/throw, validator, 버튼 활성, <if test>, CASE WHEN, TSX 조건부 렌더링)"""
        out = format_trace_stub(
            cmd_name="trace-branch",
            desc="조건 지점 전체 목록: if/switch/throw, validator, 버튼 활성 조건, <if test>, CASE WHEN, TSX disabled·조건부 렌더링",
            params={"target": target},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

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
        screen_id: Annotated[str, typer.Argument(help="화면 ID 또는 클래스명")],
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """ASIS↔TOBE 짝지어진 항목과 매칭 근거 (동일 mapper id, 테이블 조합, 명칭)"""
        out = format_trace_stub(
            cmd_name="trace-pair",
            desc="짝지어진 항목과 매칭 근거(같은 mapper id, 같은 테이블 조합, 같은 이름)",
            params={"screen_id": screen_id},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-diff")
    def trace_diff_cmd(
        target: Annotated[str, typer.Argument(help="화면ID, 클래스명, 또는 mapper id")],
        sql: Annotated[bool, typer.Option("--sql", help="SQL 정규화 diff")] = False,
        branch: Annotated[bool, typer.Option("--branch", help="분기 대응표")] = False,
        ui: Annotated[bool, typer.Option("--ui", help="UI 필드 대응표")] = False,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """SQL 정규화 diff, 분기 대응표, UI 필드 대응표"""
        out = format_trace_stub(
            cmd_name="trace-diff",
            desc="SQL 정규화 diff, 분기 대응표, UI 필드 대응표",
            params={"target": target, "sql": sql, "branch": branch, "ui": ui},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    @app.command(name="trace-gap")
    def trace_gap_cmd(
        domain: Annotated[str | None, typer.Option("--domain", "-d", help="업무 영역 필터")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """ASIS에만 있는 것, TOBE에만 있는 것, 미추적 지점 전체"""
        out = format_trace_stub(
            cmd_name="trace-gap",
            desc="ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 전체",
            params={"domain": domain},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

    # -------------------------------------------------------------------------
    # 5. 카탈로그 및 가이드 계층 (Catalog & Guide)
    # -------------------------------------------------------------------------

    @app.command(name="trace-rule")
    def trace_rule_cmd(
        action: Annotated[str, typer.Argument(help="동작 (add, list, show, update, verify)")],
        target: Annotated[str | None, typer.Argument(help="대상 화면ID 또는 규칙 ID")] = None,
        note: Annotated[str | None, typer.Option("--note", help="규칙 내용 또는 변경 사유")] = None,
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """에이전트 규칙 저장·조회 (add/list/show/update) 및 근거 검증 (verify)"""
        out = format_trace_stub(
            cmd_name="trace-rule",
            desc="규칙 저장·조회. 판정(일치/누락/변경/의도적 변경)과 사유, 근거 검증(verify)",
            params={"action": action, "target": target, "note": note},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

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
        side: SideOption = "both",
        format: FormatOption = "md",
        max: MaxOption = None,
    ) -> None:
        """카탈로그와 팩트를 신규 인원용 문서 골격으로 조립"""
        out = format_trace_stub(
            cmd_name="trace-doc",
            desc="카탈로그와 팩트를 신규 인원용 문서 골격으로 조립 (서술은 에이전트)",
            params={"domain": domain},
            side=side,
            fmt=format,
            max_n=max,
        )
        typer.echo(out)

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
