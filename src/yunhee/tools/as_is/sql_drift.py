"""두 AS-IS 소스 간 MyBatis SQL Drift(변경점) 감지 및 TOBE 매퍼 영향 분석 도구."""

import difflib
import re
from pathlib import Path
from typing import Any

from yunhee.tools.as_is.mybatis_render import (
    Statement,
    load_statements,
    render_node,
)
from yunhee.tools.base import ToolResult

DIFF_TOKEN_RE = re.compile(
    r"'(?:''|[^'])*'"                                           # 문자열 리터럴: 'false', 'Y' 등
    r"|[#$]\{[^}]+\}"                                           # 파라미터: #{companyId}, ${order} 등
    r"|</?[a-zA-Z0-9_]+(?:'[^']*'|\"[^\"]*\"|[^>'])*>"          # XML 태그: </when>, <when test="..."> 등
    r"|!=|<=|>=|<>|==|\|\||::"                                 # 복합 연산자/캐스팅: !=, <=, >=, <>, ==, ||, ::
    r"|\w+"                                                     # 일반 단어 (식별자, 키워드, 숫자)
    r"|[^\w\s]"                                                 # 기타 기호 (, ; ( ) 등)
)

XML_TAG_RE_STR = r"</?[a-zA-Z0-9_]+(?:'[^']*'|\"[^\"]*\"|[^>'])*>"
PRESERVE_RE = re.compile(
    rf"('(?:''|[^'])*')|([#$]\{{[^}}]+\}})|({XML_TAG_RE_STR})"
)


