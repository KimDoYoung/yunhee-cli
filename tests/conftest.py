"""trace-pair / trace-diff / trace-gap 테스트가 함께 쓰는 가짜 ASIS·TOBE 세계."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from yunhee.tools.trace.resolve import TraceContext, load_context

ASIS_SCREEN = """---
source_commit: abc12345
indexed_at: 2026-10-28T18:43:16+09:00
---
# Emp00_Tab_TransInfo

- 종류: 화면
- 메뉴: 사원관리 > 사원정보 관리 (#1029)
- 파일: `client/vi/emp/Emp00_Tab_TransInfo.java`

## 서비스

| 서비스 | 호출 위치 | 서버 | SQL ID |
|:---|:---|:---|:---|
| `emp.Emp00_TransInfo.selectByText` | Emp00_Tab_TransInfo:65 | [`Emp00_TransInfo.java:33`](x.md) | [`emp00_trans_info.selectByText`](x.md), [`dbConfig.getSeq`](x.md) |
| `emp.Emp00_TransInfo.update` | Emp00_Tab_TransInfo:70 | [`Emp00_TransInfo.java:415`](x.md) | [`emp02_others.insert`](x.md) |
| `emp.Emp09_Etc.legacy` | Emp00_Tab_TransInfo:75 | [`Emp09_Etc.java:10`](x.md) | [`emp09_etc.selectAll`](x.md) |

## 테이블

[`emp01_person`](x.md), [`emp02_others`](x.md), [`emp09_etc`](x.md)

## UI

### Emp00_Tab_TransInfo (`client/vi/emp/Emp00_Tab_TransInfo.java`, 80줄)

- 그리드 `grid` (buildGrid()):
  - empKorName 100 "성명" Text
  - hireDate 100 "입사일" Date
  - oldCol 80 "구분" Text

#### 이벤트
[E0] 화면 열림 (생성자 L10-20) → settings()
[E1] retrieveButton[조회].Select (L30) → retrieve()
[E2] excelButton[엑셀].Select (L40) → excel()
[E3] deadButton[템플릿].Select (L47) → 인라인 L47-49 (new SelectHandler(){…) ⚠ 도달 불가 (x)

#### 메서드
| 메서드 | 줄 | 호출처 | 하는 일 | 구분 |
| --- | --- | --- | --- | --- |
| public retrieve() | L60-70 | E1 | 서비스 emp.Emp00_TransInfo.selectByText | 업무 |

#### 사용된 버튼들
1. <Button type="search" onClick={retrieve}>조회</Button>
2. <Button type="excel" onClick={excel}>엑셀</Button>
"""

MENUS = """| 메뉴 | # | 사용 | 화면 |
|:---|:---|:---|:---|
| 사원관리 > 사원정보 관리 | 1029 | true | [`Emp00_Tab_TransInfo`](emp/screens/Emp00_Tab_TransInfo.md) |
| 사원관리 > 레거시 화면 | 1030 | true | [`Emp09_Tab_Legacy`](emp/screens/Emp09_Tab_Legacy.md) |
"""

ASIS_INDEX = {
    "client_classes": {"Emp00_Tab_TransInfo": {"services": [], "refs": []}, "Emp09_Tab_Legacy": {"services": [], "refs": []}},
    "server_classes": {
        "emp.Emp00_TransInfo": {"methods": [
            {"name": "selectByText", "sqls": ["emp00_trans_info.selectByText"], "is_service": True, "udm_calls": []},
            {"name": "update", "sqls": ["emp02_others.insert"], "is_service": True, "udm_calls": []},
        ]},
        "emp.Emp09_Etc": {"methods": [{"name": "legacy", "sqls": ["emp09_etc.selectAll"], "is_service": True, "udm_calls": []}]},
    },
    "statements": {
        "emp00_trans_info.selectByText": {"file": "server/emp/mapper/emp00_trans_info.xml", "line": 10, "kind": "select"},
        "emp02_others.insert": {"file": "server/emp/mapper/emp02_others.xml", "line": 5, "kind": "insert"},
        "emp09_etc.selectAll": {"file": "server/emp/mapper/emp09_etc.xml", "line": 3, "kind": "select"},
    },
}

ASIS_MAPPERS = {
    "emp00_trans_info.xml": """<mapper namespace="emp00_trans_info">
  <select id="selectByText">
    SELECT p.emp01_nm, o.emp02_note FROM emp01_person p JOIN emp02_others o ON o.id = p.id
    WHERE p.emp01_company_id = #{companyId}
    <if test="isSeparateAddTitle == true"> AND p.kind = 'A'</if>
    <if test="searchText != null"> AND p.emp01_nm LIKE #{searchText}</if>
    AND EXISTS (SELECT 1 FROM emp09_etc e WHERE e.id = p.id)
  </select>
</mapper>""",
    "emp02_others.xml": """<mapper namespace="emp02_others">
  <insert id="insert">INSERT INTO emp02_others (id, emp02_note) VALUES (#{id}, #{note})</insert>
</mapper>""",
    "emp09_etc.xml": """<mapper namespace="emp09_etc"><select id="selectAll">SELECT * FROM emp09_etc</select></mapper>""",
}

TOBE_TSX = """/**
 * [1029] 사원관리 > 사원정보 관리  (C01)
 * AS-IS: myApp/client/vi/emp/Emp00_Tab_TransInfo.java
 */
import { empApi } from '@/api/emp';
const buildGrid = () => [
  gb.text('korNm', 100, '성명'),
  gb.date('hireDate', 100, '입사일'),
  gb.text('newCol', 80, '신규'),
];
export const Emp00_Tab_TransInfo = () => {
  // [E1] retrieveButton[조회].Select (L30) → retrieve()
  // [E0] 화면 열림
  const rows = await empApi.searchTransInfos();
  return <div>{rows.length > 0 && <Grid />}<Button disabled={!selected}>엑셀</Button></div>;
};
"""
TOBE_ONLY_TSX = """/** AS-IS: myApp/client/vi/emp/Emp77_Tab_Brand.java */
import { empApi } from '@/api/emp';
export const Emp77_Tab_Brand = () => { empApi.brandNew(); return <div/>; };
"""

TOBE_API = """export const empApi = {
  /** AS-IS emp.Emp00_TransInfo.selectByText */
  searchTransInfos: async (): Promise<X[]> => {
    const res = await apiClient.get<ApiResponse<X[]>>('v1/emp/trans-infos', { params: {} });
    return res.data.data ?? [];
  },
  brandNew: async (): Promise<void> => {
    await apiClient.post<ApiResponse<void>>(`v1/emp/brand/${id}`, {});
  },
};
"""

TOBE_CONTROLLER = """package x;

@RestController
@RequestMapping("/api/v1/emp")
public class EmpTransInfoController {
    private final EmpTransInfoService empTransInfoService;

    /** AS-IS emp.Emp00_TransInfo.selectByText */
    @GetMapping("/trans-infos")
    public ApiResponse<List<X>> searchTransInfos(@RequestParam String q) {
        return ApiResponse.ok(empTransInfoService.searchTransInfos(q));
    }

    @PostMapping("/brand/{id}")
    public ApiResponse<Void> brand(@PathVariable Long id) {
        return ApiResponse.ok(null);
    }
}
"""

TOBE_SERVICE = """package x;

@Service
public class EmpTransInfoService {
    private final EmpTransInfoMapper empTransInfoMapper;

    /** AS-IS selectByText */
    public List<X> searchTransInfos(String q) {
        return empTransInfoMapper.searchTransInfos(q);
    }
}
"""

TOBE_MAPPER_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<!--
  AS-IS server/emp/mapper/emp00_trans_info.xml selectByText(L10)
-->
<mapper namespace="x.EmpTransInfoMapper">
    <!-- AS-IS selectByText L10 (isSeparateAddTitle → separateAddTitle) -->
    <select id="searchTransInfos" resultType="x.X">
        SELECT p.emp01_nm AS nm FROM emp01_person p
        WHERE p.emp01_company_id = #{companyId}
        <if test="separateAddTitle == true"> AND p.kind = 'A'</if>
    </select>
    <!-- 컬럼 설명 t2.emp03_trans_id — AS-IS 아님 -->
    <select id="untracked">SELECT 1 FROM emp01_person</select>
</mapper>"""

TOBE_MAPPER_IF = "package x;\npublic interface EmpTransInfoMapper { List<X> searchTransInfos(String q); }\n"


@dataclass
class World:
    ctx: TraceContext
    tobe: Path
    src: Path
    index: Path


@pytest.fixture
def world(tmp_path) -> World:
    idx = tmp_path / "idx"
    (idx / "emp" / "screens").mkdir(parents=True)
    (idx / "emp" / "screens" / "Emp00_Tab_TransInfo.md").write_text(ASIS_SCREEN, encoding="utf-8")
    (idx / "emp" / "screens" / "Emp09_Tab_Legacy.md").write_text("---\nsource_commit: a\n---\n# Emp09_Tab_Legacy\n- 종류: 화면\n", encoding="utf-8")
    (idx / "menus.md").write_text(MENUS, encoding="utf-8")
    (idx / "_index.json").write_text(json.dumps(ASIS_INDEX), encoding="utf-8")
    src = tmp_path / "asis"
    (src / "server" / "emp" / "mapper").mkdir(parents=True)
    for name, xml in ASIS_MAPPERS.items():
        (src / "server" / "emp" / "mapper" / name).write_text(xml, encoding="utf-8")
    tobe = tmp_path / "tobe"
    for rel, text in {
        "frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx": TOBE_TSX,
        "frontend/src/pages/emp/Emp77_Tab_Brand.tsx": TOBE_ONLY_TSX,
        "frontend/src/api/emp.ts": TOBE_API,
        "backend/src/main/java/x/EmpTransInfoController.java": TOBE_CONTROLLER,
        "backend/src/main/java/x/EmpTransInfoService.java": TOBE_SERVICE,
        "backend/src/main/java/x/EmpTransInfoMapper.java": TOBE_MAPPER_IF,
        "backend/src/main/resources/mapper/EmpTransInfoMapper.xml": TOBE_MAPPER_XML,
    }.items():
        path = tobe / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    from yunhee.tools.trace.tobe import build_index

    build_index.cache_clear()
    return World(load_context("asis", src=src, src_index=idx), tobe, src, idx)


@pytest.fixture
def rule_db(tmp_path, monkeypatch):
    """규칙 저장소를 임시 sqlite로 돌린다 (data/db/yunhee.db를 건드리지 않는다). 프로젝트 이름은 'p1'."""
    from yunhee.store import db, trace_rules

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "rules.sqlite")
    monkeypatch.setattr(trace_rules, "project_name", lambda: "p1")
    return tmp_path / "rules.sqlite"
