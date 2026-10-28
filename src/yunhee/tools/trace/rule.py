"""trace-rule: 에이전트가 내린 판정(규칙)의 저장·조회와 근거 검증.

근거는 `파일:줄`(`Emp00_Tab_TransInfo.java:418`, `…:394-432`), 파일 전체, 또는 mapper id(`emp00_trans_info.selectByText`,
TOBE는 `EmpTransInfoMapper.searchTransInfos`)다. `add`는 근거를 **그 자리에서 읽어 존재를 확인**하고(없으면 거부) 내용의
정규화 해시를 저장한다. `verify`는 같은 위치를 다시 읽어 판정한다.

  OK       내용이 저장 시점과 같음
  MOVED    내용은 같은데 줄 번호만 바뀜 (코드가 위에서 늘거나 줄어든 경우)
  STALE    내용이 바뀜 — 규칙을 다시 확인해야 한다
  MISSING  파일·줄·mapper 문장이 없어짐 (또는 처음부터 없던 근거)

줄 번호만이 아니라 **내용**으로 판정하므로, 서식 변경은 STALE로 보지 않는다 (공백 정규화, mapper는 `normalize_sql_for_drift`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from yunhee import config
from yunhee.store import trace_rules as store
from yunhee.store.trace_rules import Evidence, Rule
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext
from yunhee.tools.trace.tobe import build_index, find_layout

ACTIONS = ("add", "list", "show", "update", "verify")
SEVERITY = {"OK": 0, "MOVED": 1, "STALE": 2, "MISSING": 3}
_FILE_REF = re.compile(r"^(?P<path>.+?):(?P<a>\d+)(?:-(?P<b>\d+))?$")
_MAPPER_REF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_FILE_EXT = (".java", ".tsx", ".ts", ".xml", ".md", ".sql", ".json", ".properties", ".css")
MAX_EXCERPT = 4000  # 이보다 긴 근거는 해시로만 비교한다 (내용을 찾아 이동을 추적하지 못함)


@dataclass
class Roots:
    asis_app: Path | None
    asis_src: Path | None
    tobe: Path | None
    work: Path

    def candidates(self, side: str) -> list[Path]:
        pool = {"asis": [self.asis_app, self.asis_src], "tobe": [self.tobe], "work": [self.work]}[side]
        return [p for p in pool if p is not None and p.is_dir()]


@dataclass
class Check:
    status: str  # OK / MOVED / STALE / MISSING
    detail: str = ""
    new_line: int | None = None
    new_end: int | None = None


def make_roots(ctx: TraceContext, tobe: Path | None = None) -> Roots:
    from yunhee.tools.as_is.src_indexer import find_app

    src = Path(ctx.src_root) if ctx.src_root and Path(ctx.src_root).is_dir() else None
    layout = find_layout(tobe)
    return Roots(find_app(src) if src else None, src, layout.root if layout.usable else None, config.WORK_DIR)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _collapse(lines: list[str], a: int, b: int) -> str:
    """a~b줄(1부터)의 본문. 빈 줄·공백은 무시해, 서식 변경과 빈 줄 추가·삭제를 내용 변경으로 보지 않는다."""
    return _norm("\n".join(lines[a - 1 : b]))


def _locate(lines: list[str], excerpt: str, near: int) -> tuple[int, int] | None:
    """저장한 본문(excerpt)이 파일 어디에 있는지 (시작 줄, 끝 줄). 여러 곳이면 near에 가까운 곳. 줄 경계에 맞는 일치만 인정한다."""
    rows = [(i + 1, _norm(t)) for i, t in enumerate(lines) if t.strip()]
    blob = " ".join(t for _, t in rows)
    starts, pos = [], 0
    for _, t in rows:
        starts.append(pos)
        pos += len(t) + 1
    found: list[tuple[int, int]] = []
    at = blob.find(excerpt)
    while at >= 0:
        end = at + len(excerpt)
        if at in starts and (end == len(blob) or end in [x - 1 for x in starts]):
            first = starts.index(at)
            last = max(i for i, st in enumerate(starts) if st < end)
            found.append((rows[first][0], rows[last][0]))
        at = blob.find(excerpt, at + 1)
    return min(found, key=lambda f: abs(f[0] - near)) if found else None

def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 근거 만들기
# ---------------------------------------------------------------------------


def _find_file(name: str, roots: Roots, ctx: TraceContext) -> tuple[str, Path, Path]:
    """(side, 파일, 그 side의 루트). 경로가 상대·이름만이어도 ASIS 색인과 TOBE 소스에서 찾는다."""
    p = Path(name)
    if p.is_absolute() and p.is_file():
        for side in ("tobe", "asis", "work"):
            for root in roots.candidates(side):
                if root in p.parents:
                    return side, p, root
        return "work", p, p.parent
    for side in ("asis", "tobe", "work"):
        for root in roots.candidates(side):
            if (root / p).is_file():
                return side, root / p, root
    stem = p.name.rsplit(".", 1)[0] if "." in p.name else p.name
    found: list[tuple[str, Path, Path]] = []
    idx_data = ctx.index_data or {}
    for kind in ("client_classes", "server_classes"):
        rel = idx_data.get(kind, {}).get(stem, {}).get("file")
        if rel and p.suffix in ("", ".java"):
            for root in roots.candidates("asis"):
                if (root / rel).is_file():
                    found.append(("asis", root / rel, root))
    if roots.tobe is not None and p.suffix in ("", ".tsx"):
        tsx = build_index(str(roots.tobe)).tsx.get(stem)
        if tsx:
            found.append(("tobe", Path(tsx.file), roots.tobe))
    if not found:  # 마지막으로 파일 이름이 같은 파일이 하나뿐일 때
        for side in ("asis", "tobe"):
            for root in roots.candidates(side)[:1]:
                hits = [h for h in root.rglob(p.name) if "target" not in h.parts and "node_modules" not in h.parts and "build" not in h.parts][:6]
                found += [(side, h, root) for h in hits]
    unique = list({str(f[1]): f for f in found}.values())
    if len(unique) == 1:
        return unique[0]
    if not unique:
        raise ValueError(f"파일을 찾지 못함: {name} (ASIS 소스·TOBE 소스·작업 폴더에서 찾았다)")
    raise ValueError(f"파일 이름이 모호함: {name} — 경로를 포함해 적으세요. 후보: " + ", ".join(str(f[1]) for f in unique[:5]))


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _mapper_text(path: Path, sid: str) -> str | None:
    """mapper XML에서 id가 sid인 select/insert/update/delete 문장의 원문."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf'<(select|insert|update|delete)\b[^>]*\bid="{re.escape(sid)}"[^>]*>.*?</\1>', text, re.DOTALL | re.IGNORECASE)
    return m.group(0) if m else None


