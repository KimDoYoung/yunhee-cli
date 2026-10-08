"""분석 도구(analysis) 레지스트리 및 모듈 관리."""

from types import ModuleType
from typing import Any

from yunhee.tools.analysis import grid, method, model, run, screen, sql, tobe, ui

REGISTRY: dict[str, ModuleType] = {
    "method": method,
    "sql": sql,
    "model": model,
    "grid": grid,
    "screen": screen,
    "ui": ui,
    "tobe": tobe,
    "run": run,
}


def get_type_module(type_name: str) -> ModuleType | None:
    """유형 이름에 해당하는 분석 모듈을 반환한다."""
    return REGISTRY.get(type_name.lower())


def list_types() -> list[dict[str, Any]]:
    """지원하는 모든 분석 유형의 메타데이터 목록을 반환한다."""
    items = []
    for k, mod in REGISTRY.items():
        items.append({
            "name": getattr(mod, "NAME", k),
            "description": getattr(mod, "DESCRIPTION", ""),
            "target_help": getattr(mod, "TARGET_HELP", ""),
            "formats": getattr(mod, "FORMATS", ("md",)),
            "examples": getattr(mod, "EXAMPLES", []),
        })
    return items
