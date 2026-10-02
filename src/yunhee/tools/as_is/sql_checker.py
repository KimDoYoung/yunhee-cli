"""AS-IS MyBatis 매퍼 SQL을 대상 DB에서 EXPLAIN으로 정합성 검증하는 도구."""

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from yunhee.config import LOCAL_DB, SCHEMA_ENV
from yunhee.tools.as_is.src_indexer import find_app
from yunhee.tools.base import ToolResult

STATEMENT_TAGS = ("select", "insert", "update", "delete", "sql")
ENV_ERROR_RE = re.compile(r'collation "[^"]+" for encoding "[^"]+" does not exist', re.IGNORECASE)
SCHEMA_ERROR_RE = re.compile(
    r'(column|relation|function|type|schema) (?:"?[\w.]+"?\s*\(.*?\)|"[^"]+"|\S+) does not exist|missing FROM-clause entry for table "[^"]+"',
    re.IGNORECASE,
)

TOKEN_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>|<!--.*?-->|<(/?)(\w+)([^>]*?)(/?)>|([^<]+)", re.DOTALL)
ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


class Node:
    """아주 작은 XML 트리 (MyBatis 매퍼는 SQL 텍스트와 태그가 섞여 있어 ElementTree보다 이쪽이 단순하다)"""

    def __init__(self, tag: str, attrs: dict[str, str], children: list[Any]) -> None:
        self.tag, self.attrs, self.children = tag, attrs, children


def parse_xml(text: str) -> Node:
    root = Node("root", {}, [])
    stack = [root]
    for m in TOKEN_RE.finditer(text):
        cdata, closing, tag, attrs, selfclose, chars = m.groups()
        if cdata is not None:
            stack[-1].children.append(cdata)
        elif chars is not None:
            stack[-1].children.append(chars)
        elif tag:
            if closing:
                while len(stack) > 1 and stack[-1].tag != tag:
                    stack.pop()
                if len(stack) > 1:
                    stack.pop()
            else:
                node = Node(tag, dict(ATTR_RE.findall(attrs)), [])
                stack[-1].children.append(node)
                if not selfclose:
                    stack.append(node)
    return root


def unescape(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#160;", " ")
    )


class Statement:

    def __init__(self, ns: str, sid: str, kind: str, node: Node, rel: Path, line: int) -> None:
        self.ns, self.sid, self.kind, self.node, self.rel, self.line = ns, sid, kind, node, rel, line

    @property
    def key(self) -> str:
        return f"{self.ns}.{self.sid}"


