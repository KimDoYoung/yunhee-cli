import re
from pathlib import Path

from yunhee.tools.base import ToolResult

MAX_OUTLINE_CHARS = 30000


def _outline_java(content: str) -> list[str]:
    lines = content.splitlines()
    results = []
    i = 0
    pending_annotations = []

    anno_re = re.compile(
        r"^\s*(@(?:RestController|Controller|Service|Repository|Component|RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|Transactional)(?:\(.*?\))?)"
    )
    type_re = re.compile(
        r"^\s*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(class|interface|record|enum)\s+([A-Za-z0-9_]+)"
    )
    method_re = re.compile(
        r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?([A-Za-z0-9_<>, ?\[\]]+)\s+([A-Za-z0-9_]+)\s*\((.*?)\)"
    )

    while i < len(lines):
        line = lines[i]
        line_num = i + 1
        trimmed = line.strip()

        # 애너테이션 수집
        m_anno = anno_re.match(line)
        if m_anno:
            pending_annotations.append((line_num, trimmed))
            i += 1
            continue

        # 클래스 / 인터페이스 / 레코드 선언
        m_type = type_re.match(line)
        if m_type:
            for a_num, a_text in pending_annotations:
                results.append(f"L{a_num:4d}: {a_text}")
            pending_annotations = []
            kind, name = m_type.groups()
            results.append(f"L{line_num:4d}: {kind} {name}")
            i += 1
            continue

        # 메서드 선언
        m_method = method_re.match(line)
        if m_method:
            for a_num, a_text in pending_annotations:
                results.append(f"L{a_num:4d}:   {a_text}")
            pending_annotations = []
            ret_type, m_name, params = m_method.groups()
            # 파라미터가 길면 간소화
            clean_params = ", ".join(p.strip().split()[-1] if p.strip() else "" for p in params.split(","))
            results.append(f"L{line_num:4d}:   {ret_type} {m_name}({clean_params})")
            i += 1
            continue

        if not trimmed:
            pending_annotations = []
        i += 1

    return results


def _outline_mybatis_xml(content: str) -> list[str]:
    lines = content.splitlines()
    results = []

    mapper_re = re.compile(r'<\s*mapper\s+namespace=["\']([^"\']+)["\']', re.IGNORECASE)
    stmt_re = re.compile(
        r'<\s*(select|insert|update|delete|sql)\s+id=["\']([^"\']+)["\'](?:\s+resultType=["\']([^"\']+)["\'])?',
        re.IGNORECASE,
    )

    for i, line in enumerate(lines):
        line_num = i + 1
        m_map = mapper_re.search(line)
        if m_map:
            results.append(f"L{line_num:4d}: <mapper namespace=\"{m_map.group(1)}\">")

        for m_stmt in stmt_re.finditer(line):
            tag, stmt_id, res_type = m_stmt.groups()
            res_str = f" (resultType={res_type.split('.')[-1]})" if res_type else ""
            results.append(f"L{line_num:4d}:   {tag.lower()} #{stmt_id}{res_str}")

    return results


def _outline_typescript(content: str) -> list[str]:
    lines = content.splitlines()
    results = []

    type_re = re.compile(r"^\s*export\s+(?:default\s+)?(interface|type|class)\s+([A-Za-z0-9_]+)")
    func_re = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)")
    const_func_re = re.compile(
        r"^\s*export\s+const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\((.*?)\)(?:\s*:\s*([^=]+))?\s*=>"
    )

    for i, line in enumerate(lines):
        line_num = i + 1
        m_type = type_re.match(line)
        if m_type:
            kind, name = m_type.groups()
            results.append(f"L{line_num:4d}: export {kind} {name}")
            continue

        m_func = func_re.match(line)
        if m_func:
            name, params = m_func.groups()
            clean_params = ", ".join(p.strip().split(":")[0] if p.strip() else "" for p in params.split(","))
            results.append(f"L{line_num:4d}: export function {name}({clean_params})")
            continue

        m_const = const_func_re.match(line)
        if m_const:
            name, params, ret_type = m_const.groups()
            clean_params = ", ".join(p.strip().split(":")[0] if p.strip() else "" for p in params.split(","))
            ret_str = f": {ret_type.strip()}" if ret_type else ""
            results.append(f"L{line_num:4d}: export const {name} = ({clean_params}){ret_str}")
            continue

    return results


