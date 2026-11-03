import json
import re
import os
import subprocess
from pathlib import Path
from collections import defaultdict

ASIS_SRC = Path("/home/kdy987/work/IDMS-IC")
VI_BASE = ASIS_SRC / "application/src/main/java/myApp/client/vi"
SRV_BASE = ASIS_SRC / "application/src/main/java/myApp/server"
SCHEMA_PATH = Path("/home/kdy987/work/yunhee-cli/data/schema/LOCAL_DB.json")
OUT_DIR = Path("/home/kdy987/work/yunhee-cli/docs/domain분석")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Load DB Schema
with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)

table_by_dom = defaultdict(list)
for t in schema.get("tables", []):
    tname = t["name"]
    m = re.match(r"^([a-z]+)\d", tname)
    dom = m.group(1) if m else "_etc"
    table_by_dom[dom].append(t)

# 2. Load Domain Titles
domain_titles = {}
domain_md = OUT_DIR / "AssetERP-domain.md"
if domain_md.exists():
    for line in domain_md.read_text(encoding="utf-8").splitlines():
        if "`" in line and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            # ['1', '**`act`**', '**Ac**coun**t**ing', '**회계 / 계정관리**', '...']
            if len(parts) >= 5 and parts[1].isdigit() is False:
                # find code
                m_code = re.search(r"`([a-z0-9_]+)`", parts[2])
                if m_code:
                    code = m_code.group(1)
                    origin = parts[3].strip()
                    kor = parts[4].replace("**", "").strip()
                    desc = parts[5].strip()
                    domain_titles[code] = (kor, origin, desc)
            elif len(parts) >= 6 and parts[1].isdigit():
                m_code = re.search(r"`([a-z0-9_]+)`", parts[2])
                if m_code:
                    code = m_code.group(1)
                    origin = parts[3].strip()
                    kor = parts[4].replace("**", "").strip()
                    desc = parts[5].strip()
                    domain_titles[code] = (kor, origin, desc)

print(f"Loaded {len(domain_titles)} domain definitions from AssetERP-domain.md")

# 3. Load sys06_menu data
res = subprocess.run([
    "uv", "run", "yunhee", "sql",
    "SELECT m.sys06_class_nm, p.sys06_menu_nm AS parent_nm, m.sys06_menu_nm, m.sys06_note, m.sys06_menu_no, m.sys06_use_yn FROM sys06_menu m LEFT JOIN sys06_menu p ON p.sys06_menu_id = m.sys06_parent_id WHERE m.sys06_class_nm IS NOT NULL AND m.sys06_class_nm <> ''",
    "--limit", "3000"
], capture_output=True, text=True)

menu_by_class = {}
if res.returncode == 0:
    for line in res.stdout.splitlines():
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 7 and parts[1] != "sys06_class_nm" and not parts[1].startswith("---"):
                cls = parts[1]
                menu_by_class[cls] = {
                    "parent_nm": parts[2],
                    "menu_nm": parts[3],
                    "note": parts[4],
                    "menu_no": parts[5],
                    "use_yn": parts[6]
                }

print(f"Loaded {len(menu_by_class)} menus from DB.")

# Helper to clean strings for markdown
def clean_md(text: str) -> str:
    if not text:
        return ""
    return text.replace("|", "\\|").replace("\n", " ").strip()

# Scan all domain directories in VI_BASE
all_vi_doms = sorted([d.name for d in VI_BASE.iterdir() if d.is_dir()])

