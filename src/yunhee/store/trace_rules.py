"""trace-rule 저장소: 에이전트가 내린 판정(규칙)과 그 근거 위치를 sqlite에 저장한다.

프로젝트별로 `project` 컬럼으로 구분한다 (프로젝트 이름은 `.yunhee/project.json`의 name, 없으면 폴더 이름).
근거에는 **그 시점의 내용 해시**를 함께 저장해, 나중에 `trace-rule verify`가 근거가 아직 유효한지 결정적으로 확인한다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from yunhee import project
from yunhee.store.db import get_connection

VERDICTS = ("일치", "누락", "변경", "의도적 변경")
_ALIASES = {
    "match": "일치", "ok": "일치", "same": "일치",
    "missing": "누락", "omitted": "누락",
    "changed": "변경", "diff": "변경",
    "intended": "의도적 변경", "intentional": "의도적 변경", "의도적": "의도적 변경", "의도적변경": "의도적 변경",
}


def normalize_verdict(value: str) -> str:
    v = value.strip()
    out = v if v in VERDICTS else _ALIASES.get(v.lower().replace(" ", ""), _ALIASES.get(v.lower()))
    if out is None:
        raise ValueError(f"판정은 {', '.join(VERDICTS)} 중 하나여야 합니다: {value}")
    return out


def project_name() -> str:
    root = project.find_project_root()
    data = project.load(root)
    return data["name"] if data and data.get("name") else root.name


@dataclass
class Evidence:
    kind: str  # file / mapper
    side: str  # asis / tobe
    ref: str  # 사용자가 적은 원문 (Emp00_Tab_TransInfo.java:418, emp00_trans_info.selectByText)
    path: str  # 루트 기준 상대 경로 (mapper는 xml 파일)
    line: int | None
    line_end: int | None
    anchor: str  # mapper `ns.id`, 파일은 ""
    excerpt: str  # 그 시점의 정규화된 내용 (이동 추적에 쓴다)
    hash: str


@dataclass
class Rule:
    project: str
    rule_id: str
    target: str
    verdict: str
    note: str
    created_at: str
    updated_at: str
    evidence: list[Evidence] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_rule (
            project TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            target TEXT NOT NULL,
            verdict TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project, rule_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_rule_evidence (
            project TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            side TEXT NOT NULL,
            ref TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER,
            line_end INTEGER,
            anchor TEXT NOT NULL DEFAULT '',
            excerpt TEXT NOT NULL DEFAULT '',
            hash TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (project, rule_id, seq)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_rule_target ON trace_rule (project, target)")


def _connect(conn: sqlite3.Connection | None) -> tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False
    c = get_connection()
    init_db(c)
    return c, True


def _next_id(conn: sqlite3.Connection, proj: str) -> str:
    rows = conn.execute("SELECT rule_id FROM trace_rule WHERE project = ?", (proj,)).fetchall()
    nums = [int(r[0].split("-")[1]) for r in rows if r[0].startswith("R-") and r[0].split("-")[1].isdigit()]
    return f"R-{max(nums, default=0) + 1:03d}"


def _put_evidence(conn: sqlite3.Connection, proj: str, rule_id: str, evidence: list[Evidence]) -> None:
    conn.execute("DELETE FROM trace_rule_evidence WHERE project = ? AND rule_id = ?", (proj, rule_id))
    for i, e in enumerate(evidence, 1):
        conn.execute(
            "INSERT INTO trace_rule_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (proj, rule_id, i, e.kind, e.side, e.ref, e.path, e.line, e.line_end, e.anchor, e.excerpt, e.hash),
        )


def add_rule(target: str, verdict: str, note: str, evidence: list[Evidence], proj: str | None = None, conn: sqlite3.Connection | None = None) -> Rule:
    proj = proj or project_name()
    c, close = _connect(conn)
    try:
        rule_id = _next_id(c, proj)
        now = _now()
        c.execute("INSERT INTO trace_rule VALUES (?,?,?,?,?,?,?)", (proj, rule_id, target, normalize_verdict(verdict), note, now, now))
        _put_evidence(c, proj, rule_id, evidence)
        c.commit()
        return get_rule(rule_id, proj, c)  # type: ignore[return-value]
    finally:
        if close:
            c.close()


def _evidence_of(c: sqlite3.Connection, proj: str, rule_id: str) -> list[Evidence]:
    rows = c.execute(
        "SELECT kind, side, ref, path, line, line_end, anchor, excerpt, hash FROM trace_rule_evidence WHERE project = ? AND rule_id = ? ORDER BY seq",
        (proj, rule_id),
    ).fetchall()
    return [Evidence(*r) for r in rows]


def get_rule(rule_id: str, proj: str | None = None, conn: sqlite3.Connection | None = None) -> Rule | None:
    proj = proj or project_name()
    c, close = _connect(conn)
    try:
        row = c.execute(
            "SELECT project, rule_id, target, verdict, note, created_at, updated_at FROM trace_rule WHERE project = ? AND rule_id = ?",
            (proj, rule_id.upper()),
        ).fetchone()
        return Rule(*row, evidence=_evidence_of(c, proj, row[1])) if row else None
    finally:
        if close:
            c.close()


def list_rules(target: str | None = None, proj: str | None = None, verdict: str | None = None, conn: sqlite3.Connection | None = None) -> list[Rule]:
    """target을 주면 그 대상(대소문자 무시, 접두사 일치)의 규칙만."""
    proj = proj or project_name()
    c, close = _connect(conn)
    try:
        rows = c.execute(
            "SELECT project, rule_id, target, verdict, note, created_at, updated_at FROM trace_rule WHERE project = ? ORDER BY rule_id", (proj,)
        ).fetchall()
        rules = [Rule(*r, evidence=_evidence_of(c, proj, r[1])) for r in rows]
    finally:
        if close:
            c.close()
    if target:
        t = target.lower()
        rules = [r for r in rules if r.target.lower().startswith(t)]
    if verdict:
        rules = [r for r in rules if r.verdict == normalize_verdict(verdict)]
    return rules


def update_rule(
    rule_id: str,
    verdict: str | None = None,
    note: str | None = None,
    evidence: list[Evidence] | None = None,
    proj: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Rule | None:
    """바꿀 항목만 넘긴다. evidence를 주면 근거 전체를 교체한다."""
    proj = proj or project_name()
    c, close = _connect(conn)
    try:
        if get_rule(rule_id, proj, c) is None:
            return None
        rid = rule_id.upper()
        if verdict is not None:
            c.execute("UPDATE trace_rule SET verdict = ? WHERE project = ? AND rule_id = ?", (normalize_verdict(verdict), proj, rid))
        if note is not None:
            c.execute("UPDATE trace_rule SET note = ? WHERE project = ? AND rule_id = ?", (note, proj, rid))
        if evidence is not None:
            _put_evidence(c, proj, rid, evidence)
        c.execute("UPDATE trace_rule SET updated_at = ? WHERE project = ? AND rule_id = ?", (_now(), proj, rid))
        c.commit()
        return get_rule(rid, proj, c)
    finally:
        if close:
            c.close()
