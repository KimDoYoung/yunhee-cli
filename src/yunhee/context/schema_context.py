"""페이지가 참조하는 테이블의 DBML 조각을 prepare 결과에 붙일 마크다운 섹션으로 만든다 (qwen 호출 없음)."""

from yunhee.tools.page_schema import page_tables
from yunhee.tools.schema_snapshot import load_snapshot, slice_tables


def page_schema_section(page_code: str, env_name: str) -> str:
    """mapper_index로 찾은 테이블을 스냅샷과 대조해 DBML로. 실패해도 예외 대신 안내 문구를 담은 섹션을 반환."""
    header = f"## 연관 테이블 스키마 (DBML, `{env_name}` 스냅샷)"

    tables = page_tables(page_code)
    if not tables.ok:
        return f"{header}\n\n> ⚠️  {tables.error}\n"
    snapshot = load_snapshot(env_name)
    if not snapshot.ok:
        return f"{header}\n\n> ⚠️  {snapshot.error}\n"

    result = slice_tables(snapshot.data, tables.data)
    info = result.data
    lines = [header, "", f"- 스냅샷 생성: {snapshot.data.get('generated_at', '?')}"]
    lines.append(f"- 포함: {', '.join(info['tables']) or '없음'}")
    if info["omitted"]:
        lines.append(f"- 예산 초과로 제외 (`yunhee table <이름>`으로 조회): {', '.join(info['omitted'])}")
    if info["missing"]:
        lines.append(f"- 스냅샷에 없음 (CTE 별칭 등 mapper 파싱 노이즈일 수 있음): {', '.join(info['missing'])}")
    if info["dbml"]:
        lines += ["", "```dbml", info["dbml"], "```"]
    return "\n".join(lines) + "\n"
