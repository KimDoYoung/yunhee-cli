"""수정사항 076 (`yunhee kbd` — 버튼 표기 판정 및 매뉴얼 md 검사·수정) 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.kbd import (
    check_manual_md,
    evaluate_buttons,
    extract_md_inline_codes,
    format_kbd_json,
    load_aman_defines,
    load_icon_map,
    normalize_fa,
    render_check_report,
    render_kbd_markdown,
)

SAMPLE_AMAN_DEFINES = [
    {"color": "456EA6", "icon": "fas fa-search", "texts": ["조회"]},
    {"color": "17A2B8", "icon": "fas fa-check", "texts": ["저장"]},
    {"color": "E89646", "icon": "fas fa-eye", "texts": ["구분추가"]},
    {"color": "2EAC7E", "icon": "fas fa-plus", "texts": ["등록", "행 추가"]},
    {"color": "DD5E5E", "icon": "fas fa-minus", "texts": ["행 삭제"]},
    {"color": "3B82F6", "icon": "far fa-plus-square", "texts": ["전체열기"]},
]


def _write_sample_boxes(tmp_path: Path) -> Path:
    src_dir = tmp_path / "1007_Dcr05_Tab_DocType"
    src_dir.mkdir(parents=True)

    # 01_initial.boxes.json (본 화면)
    box1 = {
        "version": 1,
        "image": "01_initial.png",
        "image-size": [1920, 1080],
        "viewport": [1920, 1080],
        "scale": 1.0,
        "origin": [0, 0],
        "screen": "1007",
        "elements": [
            {
                "name": "조회",
                "kind": "button",
                "text": "조회",
                "box": [100, 50, 70, 32],
                "area": "main",
                "style": {
                    "bg": "456EA6",
                    "fg": "FFFFFF",
                    "icon": "anticon-search",
                    "fa": "search",
                    "class": ["erp-btn", "erp-btn-type-search"],
                },
            },
            {
                "name": "구분추가",
                "kind": "button",
                "text": "구분추가",
                "box": [180, 50, 90, 32],
                "area": "main",
                "style": {
                    "bg": "6AB6CF",
                    "fg": "FFFFFF",
                    "icon": "anticon-eye",
                    "fa": "eye",
                    "class": ["erp-btn", "erp-btn-type-view"],
                },
            },
            {
                # 공백 없는 '행추가' -> A-Man '행 추가'와 공백 제거 매칭
                "name": "행추가",
                "kind": "button",
                "text": "행추가",
                "box": [280, 50, 80, 32],
                "area": "main",
                "style": {
                    "bg": "2EAC7E",
                    "fg": "FFFFFF",
                    "icon": "anticon-plus",
                    "fa": "plus",
                    "class": ["erp-btn", "erp-btn-type-addRow"],
                },
            },
            {
                # 꺼진 상태만 존재하는 버튼
                "name": "승인요청",
                "kind": "button",
                "text": "승인요청",
                "box": [370, 50, 90, 32],
                "area": "main",
                "disabled": True,
                "style": {
                    "bg": "D9D9D9",
                    "fg": "8C8C8C",
                    "icon": "anticon-check",
                    "fa": "check",
                    "class": ["erp-btn", "erp-btn-type-save"],
                },
            },
            {
                # 표에 없는 아이콘
                "name": "특수기능",
                "kind": "button",
                "text": "특수기능",
                "box": [470, 50, 90, 32],
                "area": "main",
                "style": {
                    "bg": "123456",
                    "fg": "FFFFFF",
                    "icon": "anticon-rocket",
                    "fa": None,
                    "class": ["erp-btn"],
                },
            },
        ],
    }

    # 02_popup.boxes.json (모달: 저장 꺼짐/켜짐 공존, 모달 우상단 X 버튼 포함, 푸터 닫기 버튼 포함)
    box2 = {
        "version": 1,
        "image": "02_popup.png",
        "image-size": [1920, 1080],
        "viewport": [1920, 1080],
        "scale": 1.0,
        "origin": [0, 0],
        "screen": "1007",
        "elements": [
            {
                # 꺼진 저장 (먼저 나옴)
                "name": "저장",
                "kind": "button",
                "text": "저장",
                "box": [800, 800, 76, 32],
                "area": "modal",
                "parent": "문서양식 등록(모달)",
                "disabled": True,
                "style": {
                    "bg": "CCCCCC",
                    "fg": "888888",
                    "icon": "anticon-check",
                    "fa": "check",
                    "class": ["erp-btn", "erp-btn-type-save"],
                },
            },
            {
                # 켜진 저장 (나중에 나옴 -> 켜진 것 우선)
                "name": "저장#2",
                "kind": "button",
                "text": "저장",
                "box": [880, 883, 76, 32],
                "area": "modal",
                "parent": "문서양식 등록(모달)",
                "disabled": False,
                "style": {
                    "bg": "0F7F90",
                    "fg": "FFFFFF",
                    "icon": "anticon-check",
                    "fa": "check",
                    "class": ["erp-btn", "erp-btn-mint", "erp-btn-type-save"],
                },
            },
            {
                # 모달 우상단 X 버튼 -> 제외되어야 함
                "name": "닫기",
                "kind": "button",
                "text": "닫기",
                "box": [950, 200, 24, 24],
                "area": "modal",
                "parent": "문서양식 등록(모달)",
                "style": {
                    "bg": None,
                    "fg": "666666",
                    "icon": "anticon-close",
                    "fa": None,
                    "class": [],
                },
            },
            {
                # 실제 모달 푸터 닫기 버튼 -> 유지되어야 함
                "name": "닫기#2",
                "kind": "button",
                "text": "닫기",
                "box": [960, 883, 76, 32],
                "area": "modal",
                "parent": "문서양식 등록(모달)",
                "style": {
                    "bg": "E89646",
                    "fg": "FFFFFF",
                    "icon": "anticon-stop",
                    "fa": "ban",
                    "class": ["erp-btn", "erp-btn-type-close"],
                },
            },
        ],
    }

    (src_dir / "01_initial.boxes.json").write_text(
        json.dumps(box1, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (src_dir / "02_popup.boxes.json").write_text(
        json.dumps(box2, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return src_dir


def test_normalize_fa_and_icon_map_override(tmp_path: Path):
    assert normalize_fa("fas fa-check") == "check"
    assert normalize_fa("far fa-plus-square") == "far fa-plus-square"
    assert normalize_fa(None) is None

    custom_map = tmp_path / "icons.json"
    custom_map.write_text(
        json.dumps({"anticon-rocket": "rocket", "anticon-check": "check-double"}),
        encoding="utf-8",
    )
    merged = load_icon_map(custom_map)
    assert merged["anticon-rocket"] == "rocket"
    assert merged["anticon-check"] == "check-double"
    assert merged["anticon-search"] == "search"


def test_aman_defines_cache_fallback(tmp_path: Path, monkeypatch):
    cache_file = tmp_path / "cache" / "button-defines.json"

    # 1. 서버 성공 -> 캐시 저장
    class _OkResp:
        def raise_for_status(self):
            return None

        def json(self):
            return SAMPLE_AMAN_DEFINES

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _OkResp())
    defs1 = load_aman_defines(aman_url="http://localhost:8081/aman", cache_path=cache_file)
    assert defs1.used_cache is False
    assert defs1.group_count == len(SAMPLE_AMAN_DEFINES)
    assert cache_file.is_file()

    # 2. 서버 꺼짐 -> 캐시 폴백 및 날짜 안내
    def _fail_get(*a, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _fail_get)
    defs2 = load_aman_defines(aman_url="http://localhost:8081/aman", cache_path=cache_file)
    assert defs2.used_cache is True
    assert defs2.cache_date is not None
    assert "조회" in defs2.text_map


def test_evaluate_buttons_all_verdicts(tmp_path: Path):
    src_dir = _write_sample_boxes(tmp_path)
    def_file = tmp_path / "button-defines.json"
    def_file.write_text(json.dumps(SAMPLE_AMAN_DEFINES, ensure_ascii=False), encoding="utf-8")

    res = evaluate_buttons([src_dir], defines=str(def_file))
    assert res.ok
    rows = { (r["text"], r["parent"]): r for r in res.data["rows"] }

    # 같음
    r_search = rows[("조회", "본 화면")]
    assert r_search["verdict"] == "같음"
    assert r_search["notation"] == "`조회`"

    # 색다름 (구분추가)
    r_view = rows[("구분추가", "본 화면")]
    assert r_view["verdict"] == "색다름"
    assert r_view["notation"] == "`6AB6CF:eye:구분추가`"

    # 공백 무시 매칭 -> A-Man 글자('행 추가') 사용
    r_add = rows[("행추가", "본 화면")]
    assert r_add["verdict"] == "같음"
    assert r_add["notation"] == "`행 추가`"

    # 켜짐/꺼짐 공존 -> 켜진 색(0F7F90) 사용
    r_save = rows[("저장", "문서양식 등록")]
    assert r_save["disabled_only"] is False
    assert r_save["tobe"]["bg"] == "0F7F90"
    assert r_save["verdict"] == "색다름"
    assert r_save["notation"] == "`0F7F90:check:저장`"

    # 꺼짐만 존재 -> ⚠꺼짐, 색 추측 금지(D9D9D9 그대로)
    r_dis = rows[("승인요청", "본 화면")]
    assert r_dis["disabled_only"] is True
    assert r_dis["tobe"]["bg"] == "D9D9D9"
    assert "⚠꺼짐" in r_dis["verdict_display"]

    # 표에 없는 아이콘 -> 아이콘없음 + ⚠anticon-rocket
    r_noicon = rows[("특수기능", "본 화면")]
    assert r_noicon["verdict"] == "아이콘없음"
    assert r_noicon["notation"] == "`123456::특수기능`"
    assert r_noicon["note"] == "⚠anticon-rocket"

    # 모달 X 버튼 제외되고 실제 닫기 버튼만 남음
    r_close = rows[("닫기", "문서양식 등록")]
    assert r_close["tobe"]["bg"] == "E89646"
    assert r_close["verdict"] == "A-Man없음"
    assert r_close["notation"] == "`E89646:ban:닫기`"

    md = render_kbd_markdown(res.data)
    assert "### 버튼 표기 (1007," in md
    assert "| 저장 | 문서양식 등록 | 0F7F90 check | 17A2B8 check | 색다름 | `0F7F90:check:저장` |" in md

    js = format_kbd_json(res.data)
    assert any(item["text"] == "저장" and item["notation"] == "`0F7F90:check:저장`" for item in js)


def test_check_and_fix_manual_md(tmp_path: Path):
    src_dir = _write_sample_boxes(tmp_path)
    def_file = tmp_path / "button-defines.json"
    def_file.write_text(json.dumps(SAMPLE_AMAN_DEFINES, ensure_ascii=False), encoding="utf-8")

    md_file = tmp_path / "1007_manual.md"
    md_content = (
        "# 1007 문서양식등록\n"
        "1. `조회`를 누른다.\n"
        "2. `구분추가`를 눌러 항목을 추가하고 `저장`을 클릭한다.\n"
        "3. 확인창에서 `예`를 누른다.\n"
        "4. 코드 예시: `src/App.tsx`, `12345`, `매우 긴 설명 문구라서 버튼이 절대 아닐 것 같은 문자열입니다`.\n"
        "```bash\n"
        "echo `저장` # 펜스 코드 블록 안은 무시\n"
        "```\n"
        "5. 끝낼 때는 `E89646:ban:닫기`를 누른다.\n"
    )
    md_file.write_text(md_content, encoding="utf-8")

    # 1. --check (수정 없음)
    res = check_manual_md(md_file, [src_dir], defines=str(def_file), fix=False)
    assert res.ok
    d = res.data
    assert d["passed"] == 2  # 조회, E89646:ban:닫기
    assert d["mismatches"] == 2  # 구분추가, 저장
    assert d["missing"] == 1  # 예
    report = render_check_report(d)
    assert "❌ L3 `구분추가` → `6AB6CF:eye:구분추가`" in report
    assert "❌ L3 `저장` → `0F7F90:check:저장`" in report
    assert "⚠ L4 `예` — 캡처에 없는 버튼" in report
    assert "버튼 표기 5개: 통과 2 · 고칠 것 2 · 캡처에 없음 1" in report

    # 2. --fix (백업 생성 및 ❌만 치환, ⚠ 및 펜스 내부는 유지)
    res_fix = check_manual_md(md_file, [src_dir], defines=str(def_file), fix=True)
    assert res_fix.ok
    assert res_fix.data["fixed_count"] == 2
    bak_file = Path(f"{md_file}.bak")
    assert bak_file.is_file()
    assert bak_file.read_text(encoding="utf-8") == md_content

    updated = md_file.read_text(encoding="utf-8")
    assert "`6AB6CF:eye:구분추가`" in updated
    assert "`0F7F90:check:저장`" in updated
    assert "확인창에서 `예`를 누른다." in updated
    assert "echo `저장` # 펜스 코드 블록 안은 무시" in updated

    # 3. 재검사 시 통과 4 · 고칠 것 0 · 캡처에 없음 1
    res_after = check_manual_md(md_file, [src_dir], defines=str(def_file), fix=False)
    assert res_after.ok
    assert res_after.data["mismatches"] == 0
    assert res_after.data["passed"] == 4
    assert res_after.data["missing"] == 1


def test_check_ambiguous_button_across_windows(tmp_path: Path):
    """같은 글자가 창마다 다른 색이면 '⚠ 창마다 다름'으로 알리고 --fix에서도 고치지 않는다."""
    boxes_file = tmp_path / "ambig.boxes.json"
    boxes_file.write_text(
        json.dumps(
            {
                "version": 1,
                "screen": "9999",
                "elements": [
                    {
                        "name": "닫기",
                        "kind": "button",
                        "text": "닫기",
                        "box": [0, 0, 50, 30],
                        "area": "main",
                        "style": {"bg": "111111", "fg": "FFFFFF", "icon": "anticon-stop", "fa": "ban", "class": ["erp-btn"]},
                    },
                    {
                        "name": "닫기",
                        "kind": "button",
                        "text": "닫기",
                        "box": [0, 0, 50, 30],
                        "area": "modal",
                        "parent": "팝업A(모달)",
                        "style": {"bg": "E89646", "fg": "FFFFFF", "icon": "anticon-stop", "fa": "ban", "class": ["erp-btn"]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    def_file = tmp_path / "defines.json"
    def_file.write_text(json.dumps(SAMPLE_AMAN_DEFINES, ensure_ascii=False), encoding="utf-8")

    md_file = tmp_path / "m.md"
    md_file.write_text("창을 닫으려면 `닫기`를 누른다.\n", encoding="utf-8")

    res = check_manual_md(md_file, [boxes_file], defines=str(def_file), fix=True)
    assert res.ok
    assert res.data["ambiguous"] == 1
    assert res.data["fixed_count"] == 0
    assert not Path(f"{md_file}.bak").exists()
    assert "창마다 다름" in render_check_report(res.data)


def test_cli_kbd_and_exit_code(tmp_path: Path):
    src_dir = _write_sample_boxes(tmp_path)
    def_file = tmp_path / "defines.json"
    def_file.write_text(json.dumps(SAMPLE_AMAN_DEFINES, ensure_ascii=False), encoding="utf-8")

    runner = CliRunner()

    # B: 표 출력
    r1 = runner.invoke(app, ["kbd", str(src_dir), "--defines", str(def_file)])
    assert r1.exit_code == 0
    assert "| 저장 | 문서양식 등록 |" in r1.output

    # B: --json 출력
    r2 = runner.invoke(app, ["kbd", str(src_dir), "--defines", str(def_file), "--json"])
    assert r2.exit_code == 0
    parsed = json.loads(r2.output)
    assert isinstance(parsed, list)
    assert any(x["text"] == "조회" and x["verdict"] == "같음" for x in parsed)

    # C: --check 불일치 시 종료코드 1
    md_file = tmp_path / "doc.md"
    md_file.write_text("눌러라 `저장`\n", encoding="utf-8")
    r3 = runner.invoke(
        app,
        ["kbd", "--check", str(md_file), "--boxes", str(src_dir), "--defines", str(def_file)],
    )
    assert r3.exit_code == 1
    assert "❌ L1 `저장` → `0F7F90:check:저장`" in r3.output

    # C: --fix 후 종료코드 0
    r4 = runner.invoke(
        app,
        ["kbd", "--check", str(md_file), "--boxes", str(src_dir), "--defines", str(def_file), "--fix"],
    )
    assert r4.exit_code == 0
    assert "`0F7F90:check:저장`" in md_file.read_text(encoding="utf-8")


def test_extract_md_inline_codes_ignores_fences_and_double_backticks():
    md = (
        "일반 `조회` 와 `0F7F90:check:저장` 그리고 ``이중백틱``\n"
        "```\n"
        "`펜스안`\n"
        "```\n"
        "이스케이프 \\`무시\\` 뒤 `닫기`\n"
    )
    spans = extract_md_inline_codes(md)
    assert [(s.line_no, s.inner, s.label) for s in spans] == [
        (1, "조회", "조회"),
        (1, "0F7F90:check:저장", "저장"),
        (5, "닫기", "닫기"),
    ]