def _statement_hash(slice_: str) -> tuple[str, str]:
    from yunhee.tools.as_is.sql_drift import normalize_sql_for_drift

    norm = normalize_sql_for_drift(slice_)
    return norm[:MAX_EXCERPT], _hash(norm)


def _find_statement(ref: str, roots: Roots, ctx: TraceContext) -> tuple[str, str, Path, int, str, str, str]:
    """(side, key, xml 파일, 줄, 종류, id, 루트). ASIS `ns.id` 또는 TOBE `Mapper.id`."""
    hits: list[tuple[str, str, Path, int, str, str, str]] = []
    if roots.asis_src is not None:
        from yunhee.tools.as_is.mybatis_render import get_all_statements

        st = get_all_statements(roots.asis_src).get(ref)
        if st is not None and st.kind != "sql":
            app = roots.asis_app or roots.asis_src
            hits.append(("asis", st.key, app / st.rel, st.line, st.kind, st.sid, str(app)))
    if roots.tobe is not None:
        idx = build_index(str(roots.tobe))
        for key, ms in idx.statements.items():
            if key == ref or key.endswith("." + ref):
                hits.append(("tobe", key, Path(ms.file), ms.line, ms.kind, ms.id, str(roots.tobe)))
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"mapper 문장을 찾지 못함: {ref} (ASIS는 `namespace.id`, TOBE는 `Mapper클래스.id`)")
    raise ValueError(f"mapper id가 모호함: {ref} — 후보: " + ", ".join(f"{h[0]}:{h[1]}" for h in hits[:5]))


def build_evidence(ref: str, roots: Roots, ctx: TraceContext) -> Evidence:
    """근거 원문(`파일:줄`, `파일`, mapper id)을 읽어 존재를 확인하고 해시를 만든다. 없으면 ValueError."""
    ref = ref.strip()
    m = _FILE_REF.match(ref)
    if m is None and _MAPPER_REF.match(ref) and not ref.lower().endswith(_FILE_EXT):
        side, key, xml, line, _kind, sid, root = _find_statement(ref, roots, ctx)
        sl = _mapper_text(xml, sid)
        if sl is None:
            raise ValueError(f"mapper 문장 본문을 읽지 못함: {ref} ({xml})")
        excerpt, h = _statement_hash(sl)
        return Evidence("mapper", side, ref, str(xml.relative_to(root)), line, None, key, excerpt, h)

    name, a, b = (m["path"], int(m["a"]), int(m["b"] or m["a"])) if m else (ref, None, None)
    side, path, root = _find_file(name, roots, ctx)
    rel = str(path.relative_to(root)) if root in path.parents else str(path)
    lines = _read_lines(path)
    if a is None:
        body = _norm("\n".join(lines))
        return Evidence("file", side, ref, rel, None, None, "", body[:MAX_EXCERPT], _hash(body))
    if a < 1 or b < a or b > len(lines):
        raise ValueError(f"{path.name}은 {len(lines)}줄인데 L{a}-{b}를 가리킴: {ref}")
    body = _collapse(lines, a, b)
    if not body:
        raise ValueError(f"{path.name}:{a}-{b}는 빈 줄 — 근거로 쓸 내용이 없음: {ref}")
    return Evidence("file", side, ref, rel, a, b, "", body[:MAX_EXCERPT], _hash(body))


