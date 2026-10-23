"""
yunhee-cli Domain Helper Tools (Read-Only)
기존 CLI 서브커맨드 코드 자체를 일절 수정하지 않고,
이미 검증된 내부 함수(config, log_reader)를 읽기 전용으로 안전하게 소비하는 도구 어댑터.
"""

from __future__ import annotations

from yunhee import config


def lookup_config(key: str = "") -> str:
    """
    현재 yunhee의 환경 설정(작업 대상 폴더, ASIS 소스 폴더, DB 접속 정보 마스킹, Ollama URL, ChromaDB 등)을 확인합니다.
    key를 생략하면 전체 설정 요약을 반환하며, 특정 key(예: 'WORK_DIR', 'ASIS_SRC_DIR', 'CHROMA_HOST', 'LOCAL_DB')를 지정하면 해당 설정값만 반환합니다.
    """
    clean_key = key.strip()
    if clean_key:
        val = config.get_config_value(clean_key, raw=False)
        if val is not None:
            return f"{clean_key}: {val}"
        # 정규화된 키로 재탐색
        item = config.get_config_item(clean_key)
        if item:
            return f"{item.key}: {item.get_value(raw=False)}"
        return f"알 수 없는 설정 키입니다: '{clean_key}'. ('yunhee value --list' 참고)"

    # 전체 요약 반환
    lines = ["[yunhee 현재 환경 설정 요약]"]
    for k, v in config.summary().items():
        lines.append(f"  {k:<16} {v}")
    return "\n".join(lines)


def read_recent_errors(limit: int = 5) -> str:
    """
    서버 로그에서 최근 발생한 WARN 및 ERROR 로그들을 요약하여 확인합니다.
    """
    try:
        from yunhee.tools import log_reader

        summary = log_reader.get_errors_summary(limit=limit)
        if summary and summary.strip():
            return summary.strip()
        return "최근 서버 로그에서 감지된 WARN/ERROR 에러가 없습니다."
    except Exception as e:  # noqa: BLE001
        return f"로그 조회 중 오류가 발생했습니다: {e}"