def _outline_python(content: str) -> list[str]:
    lines = content.splitlines()
    results = []
    class_re = re.compile(r"^\s*class\s+([A-Za-z0-9_]+)(?:\((.*?)\))?:")
    def_re = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z0-9_]+)\s*\((.*?)\)(?:\s*->\s*(.*?))?:")
    deco_re = re.compile(r"^\s*(@[A-Za-z0-9_.]+)")

    pending_deco = []
    for i, line in enumerate(lines):
        line_num = i + 1
        m_deco = deco_re.match(line)
        if m_deco:
            pending_deco.append((line_num, m_deco.group(1)))
            continue

        m_class = class_re.match(line)
        if m_class:
            for d_num, d_text in pending_deco:
                results.append(f"L{d_num:4d}: {d_text}")
            pending_deco = []
            name, bases = m_class.groups()
            base_str = f"({bases})" if bases else ""
            results.append(f"L{line_num:4d}: class {name}{base_str}")
            continue

        m_def = def_re.match(line)
        if m_def:
            for d_num, d_text in pending_deco:
                results.append(f"L{d_num:4d}:   {d_text}")
            pending_deco = []
            name, params, ret = m_def.groups()
            clean_params = ", ".join(p.strip().split(":")[0] if p.strip() else "" for p in params.split(","))
            ret_str = f" -> {ret.strip()}" if ret else ""
            results.append(f"L{line_num:4d}:   def {name}({clean_params}){ret_str}")
            continue

        if not line.strip():
            pending_deco = []

    return results


def outline_file(file_path: Path) -> list[str]:
    if not file_path.is_file():
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return []

    ext = file_path.suffix.lower()
    if ext == ".java":
        return _outline_java(content)
    elif ext == ".xml":
        return _outline_mybatis_xml(content)
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        return _outline_typescript(content)
    elif ext == ".py":
        return _outline_python(content)
    return []


def outline_path(path: Path | str, char_limit: int = MAX_OUTLINE_CHARS) -> ToolResult:
    target = Path(path).resolve()
    if not target.exists():
        return ToolResult(ok=False, error=f"경로가 존재하지 않습니다: {target}")

    sections = []
    total_chars = 0
    truncated = False

    if target.is_file():
        lines = outline_file(target)
        if not lines:
            text = f"// {target.name} (추출 가능한 시그니처 없음)"
        else:
            text = f"// {target.name}\n" + "\n".join(lines)
        return ToolResult(ok=True, data=text)

    # 디렉터리인 경우 주요 소스 파일 스캔
    target_exts = {".java", ".xml", ".ts", ".tsx", ".py"}
    files = sorted(
        [
            f
            for f in target.rglob("*")
            if f.is_file() and f.suffix.lower() in target_exts and not any(part.startswith(".") for part in f.parts)
        ]
    )

    if not files:
        return ToolResult(ok=True, data=f"// {target} 디렉터리에 분석 가능한 소스 파일이 없습니다.")

    for f in files:
        outline_lines = outline_file(f)
        if not outline_lines:
            continue

        rel_path = f.relative_to(target)
        section = f"### 📄 {rel_path}\n" + "\n".join(outline_lines) + "\n"
        if total_chars + len(section) > char_limit:
            sections.append(f"\n... [예산 {char_limit}자 초과로 이후 파일 생략]")
            truncated = True
            break
        sections.append(section)
        total_chars += len(section)

    data = "\n".join(sections)
    return ToolResult(ok=True, data=data, truncated=truncated)
