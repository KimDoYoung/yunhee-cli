"""AS-IS 버튼 레이블과 TOBE Button type 간 매핑 사전 및 TSV 로더."""

from pathlib import Path

from yunhee.config import WORK_DIR, YUNHEE_DIR


def find_button_types_path(custom_path: Path | str | None = None) -> Path | None:
    """버튼 타입 TSV 파일 경로를 우선순위대로 탐색하여 반환한다.

    탐색 우선순위:
    1. custom_path (CLI 옵션 --button-types 지정 시)
    2. WORK_DIR / docs / as-is / button-types.tsv (작업 프로젝트 최우선)
    3. WORK_DIR / docs / button-types.tsv
    4. YUNHEE_DIR / data / button-types.tsv (yunhee 공통 디렉토리)
    5. 패키지 내장 src/yunhee/data / button-types.tsv
    """
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p

    candidates = [
        WORK_DIR / "docs" / "as-is" / "button-types.tsv",
        WORK_DIR / "docs" / "button-types.tsv",
        YUNHEE_DIR / "data" / "button-types.tsv",
        Path(__file__).parent.parent.parent / "yunhee" / "data" / "button-types.tsv",
        Path(__file__).parent.parent / "data" / "button-types.tsv",
    ]

    for cand in candidates:
        if cand.is_file():
            return cand

    return None


def parse_button_types_tsv(tsv_path: Path) -> dict[str, str]:
    """TSV 파일에서 레이블 -> type 매핑 사전을 파싱한다.

    형식: <레이블>\\t<type> (주석 `#`, 빈 줄 무시)
    """
    mapping: dict[str, str] = {}
    if not tsv_path.is_file():
        return mapping
    try:
        content = tsv_path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if len(parts) >= 2:
                mapping[parts[0]] = parts[1]
    except OSError:
        return {}
    return mapping


def load_button_types(custom_path: Path | str | None = None) -> dict[str, str]:
    """TSV 파일을 탐색하고 로드하여 반환한다. 파일이 없으면 기본 내장 사전을 반환한다."""
    path = find_button_types_path(custom_path)
    if path:
        loaded = parse_button_types_tsv(path)
        if loaded:
            return loaded

    return {}


# 기본 매핑 (패키지 로드 시 기본 TSV 탐색하여 캐싱)
BUTTON_TYPE_MAP: dict[str, str] = load_button_types()