# ---------------------------------------------------------------------------
# 근거 검증
# ---------------------------------------------------------------------------


def _abs(e: Evidence, roots: Roots) -> Path | None:
    p = Path(e.path)
    if p.is_absolute():
        return p if p.is_file() else None
    for root in roots.candidates(e.side):
        if (root / p).is_file():
            return root / p
    return None


def check_evidence(e: Evidence, roots: Roots, ctx: TraceContext) -> Check:
    if e.kind == "mapper":
        path = _abs(e, roots)
        if path is None:
            return Check("MISSING", f"mapper 파일이 없음: {e.path}")
        sl = _mapper_text(path, e.anchor.rsplit(".", 1)[-1])
        if sl is None:
            return Check("MISSING", f"문장 {e.anchor}이(가) 없어짐 ({e.path})")
        return Check("OK") if _statement_hash(sl)[1] == e.hash else Check("STALE", f"문장 {e.anchor}의 SQL이 바뀜")

    path = _abs(e, roots)
    if path is None:
        return Check("MISSING", f"파일이 없음: {e.path} ({e.side})" + ("" if _side_available(e.side, roots) else " — 해당 소스 위치를 찾지 못해 확인 불가"))
    lines = _read_lines(path)
    if e.line is None:  # 파일 전체
        body = _norm("\n".join(lines))
        return Check("OK") if _hash(body) == e.hash else Check("STALE", "파일 내용이 바뀜")
    end = e.line_end or e.line
    if e.line <= len(lines) and _hash(_collapse(lines, e.line, min(end, len(lines)))) == e.hash:
        return Check("OK")
    # 같은 내용이 다른 줄로 옮겨졌는지: 저장한 위치에 가장 가까운 일치를 찾는다 (줄이 늘거나 줄거나 빈 줄이 끼어도 된다)
    if len(e.excerpt) < MAX_EXCERPT:
        hit = _locate(lines, e.excerpt, e.line)
        if hit:
            a, b = hit
            return Check("MOVED", f"L{e.line}-{end} → L{a}-{b}", a, b)
    if e.line > len(lines):
        return Check("MISSING", f"줄이 없어짐: {path.name}은 {len(lines)}줄 (근거 L{e.line})")
    return Check("STALE", f"{path.name}:{e.line}의 내용이 바뀜")


def _side_available(side: str, roots: Roots) -> bool:
    return bool(roots.candidates(side))


def _refreshed(e: Evidence, c: Check, roots: Roots, ctx: TraceContext) -> Evidence:
    """--accept용 새 근거. MOVED는 내용이 같으니 새 위치로 옮기고, STALE은 같은 위치를 다시 읽는다. OK는 그대로 둔다."""
    if c.status == "OK":
        return e
    if c.status == "MOVED" and e.kind == "file" and c.new_line:
        path_part = _FILE_REF.match(e.ref)["path"] if _FILE_REF.match(e.ref) else e.ref
        return build_evidence(f"{path_part}:{c.new_line}-{c.new_end or c.new_line}", roots, ctx)
    return build_evidence(e.ref, roots, ctx)


def verify_rule(rule: Rule, roots: Roots, ctx: TraceContext) -> tuple[str, list[tuple[Evidence, Check]]]:
    if not rule.evidence:
        return "MISSING", []
    checks = [(e, check_evidence(e, roots, ctx)) for e in rule.evidence]
    worst = max((c.status for _, c in checks), key=lambda s: SEVERITY[s])
    return worst, checks


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------


def _fmt_rule(r: Rule) -> str:
    return f"{r.rule_id} [{r.verdict}] {r.target}" + (f" — {r.note}" if r.note else "") + f" (근거 {len(r.evidence)}건)"


def _fmt_evidence(e: Evidence) -> str:
    where = f"{e.path}:{e.line}" + (f"-{e.line_end}" if e.line_end and e.line_end != e.line else "") if e.line else e.path
    return f"{e.side} {where}" + (f" ({e.anchor})" if e.anchor else "")