# Generate doc for a single domain
def generate_domain_doc(dom: str):
    kor_name, origin, dom_desc = domain_titles.get(dom, (f"{dom.upper()} 도메인", "", ""))
    
    vi_dir = VI_BASE / dom
    srv_dir = SRV_BASE / dom
    mapper_dir = srv_dir / "mapper" if srv_dir.is_dir() else None
    
    vi_files = sorted([f.name for f in vi_dir.glob("*.java")]) if vi_dir.is_dir() else []
    srv_files = sorted([f.name for f in srv_dir.glob("*.java")]) if srv_dir.is_dir() else []
    mapper_files = sorted([f.name for f in mapper_dir.glob("*.xml")]) if mapper_dir and mapper_dir.is_dir() else []
    db_tables = sorted(table_by_dom.get(dom, []), key=lambda x: x["name"])
    
    # Identify Tabs, Pages, Lookups, Grids, Popups
    tab_files = [f for f in vi_files if "Tab" in f or "Page" in f]
    other_vi = [f for f in vi_files if f not in tab_files]
    
    # Gather menu entries belonging to this domain
    dom_menus = []
    for cls, m_info in menu_by_class.items():
        # Match class starting with Dom or dom in cls
        if cls.lower().startswith(dom.lower()) or (f".{dom}." in cls.lower()):
            dom_menus.append((cls, m_info))
    
    # Group menus and tabs into work items
    # Map class -> menu info
    # For tabs without sys06_menu, inspect file comments/Korean text
    work_items = []
    seen_classes = set()
    
    # 1. First process registered menus
    for cls, m_info in dom_menus:
        seen_classes.add(cls)
        # find matching java file
        java_file = f"{cls}.java" if f"{cls}.java" in vi_files else ""
        work_items.append({
            "cls": cls,
            "file": java_file or cls,
            "menu_nm": m_info["menu_nm"],
            "parent_nm": m_info["parent_nm"],
            "note": m_info["note"],
            "menu_no": m_info["menu_no"]
        })
        
    # 2. Add remaining Tab/Page files not registered in sys06_menu
    for tf in tab_files:
        stem = Path(tf).stem
        if stem not in seen_classes:
            seen_classes.add(stem)
            # Inspect text for Korean titles
            fpath = vi_dir / tf
            txt = fpath.read_text(encoding="utf-8", errors="replace")
            # find first few Korean phrases
            kor_matches = re.findall(r'"([가-힣\s/()0-9_-]{2,25})"', txt)
            meaningful_kor = [k.strip() for k in kor_matches if k.strip() not in ("조회", "등록", "저장", "삭제", "닫기", "확인", "취소", "전체", "선택")]
            sample_kor = meaningful_kor[0] if meaningful_kor else stem
            
            # check comments
            comment = ""
            for line in txt.splitlines()[:15]:
                if "//" in line:
                    c = line.split("//", 1)[1].strip()
                    if re.search(r"[가-힣]", c):
                        comment = c
                        break
            
            work_items.append({
                "cls": stem,
                "file": tf,
                "menu_nm": comment or sample_kor,
                "parent_nm": "내부 컴포넌트/탭",
                "note": comment or "",
                "menu_no": "-"
            })
            
    # Sort work items by parent_nm, cls
    work_items.sort(key=lambda x: (x["parent_nm"] or "", x["cls"]))
    
    # Group into Areas (SYS-01, EMP-01 style)
    # Group by parent_nm or category
    area_map = defaultdict(list)
    for it in work_items:
        p_nm = it["parent_nm"] or "기타 및 내부 탭"
        # clean parent name: remove leading numbers like '01. '
        cat = re.sub(r"^\d+\.\s*", "", p_nm).strip()
        area_map[cat].append(it)
        
    # Map server classes & tables
    # Build text
    lines = []
    lines.append(f"# {dom} ({kor_name}) 도메인 주요 업무 리스트 및 분석표")
    lines.append("")
    lines.append(f"> **문서 목적**: AssetERP의 `{dom}` ({kor_name}) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  ")
    lines.append(f"> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/{dom}/*`, `myApp/server/{dom}/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`{dom}##_*`), `sys06_menu`.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. 업무 영역별 분류 요약")
    lines.append("")
    lines.append(f"`{dom}` 도메인은 **{kor_name}** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.")
    lines.append("")
    lines.append("| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |")
    lines.append("|:---:|:---|:---|:---:|")
    
    dom_upper = dom.upper()
    area_idx = 1
    area_codes = {}
    for cat, items in sorted(area_map.items()):
        code = f"{dom_upper}-{area_idx:02d}"
        area_codes[cat] = code
        sample_classes = ", ".join([it["cls"] for it in items[:3]])
        if len(items) > 3:
            sample_classes += f" 외 {len(items)-3}개"
        lines.append(f"| **{code}** | **{cat}** | {cat} 관련 화면 및 처리 모듈 | {len(items)}개 화면 |")
        area_idx += 1
        
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. 세부 주요 업무 리스트 (전수 나열)")
    lines.append("")
    
    item_num = 1
    for cat, items in sorted(area_map.items()):
        code = area_codes[cat]
        lines.append(f"### {code}. {cat}")
        lines.append("| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |")
        lines.append("|:---:|:---|:---|:---:|:---|")
        for it in items:
            m_nm = clean_md(it["menu_nm"]) or it["cls"]
            cls_name = it["cls"]
            menu_no = it["menu_no"] or "-"
            note = clean_md(it["note"]) or f"{m_nm} 기능 처리"
            lines.append(f"| {item_num} | **{m_nm}** | `{cls_name}` | {menu_no} | {note} |")
            item_num += 1
        lines.append("")
        
    lines.append("---")
    lines.append("")
    lines.append("## 3. 관련 서버 모듈 및 매퍼 현황")
    lines.append("")
    lines.append("### 서버 서비스 클래스 (`server/" + dom + "/`)")
    if srv_files:
        lines.append("| 번호 | 서버 클래스 | 관련 역할 및 설명 |")
        lines.append("|:---:|:---|:---|")
        for s_idx, sf in enumerate(srv_files, 1):
            s_stem = Path(sf).stem
            lines.append(f"| {s_idx} | `{s_stem}` | {s_stem} 비즈니스 로직 및 RPC 서비스 처리 |")
    else:
        lines.append("- 별도 서버 클래스 없음 (공통 서비스 활용 또는 클라이언트 전용)")
    lines.append("")
    
    lines.append("### 관련 MyBatis 매퍼 XML (`server/" + dom + "/mapper/`)")
    if mapper_files:
        lines.append("| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |")
        lines.append("|:---:|:---|:---|")
        for m_idx, mf in enumerate(mapper_files, 1):
            m_stem = Path(mf).stem
            lines.append(f"| {m_idx} | `{mf}` | `{m_stem}` 테이블 관련 쿼리 매핑 |")
    else:
        lines.append("- 도메인 전용 매퍼 파일 없음")
    lines.append("")
    
    lines.append("### 관련 데이터베이스 테이블 (`LOCAL_DB`)")
    if db_tables:
        lines.append("| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |")
        lines.append("|:---:|:---|:---|:---:|:---|")
        for t_idx, t in enumerate(db_tables, 1):
            t_name = t["name"]
            t_note = clean_md(t.get("note", "")) or "-"
            cols = len(t.get("columns", []))
            pk = ", ".join(t.get("pk", [])) or "-"
            lines.append(f"| {t_idx} | `{t_name}` | {t_note} | {cols} | `{pk}` |")
    else:
        lines.append("- 전용 도메인 테이블 없음 (공통 또는 타 도메인 참조)")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## 4. 요약 통계")
    lines.append("")
    lines.append(f"- **총 세부 업무 화면**: **{len(work_items)}개**")
    lines.append(f"- **UI 컴포넌트 수**: 총 {len(vi_files)}개 (Tab/Page: {len(tab_files)}개, Lookup/Popup/기타: {len(other_vi)}개)")
    lines.append(f"- **서버 서비스 클래스 수**: **{len(srv_files)}개**")
    lines.append(f"- **MyBatis 매퍼 XML 수**: **{len(mapper_files)}개**")
    lines.append(f"- **DB 테이블 수**: **{len(db_tables)}개**")
    lines.append("")
    
    out_file = OUT_DIR / f"{dom}-도메인-주요업무들.md"
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated: {out_file.name} (Items: {len(work_items)}, Tables: {len(db_tables)}, Srv: {len(srv_files)})")

# Execute for all domains
tier1 = ['pay', 'emp', 'tdm', 'ast', 'apr', 'biz', 'fnd', 'ics', 'flt', 'dcr', 'icam', 'sch']
tier2 = ['act', 'bbs', 'car', 'dbm', 'est', 'crm', 'rpt', 'chk', 'opr', 'scm', 'att', 'bmt', 'pln', 'sms']
tier3 = ['fbx', 'adv', 'cmp', 'crd', 'msc', 'icr', 'kfs', 'mkt', 'mrb', 'ifi', 'org', 'pcd', 'tgt', 'com', 'eml', 'frm']

print("=== Generating Tier 1 (12 domains) ===")
for d in tier1:
    generate_domain_doc(d)

print("=== Generating Tier 2 (14 domains) ===")
for d in tier2:
    generate_domain_doc(d)

print("=== Generating Tier 3 (16 domains) ===")
for d in tier3:
    generate_domain_doc(d)

print("All done!")
