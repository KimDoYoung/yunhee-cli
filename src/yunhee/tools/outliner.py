import re
from pathlib import Path

from yunhee.tools.base import ToolResult

MAX_OUTLINE_CHARS = 30000

NOT_JAVA_METHOD = {
    "if", "for", "while", "switch", "catch", "synchronized", "return",
    "new", "else", "try", "do", "super", "this", "throw", "assert",
    "case",
}

JAVA_MODIFIERS = {
    "public", "protected", "private", "static", "final", "abstract",
    "default", "synchronized", "native", "transient", "volatile", "strictfp",
}

JAVA_TYPE_KEYWORDS = {"record", "class", "interface", "enum", "new"}


def strip_code(text: str, is_ts: bool = False) -> tuple[str, str]:
    """줄 번호를 유지하면서 주석과 문자열을 제거한다.
    
    반환:
        no_comment: 주석만 공백으로 치환 (문자열 보존)
        bare: 주석과 문자열 모두 공백으로 치환
    """
    no_comment: list[str] = []
    bare: list[str] = []
    i, n = 0, len(text)

    while i < n:
        c = text[i]
        # 한 줄 주석
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blanks = " " * (j - i)
            no_comment.append(blanks)
            bare.append(blanks)
            i = j
        # 여러 줄 주석
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank = re.sub(r"[^\n]", " ", text[i:j])
            no_comment.append(blank)
            bare.append(blank)
            i = j
        # TSX 템플릿 리터럴 (`...`)
        elif is_ts and c == "`":
            j = i + 1
            while j < n and text[j] != "`":
                if text[j] == "\\":
                    j += 2
                else:
                    j += 1
            j = min(j + 1, n)
            part = text[i:j]
            no_comment.append(part)
            bare.append("`" + re.sub(r"[^\n]", " ", part[1:-1]) + "`" if len(part) >= 2 else part)
            i = j
        # 일반 문자열 ("..." 또는 '...')
        elif c in ("\"", "'"):
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                else:
                    j += 1
            j = min(j + 1, n)
            part = text[i:j]
            no_comment.append(part)
            bare.append(c + " " * (j - i - 2) + c if j - i >= 2 else part)
            i = j
        else:
            no_comment.append(c)
            bare.append(c)
            i += 1

    return "".join(no_comment), "".join(bare)


def paren_end(text: str, open_paren: int, open_ch: str = "(", close_ch: str = ")") -> int:
    """중첩 괄호를 계산하여 닫는 괄호의 인덱스를 찾는다."""
    depth = 0
    i = open_paren
    n = len(text)
    while i < n:
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def split_top_level(text: str, delim: str = ",") -> list[str]:
    """중첩 괄호() 및 제네릭<> 안의 구분자는 건너뛰고 최상위 구분자 기준으로 분리한다."""
    parts = []
    cur = []
    p_depth = 0  # (), []
    g_depth = 0  # <>
    for c in text:
        if c in "([":
            p_depth += 1
        elif c in ")]":
            p_depth = max(0, p_depth - 1)
        elif c == "<":
            g_depth += 1
        elif c == ">":
            g_depth = max(0, g_depth - 1)
        elif c == delim and p_depth == 0 and g_depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(c)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _clean_java_param(param_str: str) -> str:
    """파라미터 문자열에서 주석/애너테이션/final을 정리하고 '타입 파라미터명'을 남긴다."""
    p = re.sub(r"\s+", " ", param_str).strip()
    if not p:
        return ""
    # 애너테이션 제거
    p = re.sub(r"@[A-Za-z0-9_]+(?:\([^)]*\))?\s*", "", p).strip()
    # final 제거
    if p.startswith("final "):
        p = p[6:].strip()
    return p


def _find_top_level_semi(bare: str, start: int, end: int) -> int:
    """괄호 밖의 최상위 세미콜론 위치를 찾는다. 없으면 -1."""
    p_depth = 0
    for idx in range(start, min(end, len(bare))):
        c = bare[idx]
        if c in "([{":
            p_depth += 1
        elif c in ")]}":
            p_depth = max(0, p_depth - 1)
        elif c == ";" and p_depth == 0:
            return idx
    return -1


