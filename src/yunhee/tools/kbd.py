"""매뉴얼 버튼 표기 판정 및 md 검사 도구 (`yunhee kbd`, 수정사항 076).

screen-capture --boxes 결과에 기록된 실제 브라우저 계산 스타일(`style`)과
A-Man `button-defines.json`을 비교하여 매뉴얼용 인라인 버튼 표기를 결정하고,
매뉴얼 마크다운의 버튼 표기를 검사·자동 수정한다.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from yunhee import config
from yunhee.tools.base import ToolResult

# Ant Design 아이콘 클래스 → FontAwesome 이름 기본 매핑 (TOBE 공통 버튼 전체)
DEFAULT_ICON_MAP: dict[str, str] = {
    "anticon-search": "search",
    "anticon-plus": "plus",
    "anticon-user-delete": "user-times",
    "anticon-mail": "envelope",
    "anticon-calculator": "calculator",
    "anticon-check": "check",
    "anticon-plus-square": "far fa-plus-square",
    "anticon-minus-square": "far fa-minus-square",
    "anticon-book": "bookmark",
    "anticon-minus": "minus",
    "anticon-delete": "trash",
    "anticon-stop": "ban",
    "anticon-swap": "exchange-alt",
    "anticon-upload": "upload",
    "anticon-download": "download",
    "anticon-eye": "eye",
    "anticon-arrow-right": "arrow-right",
    "anticon-team": "users",
    "anticon-printer": "print",
    "anticon-folder-add": "folder-plus",
    "anticon-undo": "undo-alt",
    "anticon-edit": "edit",
    "anticon-aim": "bullseye",
    "anticon-left-circle": "arrow-alt-circle-left",
    "anticon-setting": "cog",
}

DEFAULT_CACHE_PATH = Path.home() / ".yunhee" / "cache" / "button-defines.json"

# 색:아이콘:글자 형식 (아이콘은 빈 문자열 허용: 색::글자)
_DIRECT_NOTATION_RE = re.compile(r"^([0-9A-Fa-f]{6}):([^:]*):(.+)$")
# 펜스 코드 블록 시작/종료
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# 비버튼 판별용 패턴 (경로, URL, 코드 기호, 숫자만 등)
_PURE_NUMBER_RE = re.compile(r"^[\d\s.,:%+-]+$")
_NON_BUTTON_CHARS_RE = re.compile(r"[\\/{}()\[\]=<>`$|*#@;]")
_FILE_EXT_RE = re.compile(
    r"\.(?:tsx?|jsx?|java|xml|json|md|css|sql|png|jpg|pdf|sh|py|ya?ml|toml|csv|xlsx?)$",
    re.IGNORECASE,
)


def load_icon_map(override_path: str | Path | None = None) -> dict[str, str]:
    """기본 Ant Design → FontAwesome 매핑표에 사용자 JSON 오버라이드를 병합한다."""
    merged = dict(DEFAULT_ICON_MAP)
    raw_path = override_path if override_path is not None else config.KBD_ICON_MAP
    if raw_path:
        p = Path(str(raw_path)).expanduser()
        if not p.is_absolute():
            p = config.WORK_DIR / p
        if p.is_file():
            try:
                custom = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(custom, dict):
                    for k, v in custom.items():
                        if isinstance(k, str) and isinstance(v, str):
                            merged[k] = v
            except Exception:  # noqa: BLE001, S110
                pass
    return merged


def normalize_fa(icon: str | None) -> str | None:
    """A-Man icon 문자열에서 기본 `fas fa-` 접두사만 떼어 비교용 이름으로 정규화한다.

    `far fa-plus-square`처럼 `fas`가 아닌 아이콘은 접두사까지 유지한다.
    """
    if not icon:
        return None
    s = icon.strip()
    if not s:
        return None
    if s.startswith("fas fa-"):
        return s[len("fas fa-") :].strip()
    return s


@dataclass
class AmanButtonDef:
    color: str  # 6자리 대문자 HEX
    icon_raw: str  # 원본 icon (예: "fas fa-check")
    icon_norm: str  # 비교용 정규화 이름 (예: "check", "far fa-plus-square")
    text: str  # A-Man에 정의된 원문 글자


@dataclass
class AmanDefines:
    text_map: dict[str, AmanButtonDef]
    nospace_map: dict[str, AmanButtonDef]
    group_count: int
    text_count: int
    source: str
    used_cache: bool = False
    cache_date: str | None = None


def _parse_aman_defines_payload(
    payload: Any,
    source: str,
    used_cache: bool = False,
    cache_date: str | None = None,
) -> AmanDefines:
    if not isinstance(payload, list):
        raise TypeError(f"button-defines.json 형식이 배열이 아닙니다: {source}")

    text_map: dict[str, AmanButtonDef] = {}
    nospace_map: dict[str, AmanButtonDef] = {}

    for group in payload:
        if not isinstance(group, dict):
            continue
        color = str(group.get("color") or "").strip().lstrip("#").upper()
        icon_raw = str(group.get("icon") or "").strip()
        icon_norm = normalize_fa(icon_raw) or ""
        texts = group.get("texts") or []
        if not isinstance(texts, list):
            continue
        for t in texts:
            if not isinstance(t, str):
                continue
            label = t.strip()
            if not label:
                continue
            # A-Man L36-42 규칙: 같은 글자가 있으면 뒤 묶음이 이김
            entry = AmanButtonDef(
                color=color,
                icon_raw=icon_raw,
                icon_norm=icon_norm,
                text=label,
            )
            text_map[label] = entry
            nospace_map[label.replace(" ", "")] = entry

    return AmanDefines(
        text_map=text_map,
        nospace_map=nospace_map,
        group_count=len(payload),
        text_count=len(text_map),
        source=source,
        used_cache=used_cache,
        cache_date=cache_date,
    )


def load_aman_defines(
    defines: str | None = None,
    aman_url: str | None = None,
    cache_path: Path | None = None,
    timeout: float = 5.0,
) -> AmanDefines:
    """A-Man `button-defines.json`을 로드한다.

    우선순위:
    1. `--defines <URL|파일>`
    2. `YUNHEE_AMAN_URL` + `/button-defines.json`
    URL 로드 성공 시 `~/.yunhee/cache/button-defines.json`에 저장하고,
    서버 연결 실패 시 캐시 파일이 있으면 캐시를 사용한다.
    """
    cache_file = cache_path or DEFAULT_CACHE_PATH

    if defines:
        target = defines.strip()
        if not target.startswith(("http://", "https://")):
            p = Path(target).expanduser()
            if not p.is_absolute():
                p = config.WORK_DIR / p
            if not p.is_file():
                raise FileNotFoundError(f"정의 파일을 찾을 수 없습니다: {p}")
            payload = json.loads(p.read_text(encoding="utf-8"))
            return _parse_aman_defines_payload(payload, source=str(p))
        url = target
    else:
        base = (aman_url if aman_url is not None else config.AMAN_URL).strip().rstrip("/")
        if not base:
            base = "http://localhost:8081/aman"
        url = f"{base}/button-defines.json"

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        payload = resp.json()
        # 성공 시 캐시 갱신
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        return _parse_aman_defines_payload(payload, source=url, used_cache=False)
    except Exception as fetch_err:
        if cache_file.is_file():
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime, tz=UTC).astimezone().strftime("%Y-%m-%d")
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            return _parse_aman_defines_payload(
                payload,
                source=url,
                used_cache=True,
                cache_date=mtime,
            )
        raise RuntimeError(
            f"A-Man 버튼 정의를 불러올 수 없습니다 ({url}): {fetch_err}\n"
            f"캐시 파일({cache_file})도 존재하지 않습니다."
        ) from fetch_err


def _resolve_boxes_files(paths: list[str | Path]) -> list[Path]:
    """파일 또는 폴더 목록에서 `*.boxes.json` 파일 목록을 수집한다."""
    result: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = config.WORK_DIR / p
        if p.is_dir():
            files = sorted(p.glob("*.boxes.json"))
            for f in files:
                rf = f.resolve()
                if rf not in seen:
                    seen.add(rf)
                    result.append(f)
        elif p.is_file():
            rf = p.resolve()
            if rf not in seen:
                seen.add(rf)
                result.append(p)
        else:
            raise FileNotFoundError(f"경로를 찾을 수 없습니다: {p}")
    return result


def _clean_parent_label(parent: str | None) -> str:
    """`boxes.json`의 parent 값을 표기용 창 이름으로 정리한다."""
    if not parent:
        return "본 화면"
    # screen_capture.py가 붙이는 `(모달)` 접미사 정리 (예: "문서양식 등록(모달)" → "문서양식 등록")
    s = re.sub(r"\(모달\)(?:#\d+)?$", "", parent).strip()
    return s or "본 화면"


def _is_modal_close_x(elem: dict[str, Any], style: dict[str, Any]) -> bool:
    """모달 오른쪽 위 X 버튼(`ant-modal-close`)인지 판별한다.

    `screen_capture.py` L1950에서 이름/글자가 "닫기"로 기록되지만,
    실제 색이 없는(`style.bg is None`) 비글자 아이콘 X 버튼이다.
    """
    bg = style.get("bg")
    erp_classes = style.get("class") or []
    text = (elem.get("text") or "").strip()
    if bg is None and not erp_classes:
        if text == "닫기" and elem.get("area") in ("modal", "lookup"):
            return True
        if elem.get("kind") == "icon-button" and not text:
            return True
    return False


@dataclass
class CollectedButton:
    text: str
    parent: str  # "본 화면" 또는 모달 제목
    kind: str
    bg: str | None
    fg: str | None
    icon: str | None
    fa: str | None
    erp_classes: list[str]
    disabled_only: bool


def collect_buttons_from_boxes(
    paths: list[str | Path],
    icon_map: dict[str, str] | None = None,
) -> tuple[list[CollectedButton], str, int, int]:
    """`*.boxes.json`에서 버튼 스타일 정보를 수집·병합한다.

    Returns:
        (buttons, screen_label, file_count, missing_style_count)
    """
    files = _resolve_boxes_files(paths)
    if not files:
        raise FileNotFoundError("지정한 경로에서 *.boxes.json 파일을 찾을 수 없습니다.")

    imap = icon_map if icon_map is not None else load_icon_map()
    screens: list[str] = []
    # key = (text, parent_label) -> list of (disabled_bool, style_dict, kind)
    grouped: dict[tuple[str, str], list[tuple[bool, dict[str, Any], str]]] = {}
    order: list[tuple[str, str]] = []
    missing_style_count = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        scr = str(data.get("screen") or "").strip()
        if scr and scr not in screens:
            screens.append(scr)

        for elem in data.get("elements") or []:
            kind = elem.get("kind")
            if kind not in ("button", "icon-button"):
                continue

            style = elem.get("style")
            if not isinstance(style, dict):
                missing_style_count += 1
                continue

            if _is_modal_close_x(elem, style):
                continue

            text = str(elem.get("text") or elem.get("name") or "").strip()
            if not text:
                continue
            # 중복 접미사(#2 등)는 name에만 붙지만 혹시 icon-button name에 있으면 제거
            if not elem.get("text"):
                text = re.sub(r"#\d+$", "", text).strip()

            parent_label = _clean_parent_label(elem.get("parent"))
            disabled = bool(elem.get("disabled", False))
            key = (text, parent_label)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append((disabled, style, kind))

    buttons: list[CollectedButton] = []
    for key in order:
        text, parent_label = key
        entries = grouped[key]
        # 켜짐(disabled=False)이 하나라도 있으면 첫 번째 켜진 것 사용
        enabled_entries = [e for e in entries if not e[0]]
        if enabled_entries:
            _, style, kind = enabled_entries[0]
            disabled_only = False
        else:
            _, style, kind = entries[0]
            disabled_only = True

        bg = style.get("bg")
        if isinstance(bg, str):
            bg = bg.lstrip("#").upper() or None
        fg = style.get("fg")
        if isinstance(fg, str):
            fg = fg.lstrip("#").upper() or None
        icon = style.get("icon") or None

        # fa 계산: icon이 있으면 현재 icon_map(사용자 오버라이드 포함) 우선, 없으면 style.fa
        if icon and icon in imap:
            fa: str | None = imap[icon]
        elif style.get("fa"):
            fa = normalize_fa(str(style.get("fa")))
        else:
            fa = None

        erp_classes = [str(c) for c in (style.get("class") or [])]

        buttons.append(
            CollectedButton(
                text=text,
                parent=parent_label,
                kind=kind,
                bg=bg,
                fg=fg,
                icon=icon,
                fa=fa,
                erp_classes=erp_classes,
                disabled_only=disabled_only,
            )
        )

    screen_label = ", ".join(screens) if screens else (Path(paths[0]).name if paths else "")
    return buttons, screen_label, len(files), missing_style_count


def _judge_button(btn: CollectedButton, defines: AmanDefines) -> dict[str, Any]:
    """단일 버튼의 TOBE 스타일과 A-Man 정의를 비교해 판정·표기를 생성한다."""
    # 글자 찾기: 정확 일치 → 공백 제거 일치
    aman_def: AmanButtonDef | None = defines.text_map.get(btn.text)
    matched_by_nospace = False
    if aman_def is None:
        aman_def = defines.nospace_map.get(btn.text.replace(" ", ""))
        if aman_def is not None:
            matched_by_nospace = True

    display_text = aman_def.text if (aman_def is not None and matched_by_nospace) else btn.text
    bg = btn.bg
    fa = btn.fa

    # 판정
    note: str | None = None
    if fa is None:
        verdict = "아이콘없음"
        notation = f"`{bg or ''}::{display_text}`"
        if btn.icon:
            note = f"⚠{btn.icon}"
    elif aman_def is None:
        verdict = "A-Man없음"
        notation = f"`{bg or ''}:{fa}:{display_text}`"
    else:
        same_bg = (bg or "").upper() == aman_def.color.upper()
        same_fa = fa == aman_def.icon_norm
        if same_bg and same_fa:
            verdict = "같음"
            notation = f"`{display_text}`"
        elif not same_bg and same_fa:
            verdict = "색다름"
            notation = f"`{bg or ''}:{fa}:{display_text}`"
        elif same_bg and not same_fa:
            verdict = "아이콘다름"
            notation = f"`{bg or ''}:{fa}:{display_text}`"
        else:
            verdict = "둘다다름"
            notation = f"`{bg or ''}:{fa}:{display_text}`"

    verdict_display = f"{verdict} ⚠꺼짐" if btn.disabled_only else verdict

    return {
        "text": btn.text,
        "display_text": display_text,
        "parent": btn.parent,
        "tobe": {"bg": bg, "fa": fa, "icon": btn.icon},
        "aman": (
            {"color": aman_def.color, "icon": aman_def.icon_norm}
            if aman_def is not None
            else None
        ),
        "verdict": verdict,
        "verdict_display": verdict_display,
        "notation": notation,
        "notation_inner": notation.strip("`"),
        "disabled_only": btn.disabled_only,
        "note": note,
    }


def evaluate_buttons(
    paths: list[str | Path],
    defines: str | None = None,
    aman_url: str | None = None,
    icon_map_path: str | Path | None = None,
    cache_path: Path | None = None,
) -> ToolResult:
    """boxes.json 파일/폴더에서 버튼을 모아 A-Man 정의와 대조한 결과를 반환한다."""
    try:
        imap = load_icon_map(icon_map_path)
        buttons, screen_label, file_count, missing_style_count = collect_buttons_from_boxes(
            paths, icon_map=imap
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))

    if not buttons and missing_style_count > 0:
        return ToolResult(
            ok=False,
            error=(
                f"boxes.json({file_count}개)에 버튼 style 정보가 없습니다 ({missing_style_count}개 버튼). "
                "최신 `yunhee screen-capture --boxes`로 다시 캡처하세요."
            ),
        )

    try:
        aman_defs = load_aman_defines(
            defines=defines,
            aman_url=aman_url,
            cache_path=cache_path,
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))

    rows = [_judge_button(btn, aman_defs) for btn in buttons]

    return ToolResult(
        ok=True,
        data={
            "screen": screen_label,
            "file_count": file_count,
            "missing_style_count": missing_style_count,
            "aman_groups": aman_defs.group_count,
            "aman_texts": aman_defs.text_count,
            "aman_source": aman_defs.source,
            "used_cache": aman_defs.used_cache,
            "cache_date": aman_defs.cache_date,
            "rows": rows,
        },
    )


def format_kbd_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    """`--json` 출력 규격에 맞춘 배열을 생성한다."""
    out: list[dict[str, Any]] = []
    for r in data.get("rows") or []:
        item: dict[str, Any] = {
            "text": r["text"],
            "parent": r["parent"],
            "tobe": {"bg": r["tobe"]["bg"], "fa": r["tobe"]["fa"]},
            "aman": r["aman"],
            "verdict": r["verdict"],
            "notation": r["notation"],
        }
        if r.get("disabled_only"):
            item["disabled_only"] = True
        if r.get("note"):
            item["note"] = r["note"]
        out.append(item)
    return out


def render_kbd_markdown(data: dict[str, Any]) -> str:
    """버튼 표기 판정 결과를 마크다운 표로 렌더링한다."""
    screen = data.get("screen") or "-"
    groups = data.get("aman_groups", 0)
    texts = data.get("aman_texts", 0)
    source = data.get("aman_source", "")
    cache_suffix = ""
    if data.get("used_cache"):
        cache_suffix = f", 캐시 사용({data.get('cache_date') or '날짜미상'})"

    lines = [
        f"### 버튼 표기 ({screen}, A-Man 정의 {groups}묶음·{texts}글자, {source}{cache_suffix})",
        "| 버튼 | 창 | TOBE | A-Man | 판정 | 표기 |",
        "|:---|:---|:---|:---|:---|:---|",
    ]
    for r in data.get("rows") or []:
        tobe_bg = r["tobe"]["bg"] or "-"
        tobe_fa = r["tobe"]["fa"] or "-"
        tobe_str = f"{tobe_bg} {tobe_fa}"
        aman = r["aman"]
        aman_str = f"{aman['color']} {aman['icon']}" if aman else "-"
        notation_cell = r["notation"]
        if r.get("note") and r["verdict"] == "아이콘없음":
            notation_cell = f"{notation_cell} {r['note']}"
        lines.append(
            f"| {r['text']} | {r['parent']} | {tobe_str} | {aman_str} | {r['verdict_display']} | {notation_cell} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Part C: 매뉴얼 md 검사 및 자동 수정 (`--check` / `--fix`)
# ---------------------------------------------------------------------------


@dataclass
class InlineCodeSpan:
    line_no: int  # 1-based
    start: int  # 여는 백틱 인덱스
    end: int  # 닫는 백틱 다음 인덱스
    inner: str  # 백틱 안쪽 원문
    label: str  # 비교 대상 버튼 글자 (`색:아이콘:글자`면 글자만)


def extract_md_inline_codes(md_text: str) -> list[InlineCodeSpan]:
    """마크다운에서 펜스 코드 블록을 제외하고 단일 백틱 인라인 코드 스팬을 모두 추출한다."""
    spans: list[InlineCodeSpan] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for idx, line in enumerate(md_text.splitlines(), start=1):
        m_fence = _FENCE_RE.match(line)
        if m_fence:
            token = m_fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = token[0]
                fence_len = len(token)
            elif token[0] == fence_char and len(token) >= fence_len:
                in_fence = False
            continue
        if in_fence:
            continue

        # 한 줄에서 단일 백틱 쌍 스캔 (이중 백틱 ``...`` 및 이스케이프 \` 제외)
        pos = 0
        n = len(line)
        while pos < n:
            ch = line[pos]
            if ch == "\\":
                pos += 2
                continue
            if ch == "`":
                # 연속 백틱 길이 확인
                run_end = pos
                while run_end < n and line[run_end] == "`":
                    run_end += 1
                run_len = run_end - pos
                if run_len == 1:
                    # 닫는 단일 백틱 탐색
                    close_pos = line.find("`", run_end)
                    if close_pos != -1 and (close_pos + 1 >= n or line[close_pos + 1] != "`"):
                        inner = line[run_end:close_pos]
                        if inner.strip():
                            dm = _DIRECT_NOTATION_RE.match(inner)
                            label = dm.group(3) if dm else inner
                            spans.append(
                                InlineCodeSpan(
                                    line_no=idx,
                                    start=pos,
                                    end=close_pos + 1,
                                    inner=inner,
                                    label=label,
                                )
                            )
                        pos = close_pos + 1
                        continue
                else:
                    # 다중 백틱 코드 스팬은 끝까지 건너뜀
                    closing = line.find("`" * run_len, run_end)
                    if closing != -1:
                        pos = closing + run_len
                        continue
                pos = run_end
                continue
            pos += 1

    return spans


def _looks_like_button(label: str) -> bool:
    """표 B에 없는 인라인 코드가 버튼 이름처럼 보이는지 판별한다."""
    s = label.strip()
    if not s:
        return False
    if len(s) > 20:
        return False
    if _PURE_NUMBER_RE.match(s):
        return False
    if _NON_BUTTON_CHARS_RE.search(s):
        return False
    if _FILE_EXT_RE.search(s):
        return False
    if s.startswith(("http:", "https:", "--", "-")):
        return False
    # 공백 없는 순수 영문 식별자(snake_case, camelCase 등 코드 토큰)는 제외
    return "_" not in s


def check_manual_md(
    md_path: str | Path,
    boxes_paths: list[str | Path],
    defines: str | None = None,
    aman_url: str | None = None,
    icon_map_path: str | Path | None = None,
    cache_path: Path | None = None,
    fix: bool = False,
) -> ToolResult:
    """매뉴얼 md 파일의 인라인 버튼 표기를 boxes.json 판정표와 대조하여 검사·수정한다."""
    mp = Path(md_path).expanduser()
    if not mp.is_absolute():
        mp = config.WORK_DIR / mp
    if not mp.is_file():
        return ToolResult(ok=False, error=f"매뉴얼 파일을 찾을 수 없습니다: {mp}")

    eval_res = evaluate_buttons(
        paths=boxes_paths,
        defines=defines,
        aman_url=aman_url,
        icon_map_path=icon_map_path,
        cache_path=cache_path,
    )
    if not eval_res.ok or not isinstance(eval_res.data, dict):
        return eval_res

    rows = eval_res.data["rows"]

    # B 표에서 글자 → 표기 집합(창별) 구축
    exact_map: dict[str, list[dict[str, Any]]] = {}
    nospace_map: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        for key_text in {r["text"], r["display_text"]}:
            exact_map.setdefault(key_text, []).append(r)
            nospace_map.setdefault(key_text.replace(" ", ""), []).append(r)

    original_text = mp.read_text(encoding="utf-8")
    spans = extract_md_inline_codes(original_text)

    findings: list[dict[str, Any]] = []
    passed = 0
    mismatches = 0
    missing = 0
    ambiguous = 0
    icon_unknown = 0

    # --fix용 줄별 치환 목록: line_no -> list of (start, end, new_text)
    replacements_by_line: dict[int, list[tuple[int, int, str]]] = {}

    for sp in spans:
        matched_rows = exact_map.get(sp.label)
        if not matched_rows:
            matched_rows = nospace_map.get(sp.label.replace(" ", ""))

        if matched_rows:
            unique_notations = list(dict.fromkeys(r["notation_inner"] for r in matched_rows))
            if len(unique_notations) > 1:
                ambiguous += 1
                detail = ", ".join(
                    f"{r['parent']}=`{r['notation_inner']}`" for r in matched_rows
                )
                findings.append(
                    {
                        "status": "ambiguous",
                        "line": sp.line_no,
                        "current": sp.inner,
                        "expected": None,
                        "message": f"⚠ L{sp.line_no} `{sp.inner}` — 창마다 다름 ({detail})",
                    }
                )
                continue

            if any(r["verdict"] == "아이콘없음" for r in matched_rows):
                icon_unknown += 1
                row = next(r for r in matched_rows if r["verdict"] == "아이콘없음")
                tobe_bg = (row["tobe"]["bg"] or "").upper()
                tobe_icon = row["tobe"].get("icon") or "아이콘없음"
                dm = _DIRECT_NOTATION_RE.match(sp.inner)
                if dm and dm.group(2).strip():
                    md_color = dm.group(1).upper()
                    if tobe_bg and md_color == tobe_bg:
                        msg = (
                            f"⚠ L{sp.line_no} `{sp.inner}` — "
                            f"아이콘 확인(TOBE {tobe_icon}, 변환표에 없음)"
                        )
                    else:
                        msg = (
                            f"⚠ L{sp.line_no} `{sp.inner}` — "
                            f"아이콘 확인(TOBE {tobe_icon}, 변환표에 없음) · 색은 {tobe_bg or '-'}"
                        )
                else:
                    tobe_desc = " ".join(p for p in (tobe_bg, tobe_icon) if p)
                    msg = (
                        f"⚠ L{sp.line_no} `{sp.inner}` — "
                        f"아이콘 확인(TOBE {tobe_desc}, 변환표에 없음)"
                    )
                findings.append(
                    {
                        "status": "icon-unknown",
                        "line": sp.line_no,
                        "current": sp.inner,
                        "expected": None,
                        "message": msg,
                    }
                )
                continue

            expected_inner = unique_notations[0]
            if sp.inner == expected_inner:
                passed += 1
            else:
                mismatches += 1
                findings.append(
                    {
                        "status": "mismatch",
                        "line": sp.line_no,
                        "current": sp.inner,
                        "expected": expected_inner,
                        "message": f"❌ L{sp.line_no} `{sp.inner}` → `{expected_inner}`",
                    }
                )
                if fix:
                    replacements_by_line.setdefault(sp.line_no, []).append(
                        (sp.start, sp.end, f"`{expected_inner}`")
                    )
        else:
            if not _looks_like_button(sp.label):
                continue
            missing += 1
            findings.append(
                {
                    "status": "missing",
                    "line": sp.line_no,
                    "current": sp.inner,
                    "expected": None,
                    "message": f"⚠ L{sp.line_no} `{sp.inner}` — 캡처에 없는 버튼(확인창 등)",
                }
            )

    fixed_count = 0
    backup_path: str | None = None
    if fix and replacements_by_line:
        bak = Path(f"{mp}.bak")
        shutil.copy2(mp, bak)
        backup_path = str(bak)

        lines = original_text.splitlines(keepends=True)
        for line_no, reps in replacements_by_line.items():
            line_idx = line_no - 1
            line_str = lines[line_idx]
            # 뒤에서 앞으로 치환해야 앞쪽 오프셋이 밀리지 않음
            for start, end, new_val in sorted(reps, key=lambda x: x[0], reverse=True):
                line_str = line_str[:start] + new_val + line_str[end:]
                fixed_count += 1
            lines[line_idx] = line_str
        mp.write_text("".join(lines), encoding="utf-8")

    total = passed + mismatches + missing + ambiguous + icon_unknown
    return ToolResult(
        ok=True,
        data={
            "md_path": str(mp),
            "used_cache": eval_res.data["used_cache"],
            "cache_date": eval_res.data["cache_date"],
            "aman_source": eval_res.data["aman_source"],
            "total": total,
            "passed": passed,
            "mismatches": mismatches,
            "missing": missing,
            "ambiguous": ambiguous,
            "icon_unknown": icon_unknown,
            "fixed_count": fixed_count,
            "backup_path": backup_path,
            "findings": findings,
        },
    )


def render_check_report(data: dict[str, Any]) -> str:
    """`--check` 결과를 사람이 읽기 좋은 텍스트로 포맷한다."""
    lines: list[str] = []
    if data.get("used_cache"):
        lines.append(f"ℹ A-Man 캐시 사용({data.get('cache_date') or '날짜미상'})")
    for f in data.get("findings") or []:
        lines.append(f["message"])

    total = data["total"]
    passed = data["passed"]
    mismatches = data["mismatches"]
    missing = data["missing"]
    ambiguous = data.get("ambiguous", 0)
    icon_unknown = data.get("icon_unknown", 0)

    summary = f"버튼 표기 {total}개: 통과 {passed} · 고칠 것 {mismatches} · 캡처에 없음 {missing}"
    if ambiguous:
        summary += f" · 창마다 다름 {ambiguous}"
    if icon_unknown:
        summary += f" · 아이콘 확인 {icon_unknown}"
    lines.append(summary)

    if data.get("fixed_count"):
        lines.append(
            f"✔ {data['fixed_count']}곳 수정 완료 (백업: {data['backup_path']})"
        )
    return "\n".join(lines)
