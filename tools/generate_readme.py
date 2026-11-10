import re
from pathlib import Path

DOCS_DIR = Path("/home/kdy987/work/yunhee-cli/docs/domain분석")

files = sorted(DOCS_DIR.glob("*-도메인-주요업무들.md"))
print(f"Total domain docs: {len(files)}")

lines = []
lines.append("# AssetERP 전 도메인 주요 업무 분석 보고서")
lines.append("")
lines.append("> **개요**: AssetERP ASIS 시스템의 43개 도메인에 대한 주요 비즈니스 업무, GXT UI 컴포넌트, 서버 RPC 클래스, MyBatis 매퍼, PostgreSQL DB 테이블을 분석 정리한 통합 색인 문서입니다.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 도메인별 업무 분석표 바로가기 (총 43개)")
lines.append("")
lines.append("| 순번 | 도메인 약자 | 업무 도메인명 | 세부 화면 수 | 서버 클래스 | DB 테이블 | 문서 링크 |")
lines.append("|:---:|:---:|:---|:---:|:---:|:---:|:---|")

total_items = 0
total_srv = 0
total_tables = 0

stats = []

for f in files:
    dom = f.name.split("-")[0]
    txt = f.read_text(encoding="utf-8")
    
    # Extract title
    title_m = re.search(r"#\s*([a-z0-9_]+)\s*\(([^)]+)\)", txt)
    kor_name = title_m.group(2) if title_m else dom
    
    # Extract stats
    items_m = re.search(r"총 세부 업무 화면\*\*:\s*\*\*(\d+)개\*\*", txt)
    items_cnt = int(items_m.group(1)) if items_m else 0
    
    srv_m = re.search(r"서버 서비스 클래스 수\*\*:\s*\*\*(\d+)개\*\*", txt)
    srv_cnt = int(srv_m.group(1)) if srv_m else 0
    
    tbl_m = re.search(r"DB 테이블 수\*\*:\s*\*\*(\d+)개\*\*", txt)
    tbl_cnt = int(tbl_m.group(1)) if tbl_m else 0
    
    stats.append({
        "dom": dom,
        "kor": kor_name,
        "items": items_cnt,
        "srv": srv_cnt,
        "tables": tbl_cnt,
        "file": f.name
    })
    total_items += items_cnt
    total_srv += srv_cnt
    total_tables += tbl_cnt

# Sort by items_cnt desc
stats.sort(key=lambda x: x["items"], reverse=True)

for idx, s in enumerate(stats, 1):
    lines.append(f"| {idx} | **`{s['dom']}`** | {s['kor']} | {s['items']}개 | {s['srv']}개 | {s['tables']}개 | [{s['file']}](./{s['file']}) |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 전체 종합 통계")
lines.append("")
lines.append(f"- **분석 완료 도메인 수**: **{len(files)}개 도메인**")
lines.append(f"- **분석된 주요 업무 화면/탭 수**: **{total_items}개**")
lines.append(f"- **연계 서버 서비스 클래스 수**: **{total_srv}개**")
lines.append(f"- **연계 PostgreSQL DB 테이블 수**: **{total_tables}개**")
lines.append("")

readme_path = DOCS_DIR / "README.md"
readme_path.write_text("\n".join(lines), encoding="utf-8")
print(f"Created {readme_path.name}")