def _outline_java(content: str) -> list[str]:
    no_comment, bare = strip_code(content, is_ts=False)
    results: list[tuple[int, str]] = []

    # 1. 애너테이션 탐색
    anno_pat = re.compile(
        r"@(?:RestController|Controller|Service|Repository|Component|Configuration|"
        r"RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|"
        r"Transactional|Override|Deprecated)\b"
    )

    annos: list[tuple[int, int, str]] = []  # (start_pos, line_num, anno_text)
    for m in anno_pat.finditer(bare):
        start_pos = m.start()
        end_pos = m.end()
        if end_pos < len(bare) and bare[end_pos] == "(":
            close = paren_end(bare, end_pos, "(", ")")
            end_pos = close + 1
        anno_text = no_comment[start_pos:end_pos].strip()
        anno_text = re.sub(r"\s+", " ", anno_text)
        annos.append((start_pos, line_of(bare, start_pos), anno_text))

    # 2. 클래스 / 인터페이스 / Enum / Record 탐색
    type_pat = re.compile(
        r"\b(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?"
        r"(class|interface|record|enum)\s+([A-Za-z0-9_]+)"
    )
    type_positions = []
    enum_const_ranges: list[tuple[int, int]] = []
    enum_constant_items: list[tuple[int, str]] = []

    for m in type_pat.finditer(bare):
        kind, name = m.group(1), m.group(2)
        pos = m.start(1)
        line_num = line_of(bare, pos)

        # 2-A. record: 구성요소(파라미터) 추출
        if kind == "record":
            after_name = bare[m.end(2):].lstrip()
            if after_name.startswith("("):
                open_p = bare.find("(", m.end(2))
                close_p = paren_end(bare, open_p, "(", ")")
                param_raw = no_comment[open_p + 1:close_p]
                param_list = split_top_level(param_raw, delim=",")
                clean_params = [_clean_java_param(p) for p in param_list if _clean_java_param(p)]
                components = ", ".join(clean_params)
                type_positions.append((pos, line_num, f"record {name}({components})"))
            else:
                type_positions.append((pos, line_num, f"record {name}"))

        # 2-B. enum: 상수 구간 탐색 및 요약
        elif kind == "enum":
            type_positions.append((pos, line_num, f"enum {name}"))
            open_brace = bare.find("{", m.end(2))
            if open_brace != -1:
                close_brace = paren_end(bare, open_brace, "{", "}")
                semi_pos = _find_top_level_semi(bare, open_brace + 1, close_brace)
                const_end = semi_pos if semi_pos != -1 else close_brace
                enum_const_ranges.append((open_brace + 1, const_end))

                # 상수 파싱
                const_raw = no_comment[open_brace + 1:const_end]
                # 최상위 콤마로 스플릿
                raw_entries = split_top_level(const_raw, delim=",")
                const_names = []
                first_const_pos = None
                for entry in raw_entries:
                    m_ident = re.search(r"\b([A-Za-z0-9_]+)\b", entry)
                    if m_ident:
                        c_name = m_ident.group(1)
                        if c_name not in NOT_JAVA_METHOD and c_name not in JAVA_MODIFIERS:
                            const_names.append(c_name)
                            if first_const_pos is None:
                                first_const_pos = open_brace + 1 + const_raw.find(c_name)

                if const_names:
                    n_const = len(const_names)
                    if n_const <= 8:
                        summary_str = ", ".join(const_names)
                    else:
                        summary_str = ", ".join(const_names[:8]) + f", ..., {const_names[-1]}"
                    const_line = line_of(bare, first_const_pos) if first_const_pos else line_num + 1
                    enum_constant_items.append((const_line, f"  constants({n_const}): {summary_str}"))

        else:
            type_positions.append((pos, line_num, f"{kind} {name}"))

    # 3. 메서드 탐색
    method_ident_pat = re.compile(r"\b([A-Za-z0-9_]+)\s*\(")
    method_candidates = []

    for m in method_ident_pat.finditer(bare):
        name = m.group(1)
        if name in NOT_JAVA_METHOD:
            continue

        name_start = m.start(1)

        # enum 상수 구간 내부는 메서드 후보에서 완전 제외
        if any(c_start <= name_start < c_end for c_start, c_end in enum_const_ranges):
            continue

        open_paren = m.end() - 1
        close_paren = paren_end(bare, open_paren, "(", ")")
        if close_paren >= len(bare):
            continue

        # 닫는 괄호 ')' 뒤 토큰 검사: 다음 non-whitespace가 '{' 또는 ';' 또는 throws ... { / ;
        after_paren = bare[close_paren + 1:].lstrip()
        if not after_paren:
            continue

        is_body_method = after_paren.startswith("{")
        is_interface_method = after_paren.startswith(";")
        is_throws_method = False

        if after_paren.startswith("throws"):
            rest = after_paren[6:].lstrip()
            m_th = re.match(r"[A-Za-z0-9_,\s.]*([{;])", rest)
            if m_th:
                delim = m_th.group(1)
                is_throws_method = True
                if delim == "{":
                    is_body_method = True
                else:
                    is_interface_method = True

        if not (is_body_method or is_interface_method or is_throws_method):
            continue

        # 이름 앞의 prefix 확인
        last_delim = max(
            bare.rfind(";", 0, name_start),
            bare.rfind("{", 0, name_start),
            bare.rfind("}", 0, name_start),
        )
        prefix_str = bare[last_delim + 1:name_start].strip()

        # prefix에 '=' 나 'return' 이 있으면 메서드 선언이 아님
        if "=" in prefix_str or "return" in prefix_str:
            continue

        # prefix에서 애너테이션(@...) 제거
        clean_prefix = re.sub(r"@[A-Za-z0-9_]+(?:\([^)]*\))?", "", prefix_str).strip()

        # prefix 토큰 검사: record, class, interface, enum, new 가 있으면 메서드가 아님!
        tokens = clean_prefix.split()
        if any(tok in JAVA_TYPE_KEYWORDS for tok in tokens):
            continue

        ret_type_tokens = [t for t in tokens if t not in JAVA_MODIFIERS]
        if ret_type_tokens:
            ret_type = "".join(ret_type_tokens)
        else:
            ret_type = ""

        # 파라미터 가공 (타입 + 이름 유지)
        param_raw = no_comment[open_paren + 1:close_paren]
        param_list = split_top_level(param_raw, delim=",")
        clean_params = [_clean_java_param(p) for p in param_list if _clean_java_param(p)]
        param_str = ", ".join(clean_params)

        line_num = line_of(bare, name_start)
        sig = f"{ret_type} {name}({param_str})".strip()

        body_end = close_paren
        if is_body_method:
            body_start = bare.find("{", close_paren)
            if body_start != -1:
                body_end = paren_end(bare, body_start, "{", "}")

        method_candidates.append({
            "name": name,
            "pos": name_start,
            "line_num": line_num,
            "sig": sig,
            "body_start": close_paren,
            "body_end": body_end,
        })

    # 익명 클래스 중첩 필터링 (top-level 메서드만)
    method_candidates.sort(key=lambda x: x["pos"])
    top_methods = []
    current_end = -1
    for mc in method_candidates:
        if mc["pos"] > current_end:
            top_methods.append(mc)
            current_end = mc["body_end"]

    # 4. 종합 조립
    items: list[tuple[int, str]] = []

    for pos, l_num, text in annos:
        items.append((l_num, f"{text}"))

    for pos, l_num, text in type_positions:
        items.append((l_num, f"{text}"))

    for l_num, text in enum_constant_items:
        items.append((l_num, text))

    for mc in top_methods:
        items.append((mc["line_num"], f"  {mc['sig']}"))

    items.sort(key=lambda x: x[0])

    seen = set()
    for l_num, text in items:
        is_indent = text.startswith("  ") or not any(text.startswith(k) for k in ("class", "interface", "record", "enum"))
        prefix = "  " if is_indent and not text.startswith("  ") else ""
        formatted = f"L{l_num:4d}: {prefix}{text}"
        if formatted not in seen:
            seen.add(formatted)
            results.append((l_num, formatted))

    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


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


