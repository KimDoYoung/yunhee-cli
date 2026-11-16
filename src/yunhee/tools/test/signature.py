"""Java 매퍼 시그니처 파서 및 캐시 모듈.

XML namespace로부터 대상 Java Mapper 인터페이스를 찾아
각 statement 메서드의 파라미터(이름, Java 타입, PostgreSQL 타입)를 정적으로 추출한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from yunhee import config

JAVA_TO_PG_TYPE: dict[str, str] = {
    "Long": "numeric",
    "long": "numeric",
    "Integer": "numeric",
    "int": "numeric",
    "BigDecimal": "numeric",
    "Double": "numeric",
    "double": "numeric",
    "Float": "numeric",
    "float": "numeric",
    "Short": "numeric",
    "short": "numeric",
    "String": "text",
    "LocalDate": "date",
    "LocalDateTime": "timestamp",
    "LocalTime": "time",
    "Boolean": "text",  # 이 DB는 불리언을 'true'/'false' 문자열 컬럼으로 씀
    "boolean": "text",
}

PRIMITIVE_OR_COMMON_TYPES = set(JAVA_TO_PG_TYPE.keys()) | {
    "Object",
    "void",
    "Void",
    "byte[]",
    "Byte[]",
    "Map",
    "HashMap",
    "List",
    "ArrayList",
    "Set",
    "HashSet",
    "Collection",
}


@dataclass
class ParamInfo:
    name: str
    java_type: str
    pg_type: str
    is_collection: bool = False
    source: str = ""  # 예: "param", "record:DeductRes", "dto"


@dataclass
class MethodSignature:
    name: str
    return_type: str
    params: list[ParamInfo] = field(default_factory=list)
    param_map: dict[str, ParamInfo] = field(default_factory=dict)
    line_no: int = 0
    java_file: Path | None = None


# 메모리 캐시: (file_path_str, mtime) -> dict[method_name, MethodSignature]
_SIG_CACHE: dict[tuple[str, float], dict[str, MethodSignature]] = {}


def strip_comments(text: str) -> str:
    """Java 소스에서 블록 주석 및 한 줄 주석을 공백 보존하며 제거."""
    def replacer(match: re.Match[str]) -> str:
        s = match.group(0)
        if s.startswith("/"):
            # 줄바꿈 유지
            return "\n" * s.count("\n")
        return s

    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE,
    )
    return re.sub(pattern, replacer, text)


def split_args(args_str: str) -> list[str]:
    """제네릭 <...> 괄호를 고려하여 쉼표로 인자 분리."""
    args: list[str] = []
    curr: list[str] = []
    depth = 0
    for char in args_str:
        if char == "<":
            depth += 1
            curr.append(char)
        elif char == ">":
            depth = max(0, depth - 1)
            curr.append(char)
        elif char == "," and depth == 0:
            token = "".join(curr).strip()
            if token:
                args.append(token)
            curr = []
        else:
            curr.append(char)
    last = "".join(curr).strip()
    if last:
        args.append(last)
    return args


def find_java_file_for_namespace(namespace: str, src_root: Path | None = None) -> Path | None:
    """MyBatis mapper namespace (예: kr.co.kfs.asseterp.biz.emp.mapper.EmpDeductMapper)에 해당하는 Java 파일 탐색."""
    rel_path = Path(*namespace.split(".")).with_suffix(".java")
    cand_roots: list[Path] = []

    if src_root:
        curr = src_root.parent if src_root.is_file() else src_root
        cand_roots.extend([
            curr,
            curr / "backend/src/main/java",
            curr / "src/main/java",
        ])
        for p in curr.parents:
            cand_roots.extend([
                p / "backend/src/main/java",
                p / "src/main/java",
                p / "main/java",
                p,
            ])
            if p.name in ("backend", "AssetERP", "framework-sprt"):
                break

    tobe = getattr(config, "TOBE_SRC_DIR", None)
    if tobe:
        cand_roots.extend([
            tobe / "backend/src/main/java",
            tobe / "src/main/java",
            tobe,
        ])

    cand_roots.extend([
        config.WORK_DIR / "backend/src/main/java",
        config.WORK_DIR / "src/main/java",
        config.WORK_DIR,
        Path.cwd() / "backend/src/main/java",
        Path.cwd() / "src/main/java",
        Path.cwd(),
    ])

    for root in cand_roots:
        if not root.is_dir():
            continue
        direct = root / rel_path
        if direct.is_file():
            return direct.resolve()
        cand2 = root / "kr/co/kfs/asseterp" / rel_path.name
        if cand2.is_file():
            return cand2.resolve()

    # 클래스명으로 파일 탐색
    class_name = namespace.split(".")[-1] + ".java"
    for root in cand_roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob(class_name):
                if p.is_file():
                    return p.resolve()
        except Exception:  # noqa: BLE001, S110
            pass

    return None


def _find_type_source_file(type_name: str, current_java_file: Path) -> Path | None:
    """Java 파일 내 import문 및 같은 패키지/프로젝트 내에서 type_name의 소스 파일 탐색."""
    # 같은 디렉터리
    cand = current_java_file.parent / f"{type_name}.java"
    if cand.is_file():
        return cand.resolve()

    # 상위 패키지 기준 dto 또는 model 하위
    # 예: current = .../biz/emp/mapper/EmpDeductMapper.java -> .../biz/emp/dto/
    biz_dir = current_java_file.parent.parent
    for sub in ("dto", "model", "record", "vo"):
        cand = biz_dir / sub / f"{type_name}.java"
        if cand.is_file():
            return cand.resolve()

    # Java 파일의 import문 분석
    try:
        content = current_java_file.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("import ") and line.endswith(f".{type_name};"):
                imp_path = line[7:-1].strip()
                rel = Path(*imp_path.split(".")).with_suffix(".java")
                # src_roots 탐색
                for parent in current_java_file.parents:
                    if parent.name == "java":
                        target = parent / rel
                        if target.is_file():
                            return target.resolve()
    except Exception:  # noqa: BLE001, S110
        pass

    # 프로젝트 전체 rglob
    for parent in current_java_file.parents:
        if parent.name in ("java", "src", "backend"):
            for found in parent.rglob(f"{type_name}.java"):
                if found.is_file():
                    return found.resolve()
            break

    return None


def parse_dto_fields(type_name: str, java_file: Path) -> list[ParamInfo]:
    """Record 또는 일반 DTO 클래스 소스 파일에서 필드(파라미터 정보) 추출."""
    dto_source = _find_type_source_file(type_name, java_file)
    if not dto_source or not dto_source.is_file():
        return []

    try:
        content = dto_source.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []

    clean = strip_comments(content)
    params: list[ParamInfo] = []

    # 1. Record 형태 탐색: public record Name(Type field1, Type field2, ...)
    record_match = re.search(r"\brecord\s+" + re.escape(type_name) + r"\s*\((.*?)\)", clean, re.DOTALL)
    if record_match:
        fields_str = record_match.group(1).strip()
        field_tokens = split_args(fields_str)
        for token in field_tokens:
            token = token.strip()
            if not token:
                continue
            # 애너테이션 제거
            token = re.sub(r"@\w+(?:\(.*?\))?", "", token).strip()
            parts = token.split()
            if len(parts) >= 2:
                f_type = parts[-2]
                f_name = parts[-1]
                is_coll = f_type.startswith(("List<", "Collection<", "Set<"))
                pg_t = JAVA_TO_PG_TYPE.get(f_type, "numeric" if "Id" in f_name or "Cnt" in f_name or "Rate" in f_name or "Amt" in f_name else "text")
                params.append(
                    ParamInfo(
                        name=f_name,
                        java_type=f_type,
                        pg_type=pg_t,
                        is_collection=is_coll,
                        source=f"record:{type_name}",
                    )
                )
        return params

    # 2. 일반 클래스 필드 선언 탐색: private Type fieldName;
    for m in re.finditer(r"(?:private|protected|public)?\s+([A-Za-z0-9_<>]+)\s+([A-Za-z0-9_]+)\s*;", clean):
        f_type, f_name = m.group(1), m.group(2)
        if f_type in ("class", "interface", "record", "static", "final"):
            continue
        is_coll = f_type.startswith(("List<", "Collection<", "Set<"))
        pg_t = JAVA_TO_PG_TYPE.get(f_type, "numeric" if "Id" in f_name or "Cnt" in f_name or "Rate" in f_name else "text")
        params.append(
            ParamInfo(
                name=f_name,
                java_type=f_type,
                pg_type=pg_t,
                is_collection=is_coll,
                source=f"dto:{type_name}",
            )
        )

    return params


def parse_mapper_java_file(java_file: Path) -> dict[str, MethodSignature]:
    """Java Mapper 인터페이스 파일을 파싱하여 메서드명별 MethodSignature 반환."""
    if not java_file.is_file():
        return {}

    mtime = java_file.stat().st_mtime
    cache_key = (str(java_file.resolve()), mtime)
    if cache_key in _SIG_CACHE:
        return _SIG_CACHE[cache_key]

    try:
        content = java_file.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return {}

    clean = strip_comments(content)
    signatures: dict[str, MethodSignature] = {}

    # 메서드 선언 정규식: 반환형 메서드명 ( 인자들 ) ;
    # 예: int insertAddDeductTypes(@Param(...) ...);
    #     List<DeductRes> selectDeducts(...);
    #     DeductRes selectCurrentDeduct(...);
    method_pattern = re.compile(
        r"([A-Za-z0-9_<>.,\s]+?)\s+([A-Za-z0-9_]+)\s*\((.*?)\)\s*;",
        re.DOTALL,
    )

    for m in method_pattern.finditer(clean):
        ret_type_raw = m.group(1).strip()
        method_name = m.group(2).strip()
        args_raw = m.group(3).strip()

        # 반환형 정제 (접근제어자, default, abstract 등 제거)
        ret_tokens = ret_type_raw.split()
        ret_type = ret_tokens[-1] if ret_tokens else "void"

        # 메서드가 있는 줄 번호 찾기
        line_no = 1
        pos = m.start()
        line_no = clean[:pos].count("\n") + 1

        sig = MethodSignature(
            name=method_name,
            return_type=ret_type,
            line_no=line_no,
            java_file=java_file,
        )

        arg_tokens = split_args(args_raw)
        for arg in arg_tokens:
            arg = arg.strip()
            if not arg:
                continue

            # @Param("paramName") 추출
            param_ann_match = re.search(r'@Param\s*\(\s*["\']([^"\']+)["\']\s*\)', arg)
            param_ann_name = param_ann_match.group(1) if param_ann_match else None

            # 애너테이션 제거
            clean_arg = re.sub(r"@\w+(?:\(.*?\))?", "", arg).strip()
            parts = clean_arg.split()
            if len(parts) < 2:
                continue
            java_t = parts[-2]
            var_name = parts[-1]

            is_coll = java_t.startswith(("List<", "Collection<", "Set<", "Iterable<"))
            coll_inner = ""
            if is_coll:
                in_m = re.search(r"<([A-Za-z0-9_]+)>", java_t)
                coll_inner = in_m.group(1) if in_m else "Object"

            # 원시/기본 타입인 경우
            if java_t in PRIMITIVE_OR_COMMON_TYPES or is_coll:
                p_name = param_ann_name or var_name
                pg_t = JAVA_TO_PG_TYPE.get(java_t, JAVA_TO_PG_TYPE.get(coll_inner, "numeric" if "Id" in p_name or "Cnt" in p_name else "text"))
                p_info = ParamInfo(name=p_name, java_type=java_t, pg_type=pg_t, is_collection=is_coll, source="param")
                sig.params.append(p_info)
                sig.param_map[p_name] = p_info
                # var_name과 param_ann_name이 다르면 둘 다 매핑
                if param_ann_name and var_name != param_ann_name:
                    sig.param_map[var_name] = p_info
            else:
                # DTO / Record 파라미터 펼치기
                dto_fields = parse_dto_fields(java_t, java_file)
                if dto_fields:
                    p_prefix = param_ann_name or var_name
                    for f in dto_fields:
                        # 1) 원본 필드명 #{companyId} 매핑
                        if f.name not in sig.param_map:
                            sig.param_map[f.name] = f
                            sig.params.append(f)
                        # 2) 접두사 붙은 형태 #{req.companyId} 매핑
                        prefixed = f"{p_prefix}.{f.name}"
                        sig.param_map[prefixed] = f
                else:
                    # DTO 필드를 못 찾은 경우 기본 파라미터로 등록
                    p_name = param_ann_name or var_name
                    pg_t = JAVA_TO_PG_TYPE.get(java_t, "text")
                    p_info = ParamInfo(name=p_name, java_type=java_t, pg_type=pg_t, source="param")
                    sig.params.append(p_info)
                    sig.param_map[p_name] = p_info

        signatures[method_name] = sig

    _SIG_CACHE[cache_key] = signatures
    return signatures


def get_mapper_signatures(
    namespace: str,
    src_root: Path | None = None,
) -> dict[str, MethodSignature]:
    """MyBatis namespace로부터 Java 매퍼 인터페이스의 메서드 시그니처 사전을 반환."""
    java_file = find_java_file_for_namespace(namespace, src_root)
    if not java_file:
        return {}
    return parse_mapper_java_file(java_file)


def get_method_signature(
    namespace: str,
    statement_id: str,
    src_root: Path | None = None,
) -> MethodSignature | None:
    """특정 namespace 및 statement_id에 해당하는 MethodSignature를 반환. 없으면 None."""
    sigs = get_mapper_signatures(namespace, src_root)
    return sigs.get(statement_id)
