"""분석 도구(analysis) 공통 유틸리티 및 예외 정의."""

import re
import sys
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.as_is import find_as_is_dir


class AmbiguousTargetError(Exception):
    """대상이 모호하여 후보 중 하나를 선택해야 할 때 발생 (Exit 2)."""

    def __init__(self, candidates: list[str], target: str = "") -> None:
        self.candidates = candidates
        self.target = target
        msg = f"대상이 모호합니다: '{target}' (후보 {len(candidates)}개)\n" + "\n".join(
            f"  {i + 1} · {c}" for i, c in enumerate(candidates)
        ) + "\n다시 실행할 때 '#번호'를 붙이거나 세부 옵션을 지정하세요."
        super().__init__(msg)


def resolve_as_is_paths(
    src: Path | None = None,
    src_index: Path | None = None,
) -> tuple[Path | None, Path | None]:
    """AS-IS 소스 루트 및 색인 디렉터리를 우선순위에 따라 결정한다 (A-0 규칙 5).

    1. 인자 (-s / --src, --src-index)
    2. .yunhee.toml [as_is] src, src_index
    3. config.ASIS_SRC_DIR 및 find_as_is_dir("src")
    """
    toml_as_is = config.TOML_CONFIG.get("as_is", {})

    # 1. src_root
    final_src: Path | None = None
    if src:
        final_src = Path(src)
    elif toml_as_is.get("src"):
        final_src = Path(toml_as_is["src"])
    elif config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        final_src = config.ASIS_SRC_DIR
    elif (config.WORK_DIR / "src").is_dir():
        final_src = config.WORK_DIR

    # 2. src_index
    final_index: Path | None = None
    if src_index:
        final_index = Path(src_index)
    elif toml_as_is.get("src_index"):
        final_index = Path(toml_as_is["src_index"])
    else:
        # 워크스페이스 내 docs/as-is/src 확인
        cand_work = config.WORK_DIR / "docs" / "as-is" / "src"
        if cand_work.is_dir():
            final_index = cand_work
        else:
            cand = find_as_is_dir("src")
            if cand.is_dir():
                final_index = cand

    return final_src, final_index


def load_index_data(src_index_dir: Path | None = None, src_root: Path | None = None) -> dict[str, Any] | None:
    """_index.json 색인 데이터를 로드한다. 원본보다 오래되었으면 경고 출력 (A-9)."""
    if not src_index_dir or not src_index_dir.is_dir():
        return None

    idx_file = src_index_dir / "_index.json"
    if not idx_file.is_file():
        return None

    # mtime 검사
    if src_root and src_root.is_dir():
        try:
            idx_mtime = idx_file.stat().st_mtime
            # 최근 1단계 파일들 중 mtime 확인
            src_mtime = max((f.stat().st_mtime for f in src_root.iterdir()), default=0)
            if src_mtime > idx_mtime:
                sys.stderr.write("⚠ 색인이 오래됨 — yunhee index-src … 다시 실행\n")
        except OSError:
            pass

    import json

    try:
        return json.loads(idx_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


GRID_METHOD_NAME_PATTERN = r"(?:build\w*Grid\w*|getTreeGrid|getGroupGrid|getSumGrid|getAggregationGrid)"


def count_as_is_grids(text: str) -> tuple[int, bool]:
    r"""AS-IS 클래스 절 텍스트에서 그리드 수를 집계한다.

    1. 클래스 절 안의 `^- 그리드 \`` (또는 `^- 트리 \``/`- 트리`) 줄 수를 센다.
    2. Grid Spec의 `const build\w*Grid\w*\b` 또는 `getTreeGrid\b` 블록 수를 센다.
    3. 두 방법의 값이 다르면 큰 값을 쓰고 경고 플래그(True)를 반환한다.
    """
    bullet_matches = re.findall(r"^-\s*(?:그리드\s*`|트리\b)", text, re.MULTILINE)
    bullet_cnt = len(bullet_matches)

    # 불릿 라인(^- ...)에 포함된 메서드명 언급으로 인한 중복 카운트를 방지하기 위해 불릿 라인 제외
    non_bullet_text = re.sub(r"^-\s*.*$", "", text, flags=re.MULTILINE)
    code_cnt = len(re.findall(rf"\bconst\s+{GRID_METHOD_NAME_PATTERN}\b", non_bullet_text)) + len(
        re.findall(r"(?<!const\s)\b(?:getTreeGrid|GridGroupBuilder)\b", non_bullet_text)
    )

    if bullet_cnt > 0 and code_cnt > 0:
        if bullet_cnt == code_cnt:
            return bullet_cnt, False
        return max(bullet_cnt, code_cnt), True
    if bullet_cnt > 0:
        return bullet_cnt, False
    if code_cnt > 0:
        return code_cnt, False
    return 0, False


def count_tobe_grids(text: str) -> int:
    """TOBE TSX 텍스트에서 주석을 제외하고 그리드 컴포넌트 출현 횟수를 센다."""
    # 블록 주석 제거
    s = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # 한 줄 주석 제거
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
    matches = re.findall(r"<(?:BaseGrid|SingleGrid|MultiGrid|CellEditGrid|ModalEditGrid)\b", s)
    return len(matches)


def count_tobe_buttons(
    text: str,
    comp_config: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> int:
    """TOBE TSX 텍스트에서 주석을 제외하고 버튼 수를 센다.

    1. <Button ...> 태그 출현 횟수 (extra prop 내부의 <Button> 포함).
    2. comp_config 또는 .yunhee.toml [tobe.components]에 정의된 공통 컴포넌트 버튼 수 가산.
    3. 기본 규칙: <SearchBar ...>가 onSearch 속성을 가지면 조회 버튼 1개 가산.
       onReset만 있는 경우는 가산하지 않음 (+0).
    """
    # 블록 주석 제거
    s = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # 한 줄 주석 제거
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)

    # 1. 일반 <Button> 태그
    btn_count = len(re.findall(r"<Button\b", s))

    if comp_config is None and config is not None:
        comp_config = config.get("tobe", {}).get("components", {})
    if comp_config is None:
        from yunhee import config as app_cfg

        comp_config = app_cfg.TOML_CONFIG.get("tobe", {}).get("components", {})

    # 2. 컴포넌트별 설정 처리
    # 예: SearchBar = ["search"] 또는 CustomComp = 2
    searchbar_handled = False
    for comp_name, btn_spec in comp_config.items():
        if isinstance(btn_spec, list):
            n_btns = len(btn_spec)
        elif isinstance(btn_spec, int):
            n_btns = btn_spec
        else:
            n_btns = 0

        pattern = rf"<{comp_name}\b([\s\S]*?)(?:/>|>)"
        matches = list(re.finditer(pattern, s))
        if comp_name == "SearchBar":
            searchbar_handled = True
            for m in matches:
                attrs = m.group(1)
                if "onSearch" in attrs:
                    btn_count += n_btns
        else:
            btn_count += len(matches) * n_btns

    # 3. SearchBar 기본 처리 (설정에 SearchBar가 없는 경우)
    if not searchbar_handled:
        is_from_search = ("components/search" in s) or ("import " not in s)
        for m in re.finditer(r"<SearchBar\b([\s\S]*?)(?:/>|>)", s):
            attrs = m.group(1)
            if "onSearch" in attrs and is_from_search:
                btn_count += 1

    return btn_count

