"""AS-IS GXT/DBML 마이그레이션 정적 색인 및 검증 도구 모음."""

from pathlib import Path

from yunhee.config import WORK_DIR


def find_repo_root(start: Path) -> Path | None:
    """start 디렉토리부터 상위로 올라가며 .git 디렉토리가 있는 저장소 루트를 찾는다."""
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return None


def find_as_is_dir(sub: str = "") -> Path:
    """AS-IS 산출물 디렉터리 경로를 스마트하게 결정한다.

    에이전트가 작업 중인 하위 디렉터리(예: OMS/)에서 실행하더라도,
    상위 프로젝트(repo root)의 docs/as-is/를 우선 감지하여 산출물이 분산되는 것을 방지한다.
    """
    cur = WORK_DIR.resolve()

    # 1. 상위 디렉터리들 중 docs/as-is 가 존재하는 디렉터리가 있는지 확인 (OMS/ -> ../docs/as-is)
    for p in cur.parents:
        cand = p / "docs" / "as-is"
        if cand.is_dir():
            return cand / sub if sub else cand

    # 2. Git repo root 확인
    repo_root = find_repo_root(cur)
    if repo_root and repo_root != cur:
        cand = repo_root / "docs" / "as-is"
        if cand.is_dir() or (repo_root / "docs").is_dir():
            return cand / sub if sub else cand

    # 3. 현재 WORK_DIR 기준
    base = WORK_DIR / "docs" / "as-is"
    return base / sub if sub else base
