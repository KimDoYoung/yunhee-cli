from yunhee.config import OLLAMA_MODEL
from yunhee.ollama_client import chat
from yunhee.tools.legacy_page import find_all_page_files, find_page_files
from yunhee.tools.mapper_verify import (
    check_staleness,
    extract_mapper_refs,
    verify_mapper_refs,
)

# ── 단일 패스(기본) ────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
아래는 legacy GWT/GXT 기반 AssetERP의 '{page_code}' 페이지를 구성하는 소스 파일 전체입니다.

--- 소스 파일 시작 ---
{files_block}
--- 소스 파일 끝 ---

지금부터가 진짜 지시사항입니다. 위 코드는 참고 자료일 뿐이니 절대 그대로 인용하거나 이어서 작성하지 마세요.
Spring Boot/React로 마이그레이션할 개발자가 원본 코드를 읽지 않고도 이 화면을 파악할 수 있도록,
아래 마크다운 형식 그대로 한글 요약만 작성하세요.

이벤트 및 서버 호출 항목은 반드시 실제 mapper XML의 namespace와 sql id를 `namespace.sqlId` 형식으로 적으세요.
예: `ast01_class_tree.selectByCompanyId`

## 화면 개요
(1~2문장)

## 주요 필드 / 그리드 컬럼
(bullet)

## 이벤트 및 서버 호출
(mapperName/sqlId 단위 bullet, 형식: `namespace.sqlId` — 추측 금지, 소스에 있는 것만)

## 연관 테이블
(mapper XML 기준 bullet)

## 핵심 비즈니스 로직
(bullet)
"""

# ── 2단계 요약 ────────────────────────────────────────────────────────────────

FILE_MINI_PROMPT_TEMPLATE = """\
아래는 AssetERP GWT/GXT 소스 파일 하나입니다.

--- {filename} ---
{content}
---

이 파일의 역할을 3줄 이내로 요약하세요.
mapper XML이면: namespace, 주요 sql_id 목록, 참조 테이블을 나열하세요.
Java 클래스이면: 클래스 역할, 주요 메서드명, 호출하는 mapper sqlId를 나열하세요.
추측하지 말고 코드에 있는 것만 적으세요.
"""

COMBINE_PROMPT_TEMPLATE = """\
아래는 AssetERP '{page_code}' 페이지를 구성하는 파일별 요약 목록입니다.

{mini_summaries_block}

위 내용을 종합해서 아래 마크다운 형식 그대로 한글 요약을 작성하세요.
이벤트 및 서버 호출 항목은 `namespace.sqlId` 형식으로 정확히 적으세요.

## 화면 개요
(1~2문장)

## 주요 필드 / 그리드 컬럼
(bullet)

## 이벤트 및 서버 호출
(mapperName/sqlId 단위 bullet, 형식: `namespace.sqlId`)

## 연관 테이블
(mapper XML 기준 bullet)

## 핵심 비즈니스 로직
(bullet)
"""

# ── grounding 교정 ────────────────────────────────────────────────────────────

GROUNDING_CORRECTION_TEMPLATE = """\
아래 요약에서 "이벤트 및 서버 호출" 항목 중 실제 mapper_index에 존재하지 않는 항목이 발견됐습니다.

존재하지 않는 항목:
{invalid_block}

원본 요약:
{summary}

위 요약에서 존재하지 않는 항목을 삭제하거나 실제 존재하는 것으로 교체하세요.
다른 섹션은 변경하지 말고, 형식도 그대로 유지하세요.
"""


def _build_invalid_block(invalid: list[tuple[str, str, list[str]]]) -> str:
    lines = []
    for mapper_name, sql_id, actual_ids in invalid:
        if actual_ids:
            actual_str = ", ".join(actual_ids[:10])
            lines.append(
                f"- `{mapper_name}.{sql_id}` (존재하지 않음)\n"
                f"  실제 존재하는 {mapper_name} sql_id: {actual_str}"
            )
        else:
            lines.append(
                f"- `{mapper_name}.{sql_id}` (mapper_name `{mapper_name}` 자체가 없음 — 환각)"
            )
    return "\n".join(lines)


def _grounding_pass(summary: str, model: str) -> tuple[str, list[tuple[str, str, list[str]]]]:
    """요약에서 mapper 참조를 추출해 검증하고 필요하면 qwen에게 교정 요청.

    반환: (교정된 요약, 발견된 invalid 목록)
    mapper_index 없으면 원본 요약 그대로 반환.
    """
    refs = extract_mapper_refs(summary)
    if not refs:
        return summary, []

    invalid = verify_mapper_refs(refs)
    if not invalid:
        return summary, []

    invalid_block = _build_invalid_block(invalid)
    correction_prompt = GROUNDING_CORRECTION_TEMPLATE.format(
        invalid_block=invalid_block,
        summary=summary,
    )
    corrected = chat(correction_prompt, model=model)
    return corrected, invalid


def _summarize_file_mini(filename: str, content: str, model: str) -> str:
    prompt = FILE_MINI_PROMPT_TEMPLATE.format(filename=filename, content=content)
    return chat(prompt, model=model)


def summarize_page(
    page_code: str,
    model: str = OLLAMA_MODEL,
    two_stage: bool = False,
    grounding: bool = True,
) -> str:
    """ASIS 페이지 소스를 찾아 qwen으로 요약한 마크다운을 반환한다.

    two_stage=True: 파일별 mini-summary → combine (전체 파일 반영, 느림).
    grounding=True: 요약 후 mapper_index로 환각 검증 및 교정 (DB 없으면 skip).
    """
    stale, stale_msg = check_staleness()

    if two_stage:
        result = find_all_page_files(page_code)
    else:
        result = find_page_files(page_code)

    if not result.ok:
        raise ValueError(result.error)

    if two_stage:
        mini_summaries = []
        for f in result.data:
            mini = _summarize_file_mini(f["path"], f["content"], model)
            mini_summaries.append(f"### {f['path']}\n{mini}")

        mini_summaries_block = "\n\n".join(mini_summaries)
        combine_prompt = COMBINE_PROMPT_TEMPLATE.format(
            page_code=page_code,
            mini_summaries_block=mini_summaries_block,
        )
        summary = chat(combine_prompt, model=model)
    else:
        files_block = "\n\n".join(
            f"--- {f['path']} ---\n{f['content']}" for f in result.data
        )
        prompt = PROMPT_TEMPLATE.format(page_code=page_code, files_block=files_block)
        summary = chat(prompt, model=model)

    grounding_notes: list[str] = []
    if grounding:
        summary, invalid = _grounding_pass(summary, model)
        if invalid:
            for mapper_name, sql_id, _ in invalid:
                grounding_notes.append(f"`{mapper_name}.{sql_id}` 환각 감지 → 교정됨")

    file_count = len(result.data)
    total_count_note = ""
    if two_stage:
        total_count_note = f" (전체 {file_count}개, 2단계 요약)"
    elif result.truncated:
        total_count_note = " (예산 초과로 일부 잘림 — `--two-stage` 권장)"

    meta_lines = [
        f"# {page_code} 요약\n",
        f"원본 파일 {file_count}개{total_count_note}:",
        *[f"- {f['path']}" for f in result.data],
    ]
    if stale and stale_msg:
        meta_lines.append(f"\n> ⚠️  {stale_msg}")
    if grounding_notes:
        meta_lines.append("\n> grounding 교정:")
        meta_lines.extend(f"> - {n}" for n in grounding_notes)
    meta_lines.append("\n---\n")

    return "\n".join(meta_lines) + summary