def load_statements(app: Path) -> dict[str, Statement]:
    statements: dict[str, Statement] = {}
    for path in sorted(app.rglob("*.xml")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        ns = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", raw)
        if not ns:
            continue
        root = parse_xml(raw)
        mapper = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
        if not mapper:
            continue
        for child in mapper.children:
            if isinstance(child, Node) and child.tag in STATEMENT_TAGS and "id" in child.attrs:
                pos = re.search(rf'<{child.tag}\b[^>]*\bid\s*=\s*"{re.escape(child.attrs["id"])}"', raw)
                line = raw.count("\n", 0, pos.start()) + 1 if pos else 0
                st = Statement(ns.group(1), child.attrs["id"], child.tag, child, path.relative_to(app), line)
                statements[st.key] = st
    return statements


# ---------------------------------------------------------------- 펼치기

def render(node: Node, ns: str, statements: dict[str, Statement], seen: tuple[str, ...] = ()) -> str:
    out = []
    for c in node.children:
        if isinstance(c, str):
            out.append(unescape(c))
            continue
        tag, test = c.tag, c.attrs.get("test", "")
        if tag in ("bind", "selectKey"):
            continue
        if tag == "include":
            ref = c.attrs.get("refid", "")
            target = (
                statements.get(ref)
                or statements.get(f"{ns}.{ref}")
                or next((t for t in statements.values() if t.sid == ref), None)
            )
            if target and target.key not in seen:
                out.append(render(target.node, target.ns, statements, seen + (target.key,)))
            else:
                out.append(f" /* include {ref} 없음 */ ")
        elif tag == "choose":
            whens = [w for w in c.children if isinstance(w, Node) and w.tag == "when"]
            other = next((w for w in c.children if isinstance(w, Node) and w.tag == "otherwise"), None)
            pick = (
                next((w for w in whens if "isPostgreSql" in w.attrs.get("test", "")), None)
                or next((w for w in whens if "isTibero" not in w.attrs.get("test", "")), None)
                or other
            )
            if pick:
                out.append(render(pick, ns, statements, seen))
        elif tag == "if":
            if "isTibero" not in test:
                out.append(render(c, ns, statements, seen))
        elif tag == "foreach":
            out.append(" NULL ")
        elif tag in ("where", "set", "trim"):
            body = render(c, ns, statements, seen)
            if tag == "where":
                body = " WHERE 1=1 " + re.sub(r"^\s*(AND|OR)\b", " AND ", body, flags=re.IGNORECASE) if body.strip() else ""
            elif tag == "set":
                body = " SET " + body.strip().rstrip(",")
            else:
                prefix = c.attrs.get("prefix", "")
                overrides = [o.strip() for o in c.attrs.get("suffixOverrides", "").split("|") if o.strip()]
                body = body.strip()
                for o in overrides:
                    if body.upper().endswith(o.upper()):
                        body = body[:-len(o)]
                body = f" {prefix} {body} {c.attrs.get('suffix', '')} "
            out.append(body)
        else:
            out.append(render(c, ns, statements, seen))
    return "".join(out)


def to_sql(st: Statement, statements: dict[str, Statement]) -> str:
    sql = render(st.node, st.ns, statements, (st.key,))
    sql = re.sub(r"#\{[^}]*\}", "NULL", sql)
    sql = re.sub(r"(?i)\bin\s*\$\{[^}]*\}", "IN (1)", sql)
    sql = re.sub(r"(?i)\bin\s+NULL\b", "IN (NULL)", sql)
    sql = re.sub(r"\$\{[^}]*\}", "1", sql)
    return sql.strip().rstrip(";")


def parse_pg_url(url: str | None) -> dict[str, str]:
    """PostgreSQL URL에서 psql 환경변수 사전(PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)을 추출한다."""
    if not url:
        return {}
    try:
        parsed = urlsplit(url)
        env: dict[str, str] = {}
        if parsed.hostname:
            env["PGHOST"] = parsed.hostname
        if parsed.port:
            env["PGPORT"] = str(parsed.port)
        if parsed.username:
            env["PGUSER"] = unquote(parsed.username)
        if parsed.password:
            env["PGPASSWORD"] = unquote(parsed.password)
        if parsed.path and parsed.path.lstrip("/"):
            env["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
        return env
    except Exception:  # noqa: BLE001
        return {}


def get_db_env(db_name: str | None = None) -> tuple[str, dict[str, str]]:
    """db_name과 .env.local의 설정(SCHEMA_ENV, LOCAL_DB)을 결합하여 (최종 DB명, PG 환경변수) 반환."""
    url = os.getenv(SCHEMA_ENV) or LOCAL_DB or os.getenv("LOCAL_DB") or os.getenv("TEST_DB")
    pg_env = parse_pg_url(url)

    final_db = db_name or "asseterpdb"
    if (db_name is None or db_name == "asseterpdb") and pg_env.get("PGDATABASE"):
        final_db = pg_env["PGDATABASE"]

    return final_db, pg_env


# ---------------------------------------------------------------- 실행

def explain(sql: str, db: str, extra_env: dict[str, str] | None = None) -> str | None:
    script = f"BEGIN READ ONLY;\nSET statement_timeout = '10s';\nEXPLAIN {sql};\nROLLBACK;\n"
    env = {
        **os.environ,
        **(extra_env or {}),
        "LC_MESSAGES": "C",
        "PGOPTIONS": "-c lc_messages=C",
    }
    try:
        res = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"],
            input=script,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return "[ERROR] psql 명령어를 찾을 수 없습니다. PostgreSQL 클라이언트가 설치되어 있는지 확인하세요."

    if res.returncode == 0:
        return None
    lines = res.stderr.splitlines()
    idx = next(
        (i for i, l in enumerate(lines) if "ERROR" in l or "오류" in l or "FATAL" in l or "error:" in l.lower()),
        None,
    )
    if idx is None:
        return res.stderr.strip() or f"psql 실행 실패 (종료 코드 {res.returncode})"
    err = re.sub(r"^psql:<stdin>:\d+:\s*", "", lines[idx]).strip()
    near = next((l.strip() for l in lines[idx + 1: idx + 2] if l.strip().startswith("LINE")), "")
    return f"{err} — {near[:160]}" if near else err


def screens_using(src_index: Path | None, keys: list[str]) -> dict[str, set[str]]:
    """src-index 화면 파일에서 SQL ID를 쓰는 화면"""
    result: dict[str, set[str]] = defaultdict(set)
    if not src_index or not src_index.is_dir():
        return result
    for f in src_index.glob("*/screens/*.md"):
        text = f.read_text(encoding="utf-8")
        for key in keys:
            if f"`{key}`" in text:
                result[key].add(f.stem)
    return result


def md_cell(v: Any) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def check_sql(
    src_root: Path,
    target_file: Path,
    db: str = "asseterpdb",
    src_index_dir: Path | None = None,
) -> ToolResult:
    """AS-IS MyBatis 매퍼 SQL을 대상 DB에서 EXPLAIN으로 정합성을 검증한다."""
    if not src_root.is_dir():
        return ToolResult(ok=False, error=f"AS-IS 소스 디렉터리를 찾을 수 없습니다: {src_root}")

    app = find_app(src_root)
    if not app:
        return ToolResult(
            ok=False,
            error=f"{src_root} 아래에서 앱 패키지를 찾지 못했습니다.",
        )

    statements = load_statements(app)
    targets = [s for s in statements.values() if s.kind != "sql"]
    if not targets:
        return ToolResult(ok=False, error=f"{app} 아래에서 실행 대상 SQL을 찾지 못했습니다.")

    target_db, db_env = get_db_env(db)

    # psql 연결성 사전 테스트
    test_err = explain("SELECT 1", target_db, extra_env=db_env)
    if test_err is not None:
        return ToolResult(
            ok=False,
            error=f"대상 DB({target_db}) 접속 실패: {test_err}\n"
                  f"DB가 실행 중인지 확인하고, .env.local의 LOCAL_DB 또는 PGHOST/PGUSER/PGPASSWORD 설정을 확인하세요.",
        )

    ok_list, schema_list, env_list, other_list = [], [], [], []
    for st in sorted(targets, key=lambda s: s.key):
        err = explain(to_sql(st, statements), target_db, extra_env=db_env)
        if err is None:
            ok_list.append(st)
        elif SCHEMA_ERROR_RE.search(err):
            schema_list.append((st, err))
        elif ENV_ERROR_RE.search(err):
            env_list.append((st, err))
        else:
            other_list.append((st, err))

    used_by = screens_using(src_index_dir, [s.key for s, _ in schema_list + env_list + other_list])
    missing: dict[str, list[Statement]] = defaultdict(list)
    for st, err in schema_list:
        m = SCHEMA_ERROR_RE.search(err)
        if m:
            missing[m.group(0)].append(st)

    target_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 매퍼 SQL ↔ DB 정합성 (EXPLAIN)",
        "",
        "`yunhee sql-check`가 생성했다. 직접 수정하지 말고 명령어를 다시 실행한다.",
        "",
        f"- 소스: `{src_root}` (`{app.relative_to(src_root).as_posix() if app != src_root else '.'}`)",
        f"- DB: `{target_db}`",
        f"- SQL {len(targets)}개(`<sql>` 조각 제외): **통과 {len(ok_list)}**, **스키마 차이 {len(schema_list)}**, DB 환경 차이 {len(env_list)}, 펼치기 한계·기타 {len(other_list)}",
        "",
        '통과는 "그 DB에 그 SQL이 쓰는 테이블·컬럼·함수가 모두 있다"는 뜻이다(결과 정합성까지 보장하지 않음).',
        "",
    ]
    lines += ["## 없는 DB 객체", "", "| 오류 | SQL 수 | SQL |", "|:---|---:|:---|"]
    for msg, sts in sorted(missing.items(), key=lambda x: -len(x[1])):
        lines.append(f"| `{md_cell(msg)}` | {len(sts)} | " + ", ".join(f"`{s.key}`" for s in sts) + " |")

    for title, rows in (
        ("스키마 차이", schema_list),
        ("DB 환경 차이", env_list),
        ("펼치기 한계·기타 (직접 확인 필요)", other_list),
    ):
        lines += ["", f"## {title}", "", "| SQL | 파일:줄 | 화면 | 오류 |", "|:---|:---|:---|:---|"]
        for st, err in sorted(rows, key=lambda x: x[0].key):
            screens = ", ".join(sorted(used_by.get(st.key, []))) or "-"
            lines.append(f"| `{st.key}` | `{st.rel}:{st.line}` | {screens} | {md_cell(err)} |")

    affected: dict[str, list[str]] = defaultdict(list)
    for st, _ in schema_list:
        for scr in used_by.get(st.key, []):
            affected[scr].append(st.key)
    lines += ["", "## 스키마 차이가 있는 화면", "", "| 화면 | SQL |", "|:---|:---|"]
    for scr, keys in sorted(affected.items()):
        lines.append(f"| `{scr}` | " + ", ".join(f"`{k}`" for k in sorted(keys)) + " |")

    target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return ToolResult(
        ok=True,
        data={
            "target_file": str(target_file),
            "target_db": target_db,
            "total_sql": len(targets),
            "passed_count": len(ok_list),
            "schema_diff_count": len(schema_list),
            "env_diff_count": len(env_list),
            "other_count": len(other_list),
            "affected_screens_count": len(affected),
        },
    )