def clean_sql_for_drift(raw: str) -> str:
    """주석 및 공백을 정규화하되, 대소문자는 원본 그대로 보존한다."""
    s = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = re.sub(r"--[^\n]*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_sql_for_drift(raw: str) -> str:
    """주석 및 공백을 정규화하여 실제 SQL 내용만 남긴다.
    문자열 리터럴('...'), 파라미터(#{...}, ${...}), 그리고 XML 태그(<...>) 밖은 소문자로 변환하여
    키워드/컬럼명 대소문자 차이를 무시한다.
    XML 태그 내부(태그명, 속성명, OGNL 식 등)는 원래 대소문자를 유지한다.
    """
    s = clean_sql_for_drift(raw)
    parts: list[str] = []
    last_idx = 0
    for m in PRESERVE_RE.finditer(s):
        if m.start() > last_idx:
            parts.append(s[last_idx:m.start()].lower())
        parts.append(m.group(0))  # 리터럴, 파라미터, XML 태그는 원래 대소문자 유지
        last_idx = m.end()
    if last_idx < len(s):
        parts.append(s[last_idx:].lower())
    return "".join(parts)


def render_statement_structure(st: Statement, statements: dict[str, Statement]) -> str:
    """<include>를 재귀적으로 펼친 statement의 XML/SQL 구조 문자열을 반환한다."""
    if st.node is None:
        return st.raw
    return render_node(st.node, st.ns, statements, {}, mode="structure", seen=())


def _format_token_slice(words: list[str], max_tokens: int = 30, max_chars: int = 200) -> str:
    """토큰 슬라이스를 문자열로 포맷하되 최대 토큰/글자수 초과 시 자르고 요약 표기한다."""
    if not words:
        return ""
    total = len(words)
    taken: list[str] = []
    curr_len = 0
    for w in words:
        if len(taken) >= max_tokens:
            break
        add_len = len(w) + (1 if taken else 0)
        if taken and (curr_len + add_len > max_chars):
            break
        taken.append(w)
        curr_len += add_len

    omitted = total - len(taken)
    text = " ".join(taken)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    if omitted > 0:
        text += f" … (+{omitted}토큰)"
    return text


def _token_key(w: str) -> str:
    """diff 매칭용 키를 생성한다 (리터럴/파라미터/XML태그 외에는 소문자 비교)."""
    if w.startswith(("'", "#{", "${", "<")):
        return w
    return w.lower()


def get_diff_details(old_text: str, new_text: str) -> tuple[str, list[str]]:
    """두 텍스트의 단어 단위 diff 요약(최대 400자 요약)과 전체 변경 목록을 반환한다."""
    old_clean = clean_sql_for_drift(old_text)
    new_clean = clean_sql_for_drift(new_text)

    old_words = DIFF_TOKEN_RE.findall(old_clean)
    new_words = DIFF_TOKEN_RE.findall(new_clean)

    old_keys = [_token_key(w) for w in old_words]
    new_keys = [_token_key(w) for w in new_words]

    matcher = difflib.SequenceMatcher(None, old_keys, new_keys)
    diff_parts: list[str] = []
    full_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            del_str = _format_token_slice(old_words[i1:i2])
            ins_str = _format_token_slice(new_words[j1:j2])
            diff_parts.append(f"- {del_str} / + {ins_str}")
            full_parts.append(f"- {' '.join(old_words[i1:i2])} / + {' '.join(new_words[j1:j2])}")
        elif tag == "delete":
            del_str = _format_token_slice(old_words[i1:i2])
            diff_parts.append(f"- {del_str}")
            full_parts.append(f"- {' '.join(old_words[i1:i2])}")
        elif tag == "insert":
            ins_str = _format_token_slice(new_words[j1:j2])
            diff_parts.append(f"+ {ins_str}")
            full_parts.append(f"+ {' '.join(new_words[j1:j2])}")

    if not diff_parts:
        return "(구조 변경)", []

    total_chunks = len(diff_parts)
    if total_chunks > 3:
        shown = diff_parts[:3]
        extra = total_chunks - 3
        summary = " · ".join(shown) + f" · 외 {extra}곳"
    else:
        summary = " · ".join(diff_parts)

    if len(summary) > 400:
        summary = summary[:400].rstrip() + " …"

    return summary, full_parts


def get_diff_summary(old_text: str, new_text: str) -> str:
    """두 텍스트의 단어 단위 diff 요약을 반환한다."""
    summary, _ = get_diff_details(old_text, new_text)
    return summary


BOUNDARY_PATTERN = re.compile(
    r"(?:<mapper\b[^>]*>|</select>|</insert>|</update>|</delete>|</sql>|<sql\b[^>]*/>)"
)

AS_IS_STMT_RE = re.compile(
    r"AS-IS(?:\s*\([^)]*\))?\s+"
    r"([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)"
    r"(?:\s*\(L(\d+)\)|\s+L(\d+))?"
)


def extract_tobe_as_is_refs(
    tobe_dir: Path,
    new_name: str = "",
    valid_keys: set[str] | None = None,
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """TOBE 매퍼 디렉터리 내 XML 주석에서 AS-IS SQL 참조 관계 및 반영 표시 여부를 추출한다."""
    tobe_refs: dict[str, list[str]] = {}
    unreferenced: list[str] = []
    reflected_tobe: list[str] = []

    for path in sorted(tobe_dir.rglob("*.xml")):
        if "target" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        ns_m = re.search(r'<mapper\s+namespace="([^"]+)"', raw)
        mapper_name = ns_m.group(1).split(".")[-1] if ns_m else path.stem

        # 1. 파일 헤더 주석에서 AS-IS 매퍼/statement 정보 추출
        # 예: AS-IS server/emp/mapper/emp00_trans_info.xml selectByText(L339) · selectById(L66) ... (+ common.emp00_trans_info)
        # 또는: AS-IS(IDMS-IC) server/emp/mapper/emp00_trans_info.xml ...
        header_ns = ""
        header_stmts: set[str] = set()
        header_commons: set[str] = set()
        file_is_reflected = False

        m_hdr = re.search(r"<!--[\s\S]*?AS-IS(?:\s*\([^)]*\))?\s+(?:[\w/]+/)?([a-zA-Z0-9_]+)\.xml\b([\s\S]*?)-->", raw)
        if m_hdr:
            header_ns = m_hdr.group(1)
            hdr_body = m_hdr.group(2)
            hdr_full = m_hdr.group(0)
            if new_name and re.search(rf"\(\s*{re.escape(new_name)}\s*\)", hdr_full, re.IGNORECASE):
                file_is_reflected = True
            for m_id in re.finditer(r"\b([a-zA-Z0-9_]+)\s*\(L\d+\)", hdr_body):
                header_stmts.add(m_id.group(1))
            for m_com in re.finditer(r"\b(common\.[a-zA-Z0-9_]+)\b", hdr_body):
                header_commons.add(m_com.group(1))

        # 2. Statement별 주석 추출
        stmt_matches = list(re.finditer(r'<(select|insert|update|delete)\b[^>]*\bid="([^"]+)"', raw))

        for idx, sm in enumerate(stmt_matches):
            sid = sm.group(2)
            tobe_key = f"{mapper_name}.{sid}"

            # statement 이전 텍스트 (바로 앞 요소의 끝부터 현재 statement 시작까지)
            boundaries = list(BOUNDARY_PATTERN.finditer(raw, 0, sm.start()))
            prev_end = boundaries[-1].end() if boundaries else 0
            chunk_before = raw[prev_end : sm.start()]

            # statement 본문 텍스트
            stmt_tag = sm.group(1)
            close_m = re.search(rf"</{stmt_tag}>", raw[sm.start():])
            stmt_end = (sm.start() + close_m.end()) if close_m else (
                stmt_matches[idx + 1].start() if idx + 1 < len(stmt_matches) else len(raw)
            )
            stmt_body = raw[sm.start() : stmt_end]

            # statement 단위 새 원본 반영 표시 확인 (단일 주석 내에 AS-IS 및 (new_name) 동시 존재)
            stmt_is_reflected = False
            if new_name:
                for m_comm in re.finditer(r"<!--([\s\S]*?)-->", chunk_before):
                    c_txt = m_comm.group(1)
                    if ".xml" in c_txt:
                        continue
                    if "AS-IS" in c_txt and re.search(rf"\(\s*{re.escape(new_name)}\s*\)", c_txt, re.IGNORECASE):
                        stmt_is_reflected = True
                        break

            is_reflected = file_is_reflected or stmt_is_reflected
            if is_reflected:
                reflected_tobe.append(tobe_key)

            refs_found: list[str] = []

            # (1) statement 상단 주석: <!-- AS-IS selectByText L339 (...) -->
            # .xml이 포함된 파일 헤더 주석은 제외
            for m_comment in re.finditer(r"<!--([\s\S]*?)-->", chunk_before):
                c_text = m_comment.group(1)
                if ".xml" in c_text:
                    continue
                for m_as in AS_IS_STMT_RE.finditer(c_text):
                    target_ref = m_as.group(1)
                    has_line = bool(m_as.group(2) or m_as.group(3))
                    if target_ref.lower() in ("server", "common", "xml", "mapper"):
                        continue
                    if "." in target_ref:
                        cand_key = target_ref
                    elif header_ns:
                        cand_key = f"{header_ns}.{target_ref}"
                    elif valid_keys:
                        matches = [k for k in valid_keys if k.endswith(f".{target_ref}")]
                        cand_key = matches[0] if len(matches) == 1 else target_ref
                    else:
                        cand_key = target_ref

                    if valid_keys is not None:
                        if cand_key in valid_keys:
                            refs_found.append(cand_key)
                        elif has_line:
                            # 원본 어디에도 없지만 명시적 (L숫자) 표기이므로 (미존재) 대상
                            refs_found.append(cand_key)
                        # else: 일반 설명 문장의 단어이므로 무시 (미존재로 내지 않음)
                    else:
                        if has_line or (cand_key.split(".")[-1].upper() not in ("SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE", "JOIN")):
                            refs_found.append(cand_key)

            # (2) statement 내부의 common <include>
            for m_inc in re.finditer(r'<include\s+refid="([^"]+)"', stmt_body):
                inc_ref = m_inc.group(1)
                if inc_ref.startswith("common."):
                    refs_found.append(inc_ref)

            # (3) 파일 헤더에만 정의되어 있고 statement 주석이 없는 경우, id 이름 매칭
            if not refs_found and header_ns:
                for hs in header_stmts:
                    if hs.lower() in sid.lower() or sid.lower() in hs.lower():
                        cand_hdr = f"{header_ns}.{hs}"
                        if valid_keys is None or cand_hdr in valid_keys:
                            refs_found.append(cand_hdr)
                for hc in header_commons:
                    if hc in stmt_body:
                        refs_found.append(hc)

            # 중복 제거 (순서 보존)
            dedup_refs = []
            for r in refs_found:
                if r not in dedup_refs:
                    dedup_refs.append(r)

            if dedup_refs:
                tobe_refs[tobe_key] = dedup_refs
            else:
                unreferenced.append(tobe_key)

    return tobe_refs, unreferenced, reflected_tobe


def check_sql_drift(
    old_root: Path,
    new_root: Path | None = None,
    tobe_dir: Path | None = None,
    only_tobe: bool = False,
    fmt: str = "md",
) -> ToolResult:
    """구 AS-IS 소스와 신 AS-IS 소스 간 statement 단위 SQL Drift를 검증한다."""
    from yunhee.config import ASIS_SRC_DIR
    from yunhee.tools.as_is.src_indexer import find_app

    target_new = new_root or ASIS_SRC_DIR
    if not target_new or not Path(target_new).is_dir():
        return ToolResult(ok=False, error=f"신 AS-IS 소스 디렉터리를 찾을 수 없습니다: {target_new}")

    old_app = find_app(Path(old_root)) or Path(old_root)
    new_app = find_app(Path(target_new)) or Path(target_new)

    old_stmts = load_statements(old_app)
    new_stmts = load_statements(new_app)

    same_keys: list[str] = []
    changed_items: list[dict[str, Any]] = []
    added_keys: list[str] = []
    removed_keys: list[str] = []

    # 전체 키 합집합
    all_keys = sorted(set(old_stmts.keys()) | set(new_stmts.keys()))

    for key in all_keys:
        if key in old_stmts and key in new_stmts:
            st_old = old_stmts[key]
            st_new = new_stmts[key]
            raw_old = render_statement_structure(st_old, old_stmts)
            raw_new = render_statement_structure(st_new, new_stmts)
            clean_old = clean_sql_for_drift(raw_old)
            clean_new = clean_sql_for_drift(raw_new)
            norm_old = normalize_sql_for_drift(clean_old)
            norm_new = normalize_sql_for_drift(clean_new)

            if norm_old == norm_new:
                same_keys.append(key)
            else:
                diff_summary, diff_full = get_diff_details(clean_old, clean_new)
                changed_items.append({
                    "key": key,
                    "old_norm": norm_old,
                    "new_norm": norm_new,
                    "diff": diff_summary,
                    "diff_full": diff_full,
                    "old_rel": str(st_old.rel),
                    "new_rel": str(st_new.rel),
                })
        elif key in new_stmts:
            added_keys.append(key)
        else:
            removed_keys.append(key)

    changed_key_set = {item["key"] for item in changed_items}

    # TOBE 매퍼 분석
    tobe_affected: list[dict[str, Any]] = []
    unreferenced_tobe: list[str] = []
    reflected_tobe: list[str] = []

    diff_by_key = {item["key"]: item["diff"] for item in changed_items}

    if tobe_dir and Path(tobe_dir).is_dir():
        new_name = Path(target_new).name
        tobe_refs, unref, refl = extract_tobe_as_is_refs(
            Path(tobe_dir),
            new_name=new_name,
            valid_keys=set(all_keys),
        )
        unreferenced_tobe = unref
        reflected_tobe = refl

        for tobe_key, as_is_keys in tobe_refs.items():
            refs_status = []
            is_changed = False
            diff_lines = []
            for ak in as_is_keys:
                if ak in changed_key_set:
                    refs_status.append(f"{ak} (바뀜)")
                    is_changed = True
                    if ak in diff_by_key:
                        diff_lines.append(f"{diff_by_key[ak]}")
                elif ak in same_keys:
                    refs_status.append(f"{ak} (같음)")
                elif ak in added_keys:
                    refs_status.append(f"{ak} (새로생김)")
                    is_changed = True
                elif ak in removed_keys:
                    refs_status.append(f"{ak} (없어짐)")
                    is_changed = True
                else:
                    refs_status.append(f"{ak} (미존재)")

            # 새 원본 반영 표시(IDMS-IC 등)가 있는 statement는 영향 목록에서 제외
            is_refl = tobe_key in reflected_tobe
            if is_refl:
                is_changed = False

            if is_changed or not only_tobe:
                tobe_affected.append({
                    "tobe_key": tobe_key,
                    "as_is_refs": refs_status,
                    "is_changed": is_changed,
                    "diff_lines": diff_lines,
                    "is_reflected": is_refl,
                })

    changed_tobe = [t for t in tobe_affected if t["is_changed"] and not t.get("is_reflected")]

    # 결과 데이터 조립
    data = {
        "summary": {
            "total_old": len(old_stmts),
            "total_new": len(new_stmts),
            "same": len(same_keys),
            "changed": len(changed_items),
            "added": len(added_keys),
            "removed": len(removed_keys),
            "tobe_affected": len(changed_tobe),
            "tobe_reflected": len(reflected_tobe),
        },
        "changed": changed_items,
        "added": added_keys,
        "removed": removed_keys,
        "tobe_affected": tobe_affected,
        "reflected_tobe": reflected_tobe,
        "unreferenced_tobe": unreferenced_tobe,
    }

    # 마크다운 렌더링
    lines: list[str] = [
        "### SQL Drift 검증 결과",
        f"- 구 AS-IS: `{old_root}` ({len(old_stmts)}개 statements)",
        f"- 신 AS-IS: `{target_new}` ({len(new_stmts)}개 statements)",
        f"- 동일: {len(same_keys)}개, 바뀜: {len(changed_items)}개, 신규: {len(added_keys)}개, 삭제: {len(removed_keys)}개",
    ]

    if tobe_dir:
        tobe_line = f"- TOBE 매퍼: `{tobe_dir}` (영향 받는 TOBE statement: {len(changed_tobe)}개"
        if reflected_tobe:
            tobe_line += f", 반영 표시됨: {len(reflected_tobe)}개"
        tobe_line += ")"
        lines.append(tobe_line)

    if only_tobe and tobe_dir:
        # --only-tobe: 바뀐 원본 statement를 쓰는 TOBE statement 목록만
        lines.append("\n#### 바뀐 원본 SQL을 사용하는 TOBE statement")
        if changed_tobe:
            for t in changed_tobe:
                refs_str = " · ".join(t["as_is_refs"])
                lines.append(f"- `{t['tobe_key']}` ← {refs_str}")
                for d in t.get("diff_lines", []):
                    lines.append(f"  {d}")
        else:
            lines.append("- (바뀐 원본 SQL을 사용하는 TOBE statement 없음)")

        if reflected_tobe:
            lines.append(f"\n#### 새 원본 반영 표시됨 ({len(reflected_tobe)}개)")
            for rk in reflected_tobe:
                lines.append(f"- `{rk}`")

        if unreferenced_tobe:
            lines.append("\n#### ⚠ 출처 없음 (TOBE statement 주석 부재)")
            for u in unreferenced_tobe[:20]:
                lines.append(f"- `{u}`")
            if len(unreferenced_tobe) > 20:
                lines.append(f"  ... 외 {len(unreferenced_tobe) - 20}개")
    else:
        if changed_items:
            lines.append(f"\n#### 바뀐 Statement ({len(changed_items)}개)")
            for c in changed_items:
                lines.append(f"- `{c['key']}`: {c['diff']}")

        if added_keys:
            lines.append(f"\n#### 새로 생긴 Statement ({len(added_keys)}개)")
            for a in added_keys[:10]:
                lines.append(f"- `{a}`")
            if len(added_keys) > 10:
                lines.append(f"  ... 외 {len(added_keys) - 10}개")

        if removed_keys:
            lines.append(f"\n#### 없어진 Statement ({len(removed_keys)}개)")
            for r in removed_keys[:10]:
                lines.append(f"- `{r}`")
            if len(removed_keys) > 10:
                lines.append(f"  ... 외 {len(removed_keys) - 10}개")

        if tobe_affected and changed_tobe:
            lines.append(f"\n#### TOBE 영향 ({len(changed_tobe)}개)")
            for t in changed_tobe:
                refs_str = " · ".join(t["as_is_refs"])
                lines.append(f"- `{t['tobe_key']}` ← {refs_str}")
                for d in t.get("diff_lines", []):
                    lines.append(f"  {d}")

        if reflected_tobe:
            lines.append(f"\n#### 새 원본 반영 표시됨 ({len(reflected_tobe)}개)")
            for rk in reflected_tobe:
                lines.append(f"- `{rk}`")

    data["summary_text"] = "\n".join(lines)

    return ToolResult(ok=True, data=data)
