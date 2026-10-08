"""분석 도구(analysis) 공통 유틸리티 및 예외 정의."""

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
        final_src = src
    elif toml_as_is.get("src"):
        final_src = Path(toml_as_is["src"])
    elif config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        final_src = config.ASIS_SRC_DIR
    elif (config.WORK_DIR / "src").is_dir():
        final_src = config.WORK_DIR

    # 2. src_index
    final_index: Path | None = None
    if src_index:
        final_index = src_index
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
