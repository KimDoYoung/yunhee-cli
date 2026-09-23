from yunhee.config import OLLAMA_MODEL
from yunhee.ollama_client import chat
from yunhee.tools.legacy_page import find_page_files

PROMPT_TEMPLATE = """\
아래는 legacy GWT/GXT 기반 AssetERP의 '{page_code}' 페이지를 구성하는 소스 파일 전체입니다.

--- 소스 파일 시작 ---
{files_block}
--- 소스 파일 끝 ---

지금부터가 진짜 지시사항입니다. 위 코드는 참고 자료일 뿐이니 절대 그대로 인용하거나 이어서 작성하지 마세요.
Spring Boot/React로 마이그레이션할 개발자가 원본 코드를 읽지 않고도 이 화면을 파악할 수 있도록,
아래 마크다운 형식 그대로 한글 요약만 작성하세요.

## 화면 개요
(1~2문장)

## 주요 필드 / 그리드 컬럼
(bullet)

## 이벤트 및 서버 호출
(mapperName/sqlId 단위 bullet)

## 연관 테이블
(mapper XML 기준 bullet)

## 핵심 비즈니스 로직
(bullet)
"""


def summarize_page(page_code: str, model: str = OLLAMA_MODEL) -> str:
    """ASIS 페이지 소스를 찾아 qwen으로 요약한 마크다운을 반환한다."""
    result = find_page_files(page_code)
    if not result.ok:
        raise ValueError(result.error)

    files_block = "\n\n".join(f"--- {f['path']} ---\n{f['content']}" for f in result.data)
    prompt = PROMPT_TEMPLATE.format(page_code=page_code, files_block=files_block)
    summary = chat(prompt, model=model)

    meta = (
        f"# {page_code} 요약\n\n"
        f"원본 파일 {len(result.data)}개"
        + (" (일부 잘림, truncated)" if result.truncated else "")
        + ":\n"
        + "\n".join(f"- {f['path']}" for f in result.data)
        + "\n\n---\n\n"
    )
    return meta + summary
