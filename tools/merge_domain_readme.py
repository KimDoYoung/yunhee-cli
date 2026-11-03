import re
from pathlib import Path

OUT_DIR = Path("/home/kdy987/work/yunhee-cli/docs/domain분석")
domain_md_path = OUT_DIR / "AssetERP-domain.md"
readme_path = OUT_DIR / "README.md"

# 1. Parse AssetERP-domain.md
domain_info = {}
table_aux_info = []

current_section = 1
if domain_md_path.exists():
    for line in domain_md_path.read_text(encoding="utf-8").splitlines():
        if "2. DB 테이블/메뉴에만 존재하는 보조 도메인" in line:
            current_section = 2
            continue
        
        if "`" in line and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if current_section == 1 and len(parts) >= 6 and parts[1].isdigit():
                m_code = re.search(r"`([a-z0-9_]+)`", parts[2])
                if m_code:
                    code = m_code.group(1)
                    origin = parts[3].strip()
                    kor = parts[4].replace("**", "").strip()
                    desc = parts[5].strip()
                    domain_info[code] = {
                        "origin": origin,
                        "kor": kor,
                        "desc": desc
                    }
            elif current_section == 2 and len(parts) >= 4:
                m_code = re.search(r"`([a-z0-9_*]+)`", parts[1])
                if m_code:
                    code = m_code.group(1)
                    kor = parts[2].replace("**", "").strip()
                    desc = parts[3].strip()
                    table_aux_info.append((code, kor, desc))

print(f"Parsed {len(domain_info)} primary domains, {len(table_aux_info)} aux domains.")

# 2. Parse stats from all *-도메인-주요업무들.md
files = sorted(OUT_DIR.glob("*-도메인-주요업무들.md"))
domain_stats = {}

total_items = 0
total_srv = 0
total_tables = 0

for f in files:
    dom = f.name.split("-")[0]
    txt = f.read_text(encoding="utf-8")
    
    items_m = re.search(r"총 세부 업무 화면\*\*:\s*\*\*(\d+)개\*\*", txt)
    items_cnt = int(items_m.group(1)) if items_m else 0
    
    srv_m = re.search(r"서버 서비스 클래스 수\*\*:\s*\*\*(\d+)개\*\*", txt)
    srv_cnt = int(srv_m.group(1)) if srv_m else 0
    
    tbl_m = re.search(r"DB 테이블 수\*\*:\s*\*\*(\d+)개\*\*", txt)
    tbl_cnt = int(tbl_m.group(1)) if tbl_m else 0
    
    domain_stats[dom] = {
        "items": items_cnt,
        "srv": srv_cnt,
        "tables": tbl_cnt,
        "file": f.name
    }
    total_items += items_cnt
    total_srv += srv_cnt
    total_tables += tbl_cnt

# Merge & Sort by items desc
merged_list = []
for dom, stat in domain_stats.items():
    info = domain_info.get(dom, {
        "origin": "-",
        "kor": f"{dom.upper()} 관리",
        "desc": "-"
    })
    merged_list.append({
        "dom": dom,
        "kor": info["kor"],
        "origin": info["origin"],
        "desc": info["desc"],
        "items": stat["items"],
        "srv": stat["srv"],
        "tables": stat["tables"],
        "file": stat["file"]
    })

merged_list.sort(key=lambda x: x["items"], reverse=True)

# 3. Construct Hybrid README.md
lines = []
lines.append("# AssetERP 전 도메인 주요 업무 통합 안내서 (Agent Guide)")
lines.append("")
lines.append("> **문서 목적**: AI Agent 및 개발자가 AssetERP ASIS 시스템의 43개 비즈니스 도메인 구조를 빠르게 파악하고, 필요한 세부 업무 분석 문서로 직행할 수 있도록 지원하는 **통합 내비게이션 색인**입니다.  ")
lines.append("> **포함 정보**: 도메인 약자 및 영문 유래, 한글 업무명, 핵심 역할/기능 요약, 모듈 규모 통계(화면·서버·테이블 수), 상세 분석표 직접 링크.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 1. 43개 업무 도메인 색인 및 세부 분석표 링크")
lines.append("")
lines.append("| 순번 | 도메인 | 업무 도메인명 | 영문 유래 | 핵심 역할 및 주요 기능 요약 | 화면 | 서버 | DB | 세부 분석표 |")
lines.append("|:---:|:---:|:---|:---|:---|:---:|:---:|:---:|:---|")

for idx, m in enumerate(merged_list, 1):
    lines.append(
        f"| {idx} | **`{m['dom']}`** | **{m['kor']}** | {m['origin']} | {m['desc']} | {m['items']}개 | {m['srv']}개 | {m['tables']}개 | [{m['dom']} 상세 분석](./{m['file']}) |"
    )

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 2. DB 테이블 / 특수 목적 보조 도메인")
lines.append("")
lines.append("클라이언트 독립 UI 메뉴 없이 DB 스키마 및 특정 목적(데이터 이행, 인프라 관리 등)으로 분리된 도메인 접두사입니다.")
lines.append("")
lines.append("| 도메인 약자 | 한글 의미 | 영문 유래 / 설명 및 관련 테이블 |")
lines.append("|:---:|:---|:---|")
for code, kor, desc in table_aux_info:
    lines.append(f"| **`{code}`** | **{kor}** | {desc} |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 3. 전체 시스템 규모 통계 요약")
lines.append("")
lines.append(f"- **분석 완료 비즈니스 도메인**: **{len(merged_list)}개 도메인**")
lines.append(f"- **식별된 주요 세부 화면/탭**: **총 {total_items}개**")
lines.append(f"- **연계 Java 서버 RPC 클래스**: **총 {total_srv}개**")
lines.append(f"- **연계 PostgreSQL DB 테이블**: **총 {total_tables}개** (보조/백업 테이블 제외)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 4. Agent 업무 파악 권장 워크플로우")
lines.append("")
lines.append("1. **도메인 식별**: 사용자의 요청(예: `급여 명세서`, `책무구조도`, `법인카드`)과 관련된 **도메인 약자(`pay`, `tdm`, `crd`)**를 상단 표에서 확인합니다.")
lines.append("2. **세부 분석표 참조**: 해당 도메인의 `세부 분석표 링크`(`docs/domain분석/{dom}-도메인-주요업무들.md`)를 열람하여 관련 GXT 화면(`Tab`, `Page`), 서버 클래스, MyBatis 매퍼, DB 테이블 매핑을 파악합니다.")
lines.append("3. **정밀 소스 검토**: 파악된 컴포넌트명을 바탕으로 ASIS 소스(`client/vi/{dom}/*`, `server/{dom}/*`) 또는 `yunhee outline / yunhee events` 도구를 사용하여 세부 로직을 분석합니다.")
lines.append("")

readme_path.write_text("\n".join(lines), encoding="utf-8")
print("README.md successfully updated!")

# Remove duplicate AssetERP-domain.md
if domain_md_path.exists():
    domain_md_path.unlink()
    print("AssetERP-domain.md removed.")
