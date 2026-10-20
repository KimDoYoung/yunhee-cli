"""서블릿 클래스 분석 도구."""

import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.analysis.method import _find_method_blocks
from yunhee.tools.as_is.src_indexer import find_app

NAME = "servlet"
DESCRIPTION = "서블릿 클래스 및 fileType 분기 처리 로직 분석 (클라이언트 서블릿 호출과 연결)"
TARGET_HELP = "<서블릿클래스>"
FORMATS = ("md", "code")
EXAMPLES = [
    "yunhee analysis servlet FileDownload --type apprList",
    "yunhee analysis servlet FileDownload --type apprList -o code",
    "yunhee analysis servlet FileDownload --type selectList",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    target_name = target.strip().removesuffix(".java")
    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    app = find_app(src_root) or src_root

    cand_files: list[Path] = []
    for f in (app / "server").rglob(f"{target_name}.java"):
        if "target" not in f.parts:
            cand_files.append(f)

    if not cand_files:
        for f in src_root.rglob(f"{target_name}.java"):
            if "target" not in f.parts:
                cand_files.append(f)

    if not cand_files:
        raise ValueError(f"서블릿 소스 파일을 찾을 수 없습니다: {target_name}.java")

    servlet_file = cand_files[0]
    raw_text = servlet_file.read_text(encoding="utf-8", errors="replace")

    # service() 메서드에서 fileType 분기 파싱
    # if ("apprList".equals(fileType)) downloadApprList(...)
    branches: dict[str, str] = {}
    pattern = re.compile(
        r'if\s*\(\s*["\']([^"\']+)["\']\.equals\(\s*fileType\s*\)\s*\)\s*\{?\s*(\w+)\s*\('
    )
    for m in pattern.finditer(raw_text):
        ftype, mname = m.group(1), m.group(2)
        branches[ftype] = mname

    pattern2 = re.compile(
        r'if\s*\(\s*fileType\.equals\(\s*["\']([^"\']+)["\']\s*\)\s*\)\s*\{?\s*(\w+)\s*\('
    )
    for m in pattern2.finditer(raw_text):
        ftype, mname = m.group(1), m.group(2)
        branches[ftype] = mname

    req_type = opts.get("type") or opts.get("file_type")
    chosen_method = None
    if req_type:
        chosen_method = branches.get(req_type)
        if not chosen_method:
            # fallback: 이름 패턴 검색 download{req_type}
            cand_m = f"download{req_type[0].upper()}{req_type[1:]}"
            blocks = _find_method_blocks(raw_text, cand_m)
            if blocks:
                chosen_method = cand_m

    if not chosen_method and branches:
        if req_type:
            raise ValueError(
                f"{target_name}에서 fileType '{req_type}' 분기를 찾을 수 없습니다. 지원 목록: {', '.join(sorted(branches.keys()))}"
            )
        # default to first or list
        req_type = next(iter(branches.keys()))
        chosen_method = branches[req_type]

    blocks = _find_method_blocks(raw_text, chosen_method) if chosen_method else []
    if not blocks:
        raise ValueError(f"{target_name}에서 메서드 '{chosen_method}'을 찾을 수 없습니다.")

    _, start_l, end_l, body = blocks[0]

    rel = servlet_file.relative_to(app) if servlet_file.is_relative_to(app) else servlet_file.relative_to(src_root)

    return {
        "file": servlet_file,
        "rel": str(rel),
        "target": target_name,
        "file_type": req_type,
        "method_name": chosen_method,
        "start": start_l,
        "end": end_l,
        "body": body,
        "raw_text": raw_text,
        "branches": branches,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    body = obj["body"]
    start = obj["start"]
    end = obj["end"]
    rel = obj["rel"]
    file_type = obj["file_type"]
    m_name = obj["method_name"]

    if fmt == "code":
        return f"{rel}:{start}-{end}\n{body}"

    # MD 요약 분석
    # 1. SQL ID 추출
    sqls = sorted(set(re.findall(r'sqlSession\.\w+\(\s*["\']([a-zA-Z0-9_.]+)["\']', body)))
    # 2. ZIP 이름 / Content-Disposition 추출
    m_zip = re.search(r'createZip\s*\([^,]+,[^,]+,\s*["\']([^"\']+)["\']', body)
    zip_name = m_zip.group(1) if m_zip else ""
    if not zip_name:
        m_cd = re.search(r'Content-Disposition[^"\']*filename=\\?["\']?([^"\';]+)', body)
        if m_cd:
            zip_name = m_cd.group(1)

    # 3. 번호 규칙 분기
    branches_desc = []
    if re.search(r'getTitleYn\(\)', body) or "titleYn" in body:
        branches_desc.append('번호 규칙 분기 (`titleYn == "true"`: 본문(1) / 첨부파일(1-sub))')

    lines = [
        f"### 서블릿 `{obj['target']}` — fileType=`{file_type}`",
        f"- 위치: `{rel}:{start}-{end}` (`{m_name}`)",
    ]
    if sqls:
        lines.append(f"- 호출 SQL: {', '.join(f'`{s}`' for s in sqls)}")
    if zip_name:
        lines.append(f"- 다운로드 파일(ZIP) 이름: `{zip_name}`")
    if branches_desc:
        lines.append(f"- 상세 분기: {', '.join(branches_desc)}")

    # 파라미터 추출
    params = sorted(set(re.findall(r'request\.getParameter\(\s*["\']([^"\']+)["\']', body)))
    if params:
        lines.append(f"- 전달 파라미터: {', '.join(f'`{p}`' for p in params)}")

    return "\n".join(lines)