def run_rule(
    action: str,
    target: str | None,
    ctx: TraceContext,
    tobe: Path | None = None,
    note: str | None = None,
    verdict: str | None = None,
    evidence: list[str] | None = None,
    accept: bool = False,
) -> tuple[TraceResult, int]:
    """trace-rule 실행. 반환: (결과, 종료 코드). verify에서 MISSING·STALE이 있으면 종료 코드 1."""
    res = TraceResult(
        command="trace-rule", description="규칙 저장·조회와 근거 검증", side="both",
        params={"action": action, "target": target, "verdict": verdict, "evidence": evidence or []},
    )
    action = action.lower()
    if action not in ACTIONS:
        raise ValueError(f"동작은 {', '.join(ACTIONS)} 중 하나여야 합니다: {action}")
    proj = store.project_name()
    res.params["project"] = proj
    roots = make_roots(ctx, tobe)

    if action == "add":
        if not target:
            raise ValueError("add: 대상(화면ID·클래스·mapper id 등)이 필요합니다 — trace-rule add <대상> --verdict … --note … --evidence …")
        if verdict is None:
            raise ValueError(f"add: --verdict가 필요합니다 ({', '.join(store.VERDICTS)})")
        built = [build_evidence(r, roots, ctx) for r in (evidence or [])]  # 없는 근거는 여기서 ValueError로 거부된다
        rule = store.add_rule(target, verdict, note or "", built, proj)
        res.facts.append(f"규칙 저장: {_fmt_rule(rule)}")
        res.evidence += [_fmt_evidence(e) for e in rule.evidence]
        if not built:
            res.unresolved.append(f"{rule.rule_id}: 근거(--evidence)가 없어 trace-rule verify로 확인할 수 없음")
        return res, 0

    if action == "list":
        rules = store.list_rules(target, proj, verdict)
        res.facts.append(f"규칙 {len(rules)}건" + (f" (대상 '{target}')" if target else "") + (f" [{verdict}]" if verdict else ""))
        res.facts += [_fmt_rule(r) for r in rules]
        return res, 0

    if action in ("show", "update", "verify") and target and re.fullmatch(r"[Rr]-\d+", target):
        rule = store.get_rule(target, proj)
        if rule is None:
            raise ValueError(f"규칙 {target.upper()}을(를) 찾지 못함 (프로젝트 {proj})")
        rules = [rule]
    elif action == "verify":
        rules = store.list_rules(target, proj)
    elif action in ("show", "update"):
        raise ValueError(f"{action}: 규칙 ID가 필요합니다 (예: R-001) — `trace-rule list`로 확인")
    else:
        rules = []

    if action == "show":
        r = rules[0]
        res.facts.append(f"{r.rule_id} [{r.verdict}] {r.target}")
        res.facts.append(f"사유: {r.note or '(없음)'}")
        res.facts.append(f"저장: {r.created_at} / 수정: {r.updated_at}")
        res.facts.append("근거:\n" + ("\n".join(f"  - {e.ref} → {_fmt_evidence(e)}" for e in r.evidence) or "  (없음)"))
        res.evidence += [_fmt_evidence(e) for e in r.evidence]
        return res, 0

    if action == "update":
        r = rules[0]
        built = [build_evidence(x, roots, ctx) for x in evidence] if evidence else None
        updated = store.update_rule(r.rule_id, verdict, note, built, proj)
        res.facts.append(f"규칙 수정: {_fmt_rule(updated)}" + (" — 근거를 교체함" if built is not None else ""))
        return res, 0

    # verify
    counts = {k: 0 for k in SEVERITY}
    lines: list[str] = []
    if not rules:
        res.facts.append("검증할 규칙이 없음" + (f" (대상 '{target}')" if target else ""))
        return res, 0
    for r in rules:
        status, checks = verify_rule(r, roots, ctx)
        if accept and status in ("MOVED", "STALE") and len(rules) == 1:
            fresh = [_refreshed(e, c, roots, ctx) for e, c in checks]
            store.update_rule(r.rule_id, evidence=fresh, proj=proj)
            lines.append(f"{r.rule_id} {status} → 근거를 현재 내용으로 갱신함 (--accept): {r.target}")
            status = "OK"
            checks = []
        counts[status] += 1
        if checks or not r.evidence:
            block = [f"{r.rule_id} {status} [{r.verdict}] {r.target}"]
            block += [f"    {c.status:<7} {e.ref}" + (f" — {c.detail}" if c.detail else "") for e, c in checks]
            if not r.evidence:
                block.append("    (근거가 없어 확인할 수 없음)")
            lines.append("\n".join(block))
        for e, c in checks:
            if c.status != "OK":
                res.evidence.append(f"{c.status} {_fmt_evidence(e)}")
    res.facts.append("검증 결과: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" (규칙 {len(rules)}건)")
    res.facts += lines
    for side in ("asis", "tobe"):
        if any(e.side == side for r in rules for e in r.evidence) and not roots.candidates(side):
            res.unresolved.append(f"{side.upper()} 소스 위치를 찾지 못해 해당 근거는 확인할 수 없음 (--src / --tobe)")
    return res, (1 if counts["MISSING"] or counts["STALE"] else 0)

