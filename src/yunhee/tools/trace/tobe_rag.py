"""TOBE 에이전트 RAG 학습·색인·검색 엔진 (rag-index, rag-reset, rag-status, rag-search, lookup_tobe).

실행 위치(yunhee-cli 폴더 vs 대상 프로젝트 폴더)에 구애받지 않도록 항상 `config.TOBE_SRC_DIR`
(또는 `--tobe` 인자)를 기준으로 스냅샷(`TOBE_SRC_DIR/.yunhee/tobe_catalog.json`),
마크다운 색인(`TOBE_SRC_DIR/docs/to-be/`), ChromaDB 컬렉션(`yunhee_tobe_kb`)을 관리한다.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yunhee.store.vectorstore import delete_collection, get_collection
from yunhee.tools.trace import screen_catalog
from yunhee.tools.trace.resolve import load_context
from yunhee.tools.trace.screen_catalog import (
    ScreenRecord,
    _collect_tobe_tsx_files,
    _load_full_menu_map,
    get_catalog_snapshot_path,
    iter_screens,
)
from yunhee.tools.trace.tobe import TobeLayout, find_layout

logger = logging.getLogger(__name__)

TOBE_RAG_COLLECTION_NAME = "yunhee_tobe_kb"
MANUAL_KB_COLLECTION_NAME = "yunhee_knowledge"
TOBE_DOC_ID_PREFIX = "TOBE_SCREEN_"


def get_tobe_rag_collection():
    """ChromaDB의 TOBE 자동 학습 컬렉션(yunhee_tobe_kb) 반환."""
    return get_collection(name=TOBE_RAG_COLLECTION_NAME)


def _build_menus_summary(
    layout: TobeLayout,
    screens: list[ScreenRecord],
) -> list[dict[str, Any]]:
    """menus.tsv의 전체 메뉴와 TOBE 화면 매핑 상태를 결합한다."""
    ctx = load_context("tobe")
    menu_map = _load_full_menu_map(ctx, layout)
    by_name = {s.name: s for s in screens if s.side == "tobe"}
    by_menu_no: dict[str, ScreenRecord] = {}
    for s in screens:
        if s.side == "tobe" and s.menu_no and (s.menu_no not in by_menu_no or s.role == "Tab"):
            by_menu_no[s.menu_no] = s

    menus_list: list[dict[str, Any]] = []
    seen_nos: set[str] = set()
    for asis_screen, entries in menu_map.items():
        for no, full_path, leaf, active in entries:
            if not no or no in seen_nos:
                continue
            seen_nos.add(no)
            tobe_rec = by_name.get(asis_screen) or by_menu_no.get(no)
            menus_list.append(
                {
                    "no": no,
                    "path": full_path,
                    "name": leaf,
                    "asis_screen": asis_screen,
                    "active": active,
                    "migrated": tobe_rec is not None,
                    "tobe_screen": tobe_rec.name if tobe_rec else "",
                    "tobe_file": tobe_rec.file if tobe_rec else "",
                    "page_style": tobe_rec.page_style if tobe_rec else "",
                    "backend_files": tobe_rec.backend_files if tobe_rec else [],
                }
            )
    menus_list.sort(key=lambda m: (int(m["no"]) if str(m["no"]).isdigit() else 999999, str(m["no"])))
    return menus_list


def _write_tobe_markdown_docs(
    layout: TobeLayout,
    screens: list[ScreenRecord],
    menus: list[dict[str, Any]],
) -> Path:
    """TOBE_SRC_DIR/docs/to-be/ 아래에 menus.md 및 도메인별 마크다운 요약본을 생성한다."""
    docs_dir = layout.root / "docs" / "to-be"
    domains_dir = docs_dir / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)

    # 1. docs/to-be/menus.md
    lines = [
        "# TOBE 메뉴 및 화면 파일 매핑 색인",
        "",
        "| 메뉴번호 | 메뉴 경로 | 상태 | TOBE 화면명 | 프론트엔드 파일 경로 | 스타일 | 백엔드 파일 수 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for m in menus:
        status = "✔ TOBE" if m["migrated"] else "⏳ 미변환(AS-IS)"
        scr = f"`{m['tobe_screen']}`" if m["tobe_screen"] else f"`{m['asis_screen']}` (AS-IS)"
        fpath = f"`{m['tobe_file']}`" if m["tobe_file"] else "-"
        style = m["page_style"] or "-"
        be_cnt = str(len(m["backend_files"])) if m["migrated"] else "-"
        lines.append(f"| #{m['no']} | {m['path']} | {status} | {scr} | {fpath} | {style} | {be_cnt} |")
    (docs_dir / "menus.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 2. docs/to-be/domains/{domain}.md
    by_domain: dict[str, list[ScreenRecord]] = {}
    for s in screens:
        if s.side != "tobe":
            continue
        m_dom = re.match(r"^([A-Za-z]{2,5})\d{2}_", s.name)
        dom = m_dom.group(1).lower() if m_dom else "common"
        by_domain.setdefault(dom, []).append(s)

    for dom, dom_screens in sorted(by_domain.items()):
        d_lines = [
            f"# TOBE `{dom}` 도메인 화면·컴포넌트 색인 ({len(dom_screens)}개)",
            "",
        ]
        for s in dom_screens:
            d_lines.append(f"## {s.name}")
            d_lines.append(s.to_card_text())
            d_lines.append("")
        (domains_dir / f"{dom}.md").write_text("\n".join(d_lines), encoding="utf-8")

    return docs_dir


def build_and_save_tobe_snapshot(
    tobe: Path | str | None = None,
    write_docs: bool = True,
) -> dict[str, Any]:
    """TOBE 전체 소스를 스캔하여 .yunhee/tobe_catalog.json 스냅샷과 docs/to-be/ 문서를 생성한다."""
    layout = find_layout(Path(tobe) if tobe else None)
    snap_path = get_catalog_snapshot_path(layout)

    # 기존 스냅샷을 우회해 실제 소스에서 새로 빌드하도록 임시 제거 후 캐시 초기화
    if snap_path.is_file():
        snap_path.unlink()
    screen_catalog._cached_catalog.cache_clear()

    screens = iter_screens(side="tobe", tobe=layout.root)
    menus = _build_menus_summary(layout, screens)

    snap_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "version": 1,
        "indexed_at": now_iso,
        "tobe_root": str(layout.root),
        "screen_count": len(screens),
        "menu_count": len(menus),
        "migrated_menu_count": sum(1 for m in menus if m["migrated"]),
        "screens": [s.to_dict() for s in screens],
        "menus": menus,
    }
    snap_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    screen_catalog._cached_catalog.cache_clear()

    docs_dir = None
    if write_docs and layout.usable:
        docs_dir = _write_tobe_markdown_docs(layout, screens, menus)

    return {
        "ok": True,
        "tobe_root": str(layout.root),
        "snapshot_path": str(snap_path),
        "docs_dir": str(docs_dir) if docs_dir else "",
        "indexed_at": now_iso,
        "screen_count": len(screens),
        "menu_count": len(menus),
        "migrated_menu_count": payload["migrated_menu_count"],
        "screens": screens,
        "menus": menus,
    }


def rag_index(
    tobe: Path | str | None = None,
    no_vector: bool = False,
    reset: bool = False,
    reset_all: bool = False,
) -> dict[str, Any]:
    """TOBE 프로젝트 증분(또는 초기화 후) RAG 학습을 수행한다."""
    t0 = time.monotonic()
    layout = find_layout(Path(tobe) if tobe else None)
    snap_path = get_catalog_snapshot_path(layout)
    docs_dir = layout.root / "docs" / "to-be"

    if reset or reset_all:
        delete_collection(TOBE_RAG_COLLECTION_NAME)
        if reset_all:
            delete_collection(MANUAL_KB_COLLECTION_NAME)
        if snap_path.is_file():
            snap_path.unlink()
        if docs_dir.is_dir():
            shutil.rmtree(docs_dir, ignore_errors=True)

    snap_res = build_and_save_tobe_snapshot(tobe=layout.root, write_docs=True)
    screens: list[ScreenRecord] = snap_res["screens"]

    upserted = 0
    skipped = 0
    deleted = 0
    vector_total = 0
    vector_error = ""

    if not no_vector and screens:
        try:
            col = get_tobe_rag_collection()
            existing = col.get(include=["metadatas"])
            existing_ids: list[str] = existing.get("ids") or []
            existing_metas: list[dict[str, Any]] = existing.get("metadatas") or []
            hash_by_id: dict[str, str] = {}
            for doc_id, meta in zip(existing_ids, existing_metas):
                if meta and "content_hash" in meta:
                    hash_by_id[doc_id] = str(meta["content_hash"])

            current_ids: set[str] = set()
            to_upsert_ids: list[str] = []
            to_upsert_docs: list[str] = []
            to_upsert_metas: list[dict[str, Any]] = []

            for s in screens:
                doc_id = f"{TOBE_DOC_ID_PREFIX}{s.name}"
                current_ids.add(doc_id)
                c_hash = s.content_hash or s.compute_hash()
                if not (reset or reset_all) and hash_by_id.get(doc_id) == c_hash:
                    skipped += 1
                    continue
                to_upsert_ids.append(doc_id)
                to_upsert_docs.append(s.to_card_text())
                to_upsert_metas.append(
                    {
                        "name": s.name,
                        "file": s.file,
                        "menu_no": s.menu_no or "",
                        "menu_path": s.menu_path or "",
                        "role": s.role or "",
                        "page_style": s.page_style or "",
                        "content_hash": c_hash,
                    }
                )

            stale_ids = [eid for eid in existing_ids if eid not in current_ids]
            if stale_ids:
                col.delete(ids=stale_ids)
                deleted = len(stale_ids)

            batch_size = 32
            for i in range(0, len(to_upsert_ids), batch_size):
                col.upsert(
                    ids=to_upsert_ids[i : i + batch_size],
                    documents=to_upsert_docs[i : i + batch_size],
                    metadatas=to_upsert_metas[i : i + batch_size],
                )
            upserted = len(to_upsert_ids)
            vector_total = col.count()
        except Exception as e:  # noqa: BLE001
            logger.warning("ChromaDB 벡터 학습 중 오류: %s", e)
            vector_error = str(e)

    elapsed = round(time.monotonic() - t0, 2)
    return {
        "ok": True,
        "tobe_root": snap_res["tobe_root"],
        "snapshot_path": snap_res["snapshot_path"],
        "docs_dir": snap_res["docs_dir"],
        "indexed_at": snap_res["indexed_at"],
        "screen_count": snap_res["screen_count"],
        "menu_count": snap_res["menu_count"],
        "migrated_menu_count": snap_res["migrated_menu_count"],
        "no_vector": no_vector,
        "upserted": upserted,
        "skipped": skipped,
        "deleted": deleted,
        "vector_total": vector_total,
        "vector_error": vector_error,
        "elapsed_sec": elapsed,
    }


def rag_reset(
    tobe: Path | str | None = None,
    reset_all: bool = False,
    reindex: bool = True,
) -> dict[str, Any]:
    """TOBE RAG 컬렉션과 스냅샷을 완전히 초기화하고 필요 시 재학습한다."""
    layout = find_layout(Path(tobe) if tobe else None)
    snap_path = get_catalog_snapshot_path(layout)
    docs_dir = layout.root / "docs" / "to-be"

    deleted_tobe_col = delete_collection(TOBE_RAG_COLLECTION_NAME)
    deleted_manual_col = delete_collection(MANUAL_KB_COLLECTION_NAME) if reset_all else False

    if snap_path.is_file():
        snap_path.unlink()
    if docs_dir.is_dir():
        shutil.rmtree(docs_dir, ignore_errors=True)
    screen_catalog._cached_catalog.cache_clear()

    if reindex:
        res = rag_index(tobe=layout.root, reset=False, reset_all=False)
        res["reset_performed"] = True
        res["deleted_tobe_collection"] = deleted_tobe_col
        res["deleted_manual_collection"] = deleted_manual_col
        return res

    return {
        "ok": True,
        "reset_performed": True,
        "reindexed": False,
        "tobe_root": str(layout.root),
        "deleted_tobe_collection": deleted_tobe_col,
        "deleted_manual_collection": deleted_manual_col,
    }


def rag_status(tobe: Path | str | None = None) -> dict[str, Any]:
    """현재 TOBE RAG 학습 상태 및 디스크 변경(Stale) 파일 건수를 점검한다."""
    layout = find_layout(Path(tobe) if tobe else None)
    snap_path = get_catalog_snapshot_path(layout)
    tsx_files = _collect_tobe_tsx_files(layout)

    snap_exists = snap_path.is_file()
    indexed_at = ""
    screen_count = 0
    menu_count = 0
    migrated_menu_count = 0
    added_files: list[str] = []
    modified_files: list[str] = []
    deleted_files: list[str] = []

    if snap_exists:
        try:
            data = json.loads(snap_path.read_text(encoding="utf-8"))
            indexed_at = data.get("indexed_at", "")
            raw_screens = data.get("screens", [])
            screen_count = len(raw_screens)
            menu_count = int(data.get("menu_count", 0))
            migrated_menu_count = int(data.get("migrated_menu_count", 0))

            by_stem = {item["name"]: item for item in raw_screens}
            disk_stems = {p.stem for p in tsx_files}
            for p in tsx_files:
                item = by_stem.get(p.stem)
                if not item:
                    added_files.append(p.name)
                elif abs(p.stat().st_mtime - float(item.get("mtime", 0.0))) > 0.01:
                    modified_files.append(p.name)
            for stem_name, item in by_stem.items():
                if stem_name not in disk_stems:
                    deleted_files.append(item.get("file", stem_name))
        except Exception as e:  # noqa: BLE001
            logger.warning("스냅샷 상태 읽기 실패: %s", e)

    tobe_vector_count = 0
    manual_vector_count = 0
    chroma_ok = True
    chroma_error = ""
    try:
        tobe_vector_count = get_tobe_rag_collection().count()
        manual_vector_count = get_collection(name=MANUAL_KB_COLLECTION_NAME).count()
    except Exception as e:  # noqa: BLE001
        chroma_ok = False
        chroma_error = str(e)

    stale_count = len(added_files) + len(modified_files) + len(deleted_files)
    return {
        "tobe_root": str(layout.root),
        "snapshot_path": str(snap_path),
        "snapshot_exists": snap_exists,
        "indexed_at": indexed_at,
        "disk_tsx_count": len(tsx_files),
        "indexed_screen_count": screen_count,
        "menu_count": menu_count,
        "migrated_menu_count": migrated_menu_count,
        "stale_count": stale_count,
        "added_files": added_files,
        "modified_files": modified_files,
        "deleted_files": deleted_files,
        "chroma_ok": chroma_ok,
        "chroma_error": chroma_error,
        "tobe_vector_count": tobe_vector_count,
        "manual_vector_count": manual_vector_count,
    }


def _load_menus_from_snapshot(layout: TobeLayout) -> list[dict[str, Any]]:
    snap_path = get_catalog_snapshot_path(layout)
    if snap_path.is_file():
        try:
            data = json.loads(snap_path.read_text(encoding="utf-8"))
            if "menus" in data:
                return data["menus"]
        except Exception as e:  # noqa: BLE001
            logger.debug("스냅샷 메뉴 읽기 무시: %s", e)
    screens = iter_screens(side="tobe", tobe=layout.root)
    return _build_menus_summary(layout, screens)


def find_deterministic_matches(
    query: str,
    tobe: Path | str | None = None,
    max_cards: int = 5,
) -> list[str]:
    """질문에서 화면번호(#1002), 화면/컴포넌트 코드, 메뉴명, API, 테이블명을 결정적으로 찾아 카드를 반환한다."""
    clean = query.strip()
    if not clean:
        return []

    layout = find_layout(Path(tobe) if tobe else None)
    screens = iter_screens(side="tobe", tobe=layout.root)
    if not screens:
        return []

    cards: list[str] = []
    seen_names: set[str] = set()

    def _add_screen(s: ScreenRecord) -> None:
        if s.name not in seen_names and len(cards) < max_cards:
            seen_names.add(s.name)
            cards.append(s.to_card_text())

    # 1. 4자리 메뉴 번호 매칭 (예: "1002", "#1002", "1029번")
    menu_nos = re.findall(r"#?(\b\d{4}\b)", clean)
    for mno in menu_nos:
        matched_for_no = [s for s in screens if s.menu_no == mno]
        # 메인 Tab 화면을 먼저 넣고, 하위 컴포넌트를 이어서 추가
        matched_for_no.sort(key=lambda s: (0 if s.role == "Tab" else 1, s.name))
        if matched_for_no:
            for s in matched_for_no:
                _add_screen(s)
        else:
            # 미변환 메뉴인지 확인
            for m in _load_menus_from_snapshot(layout):
                if m.get("no") == mno:
                    cards.append(
                        f"[메뉴 #{mno} | {m.get('path', '')} | ⏳ TOBE 미변환]\n"
                        f"- 상태: TOBE에 아직 변환된 화면 파일이 없습니다.\n"
                        f"- AS-IS 원본 화면 클래스: {m.get('asis_screen', '-')}"
                    )
                    break

    # 2. 화면/컴포넌트 영문 식별자 매칭 (예: Dcr01_Tab_DcrUser, Ics01_Edit_ClassTree, Dcr01)
    comp_tokens = re.findall(r"\b([A-Za-z]{2,5}\d{2}(?:_[A-Za-z0-9_]+)?)\b", clean)
    for tok in comp_tokens:
        tok_low = tok.lower()
        for s in screens:
            if s.name.lower() == tok_low or s.name.lower().startswith(tok_low + "_"):
                _add_screen(s)

    # 3. API URL 또는 테이블명 매칭
    api_tokens = re.findall(r"(/api/v\d+/[\w/-]+)", clean)
    for api_tok in api_tokens:
        for s in screens:
            if any(api_tok in a for a in s.apis):
                _add_screen(s)

    table_tokens = re.findall(r"\b([a-z]{2,5}\d{2}_[a-z0-9_]+)\b", clean.lower())
    for tbl in table_tokens:
        for s in screens:
            if tbl in s.tables or any(tbl in sid.lower() for sid in s.sql_ids):
                _add_screen(s)

    # 4. 메뉴명/모달명 직접 포함 매칭 (예: "업무별 문서작성 화면", "사원정보 관리")
    if len(cards) < max_cards:
        for s in screens:
            if (
                s.role == "Tab"
                and s.menu_name
                and len(s.menu_name) >= 3
                and (s.menu_name in clean or s.menu_name.replace(" ", "") in clean.replace(" ", ""))
            ):
                _add_screen(s)

    return cards


def rag_search(
    query: str,
    limit: int = 5,
    max_distance: float = 0.75,
    tobe: Path | str | None = None,
) -> dict[str, Any]:
    """결정적 카탈로그 매칭 + ChromaDB 벡터 검색을 결합한 하이브리드 검색 결과를 반환한다."""
    det_cards = find_deterministic_matches(query, tobe=tobe, max_cards=limit)
    vec_hits: list[dict[str, Any]] = []
    vec_error = ""

    try:
        col = get_tobe_rag_collection()
        cnt = col.count()
        if cnt > 0:
            res = col.query(query_texts=[query.strip()], n_results=min(limit, cnt))
            docs = res.get("documents", [[]])[0]
            dists = res.get("distances", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            for doc, dist, meta in zip(docs, dists, metas):
                if dist is not None and dist > max_distance:
                    continue
                vec_hits.append(
                    {
                        "name": (meta or {}).get("name", ""),
                        "menu_no": (meta or {}).get("menu_no", ""),
                        "file": (meta or {}).get("file", ""),
                        "distance": round(float(dist), 4) if dist is not None else None,
                        "document": doc,
                    }
                )
    except Exception as e:  # noqa: BLE001
        vec_error = str(e)

    return {
        "query": query,
        "deterministic_cards": det_cards,
        "vector_hits": vec_hits,
        "vector_error": vec_error,
    }


def lookup_tobe(query: str, tobe: Path | str | None = None) -> str:
    """에이전트 전용 만능 TOBE 조회 도구.

    화면번호('1002'), 메뉴명('업무별 문서작성'), 컴포넌트명('Ics01_Edit_ClassTree'),
    API 경로('/api/v1/...'), 테이블명('ics01_class_tree') 등을 받아 관련 TOBE 화면·파일·백엔드 정보를 반환한다.
    """
    res = rag_search(query, limit=5, tobe=tobe)
    blocks: list[str] = []
    seen_docs: set[str] = set()

    for card in res["deterministic_cards"]:
        if card not in seen_docs:
            seen_docs.add(card)
            blocks.append(card)

    for hit in res["vector_hits"]:
        doc = hit["document"]
        if doc not in seen_docs and len(blocks) < 6:
            seen_docs.add(doc)
            blocks.append(doc)

    # 만약 결정적 매칭/벡터 매칭이 없으면 부분 문자열로 한 번 더 탐색
    if not blocks:
        q_low = query.strip().lower().lstrip("#")
        for s in iter_screens(side="tobe", tobe=tobe):
            if (
                q_low in s.name.lower()
                or q_low == s.menu_no
                or q_low in s.menu_path.lower()
                or any(q_low in m.title.lower() for m in s.modals)
            ):
                card = s.to_card_text()
                if card not in seen_docs:
                    seen_docs.add(card)
                    blocks.append(card)
                if len(blocks) >= 5:
                    break

    if not blocks:
        return f"'{query}'에 일치하는 TOBE 화면/컴포넌트/메뉴 정보를 찾지 못했습니다."

    return f"[TOBE 조회 결과: '{query}' ({len(blocks)}건)]\n\n" + "\n\n".join(blocks)


def prefetch_tobe_rag(
    query: str,
    limit: int = 3,
    max_distance: float = 0.52,
    enable_vector: bool = True,
) -> str:
    """에이전트 루프 시작 전 질문과 연관된 TOBE 학습 카드를 자동 소환한다."""
    clean = query.strip()
    if not clean or len(clean) < 2:
        return ""

    det_cards = find_deterministic_matches(clean, max_cards=4)
    vec_cards: list[str] = []

    if enable_vector and len(det_cards) < 2:
        try:
            col = get_tobe_rag_collection()
            cnt = col.count()
            if cnt > 0:
                res = col.query(query_texts=[clean], n_results=min(limit, cnt))
                docs = res.get("documents", [[]])[0]
                dists = res.get("distances", [[]])[0]
                for doc, dist in zip(docs, dists):
                    if dist is not None and dist <= max_distance and doc not in det_cards:
                        vec_cards.append(doc)
        except Exception as e:  # noqa: BLE001
            logger.debug("prefetch_tobe_rag 벡터 검색 무시: %s", e)

    all_cards = det_cards + vec_cards
    if not all_cards:
        return ""

    return (
        "[참고 가능한 TOBE 화면·API·백엔드 학습 지식 (TOBE RAG — 아래 팩트로 바로 답변 가능하면 도구를 호출하지 말고 즉시 답변하세요)]\n"
        + "\n\n".join(all_cards[:4])
        + "\n\n"
    )