def _clean_ts_params(param_str: str) -> str:
    """TS 파라미터에서 타입 정보를 포함하여 간결화."""
    p = re.sub(r"\s+", " ", param_str).strip()
    if not p:
        return ""
    parts = split_top_level(p, delim=",")
    cleaned = []
    for part in parts:
        cleaned.append(re.sub(r"\s+", " ", part).strip())
    return ", ".join(cleaned)


def _outline_typescript(content: str) -> list[str]:
    no_comment, bare = strip_code(content, is_ts=True)
    results: list[tuple[int, str]] = []

    # 1. export interface / type / class / enum
    type_pat = re.compile(r"\bexport\s+(?:default\s+)?(interface|type|class|enum)\s+([A-Za-z0-9_]+)")
    for m in type_pat.finditer(bare):
        kind, name = m.group(1), m.group(2)
        l_num = line_of(bare, m.start())
        results.append((l_num, f"export {kind} {name}"))

    # 2. export (async) function name<...>(...)
    func_pat = re.compile(r"\bexport\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)")
    for m in func_pat.finditer(bare):
        name = m.group(1)
        cursor = m.end()
        # 제네릭 <...> 확인
        rest = bare[cursor:].lstrip()
        generic_str = ""
        if rest.startswith("<"):
            angle_open = bare.find("<", cursor)
            angle_close = paren_end(bare, angle_open, "<", ">")
            if angle_close < len(bare):
                generic_str = re.sub(r"\s+", " ", no_comment[angle_open:angle_close + 1]).strip()
                cursor = angle_close + 1

        rest_after_generic = bare[cursor:].lstrip()
        if rest_after_generic.startswith("("):
            open_p = bare.find("(", cursor)
            close_p = paren_end(bare, open_p, "(", ")")
            raw_params = no_comment[open_p + 1:close_p]
            clean_params = _clean_ts_params(raw_params)
            l_num = line_of(bare, m.start())
            results.append((l_num, f"export function {name}{generic_str}({clean_params})"))

    # 3. export const Name: Type = ... (예: React.FC 컴포넌트)
    const_typed_pat = re.compile(
        r"\bexport\s+const\s+([A-Za-z0-9_]+)\s*:\s*([^=;{]+)\s*="
    )
    for m in const_typed_pat.finditer(bare):
        name = m.group(1)
        type_annot = re.sub(r"\s+", " ", m.group(2)).strip()
        l_num = line_of(bare, m.start())
        results.append((l_num, f"export const {name}: {type_annot}"))

    # 4. export const Name = (async)? <T,>?(params) => ... (화살표 함수, 제네릭 포함)
    const_arrow_pat = re.compile(
        r"\bexport\s+const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?"
    )
    for m in const_arrow_pat.finditer(bare):
        name = m.group(1)
        cursor = m.end()
        rest = bare[cursor:].lstrip()
        generic_str = ""
        if rest.startswith("<"):
            angle_open = bare.find("<", cursor)
            angle_close = paren_end(bare, angle_open, "<", ">")
            if angle_close < len(bare):
                generic_str = re.sub(r"\s+", " ", no_comment[angle_open:angle_close + 1]).strip()
                cursor = angle_close + 1

        rest_after_generic = bare[cursor:].lstrip()
        if rest_after_generic.startswith("("):
            open_p = bare.find("(", cursor)
            close_p = paren_end(bare, open_p, "(", ")")
            after = bare[close_p + 1:close_p + 50].lstrip()
            if "=>" in after:
                raw_params = no_comment[open_p + 1:close_p]
                clean_params = _clean_ts_params(raw_params)
                l_num = line_of(bare, m.start())
                gen_part = f"{generic_str}" if generic_str else ""
                results.append((l_num, f"export const {name} = {gen_part}({clean_params}) =>"))

    # 5. export const sysApi = { ... } (API 객체 리터럴 모듈)
    api_obj_pat = re.compile(
        r"\bexport\s+const\s+([A-Za-z0-9_]+)\s*=\s*\{"
    )
    for m in api_obj_pat.finditer(bare):
        obj_name = m.group(1)
        open_brace = m.end() - 1
        close_brace = paren_end(bare, open_brace, "{", "}")
        l_num = line_of(bare, m.start())
        results.append((l_num, f"export const {obj_name} = {{"))

        inside_bare = bare[open_brace + 1:close_brace]

        # prop_name: (async) (params) =>
        prop_pat = re.compile(r"\b([A-Za-z0-9_]+)\s*:\s*(?:async\s*)?\(")
        for pm in prop_pat.finditer(inside_bare):
            p_name = pm.group(1)
            p_open = open_brace + 1 + pm.end() - 1
            p_close = paren_end(bare, p_open, "(", ")")
            p_raw = no_comment[p_open + 1:p_close]
            p_clean = _clean_ts_params(p_raw)
            p_line = line_of(bare, open_brace + 1 + pm.start(1))
            results.append((p_line, f"  {p_name}: ({p_clean})"))

    # 줄 번호 순 정렬
    results.sort(key=lambda x: x[0])
    seen = set()
    out = []
    for l_num, text in results:
        formatted = f"L{l_num:4d}: {text}"
        if formatted not in seen:
            seen.add(formatted)
            out.append(formatted)
    return out


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
