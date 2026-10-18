from pathlib import Path

from yunhee.tools.analysis import grid, method, model, ui
from yunhee.tools.as_is import events
from yunhee.tools.as_is.sql_porter import port_sql


def _setup_chk02_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """037 테스트용 AS-IS 프로젝트 및 DBML 테이블 픽스처 생성."""
    src_root = tmp_path / "asis"
    app_dir = src_root / "application" / "src" / "main" / "java" / "myApp"
    chk_dir = app_dir / "client" / "vi" / "chk"
    model_dir = chk_dir / "model"
    mapper_dir = app_dir / "server" / "chk" / "mapper"
    svc_dir = app_dir / "client" / "service"
    for d in (chk_dir, model_dir, mapper_dir, svc_dir):
        d.mkdir(parents=True, exist_ok=True)

    # DBML 테이블 정의: chk02_daily_list에는 reason, answer_code 등이 없음
    db_tables_dir = tmp_path / "docs" / "as-is" / "db" / "tables"
    db_tables_dir.mkdir(parents=True, exist_ok=True)
    (db_tables_dir / "chk.md").write_text(
        """```dbml
Table chk02_daily_list {
  chk02_daily_list_id numeric(20,0) [pk, not null]
  chk02_company_id numeric(20,0) [not null]
  chk02_class_tree_id numeric(20,0) [not null]
  chk02_content varchar(200)
  chk02_explan varchar(2000)
  chk02_cutoff varchar(100)
  chk02_window_no varchar(100)
  chk02_seq numeric(5,0)
  chk02_use_yn varchar(10)
  chk02_admin_daily_list_id numeric(20,0)
}
```
""",
        encoding="utf-8",
    )

    src_index_dir = tmp_path / "docs" / "as-is" / "src"
    src_index_dir.mkdir(parents=True, exist_ok=True)

    # Model
    (model_dir / "Chk02_DailyListModel.java").write_text(
        """package myApp.client.vi.chk.model;
public class Chk02_DailyListModel {
    private Long dailyListId;
    private Long companyId;
    private Long classTreeId;
    private String content;
    private String explan;
    private String cutoff;
    private String windowNo;
    private Long seq;
    private Boolean useYn;
    private Long adminDailyListId;
    private String classTreeName;
    private String reason;
    private String note;

    public Boolean getAdminYn() {
        if(companyId == 0 || adminDailyListId != 0) {
            return true;
        }else {
            return false;
        }
    }
}
""",
        encoding="utf-8",
    )

    # Properties
    (model_dir / "Chk02_DailyListModelProperties.java").write_text(
        """package myApp.client.vi.chk.model;
public interface Chk02_DailyListModelProperties {
    ValueProvider<Chk02_DailyListModel, Boolean> adminYn();
    ValueProvider<Chk02_DailyListModel, String> classTreeName();
    ValueProvider<Chk02_DailyListModel, String> content();
    ValueProvider<Chk02_DailyListModel, String> reason();
    ValueProvider<Chk02_DailyListModel, Long> seq();
}
""",
        encoding="utf-8",
    )

    # Mapper XML
    (mapper_dir / "chk02_daily_list.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="chk02_daily_list">
<resultMap id="mapper" type="myApp.client.vi.chk.model.Chk02_DailyListModel">
    <id column="chk02_daily_list_id" property="dailyListId"/>
    <result column="chk02_company_id" property="companyId"/>
    <result column="chk02_class_tree_id" property="classTreeId"/>
    <result column="chk02_content" property="content"/>
    <result column="chk02_explan" property="explan"/>
    <result column="chk02_cutoff" property="cutoff"/>
    <result column="chk02_window_no" property="windowNo"/>
    <result column="chk02_seq" property="seq"/>
    <result column="chk02_use_yn" property="useYn"/>
    <result column="chk02_admin_daily_list_id" property="adminDailyListId"/>
    <result column="chk01_class_tree_nm" property="classTreeName"/>
    <result column="chk02_reason" property="reason"/>
    <result column="chk02_note" property="note"/>
</resultMap>

<select id="selectByAdmin" resultMap="mapper" parameterType="HashMap">
    SELECT chk01_class_tree_nm,
           chk02_daily_list.*
      FROM chk02_daily_list
     INNER JOIN chk01_class_tree ON chk01_class_tree_id = chk02_class_tree_id
     WHERE chk02_company_id = #{companyId}
</select>
</mapper>
""",
        encoding="utf-8",
    )

    # Screen Java
    (chk_dir / "Chk02_Tab_DailyListAdmin.java").write_text(
        """package myApp.client.vi.chk;
import myApp.client.vi.chk.model.Chk02_DailyListModel;
import myApp.client.vi.chk.model.Chk02_DailyListModelProperties;
public class Chk02_Tab_DailyListAdmin {
    private Grid<Chk02_DailyListModel> grid;
    public Chk02_Tab_DailyListAdmin() {
        this.grid = this.buildGrid();
        retrieve();
    }
    public Grid<Chk02_DailyListModel> buildGrid() {
        Chk02_DailyListModelProperties properties = GWT.create(Chk02_DailyListModelProperties.class);
        GridBuilder<Chk02_DailyListModel> gridBuilder = new GridBuilder<Chk02_DailyListModel>(properties.keyId());
        gridBuilder.addBoolean(properties.adminYn(), 70, "관리자");
        gridBuilder.addText(properties.classTreeName(), 120, "문서분류");
        gridBuilder.addText(properties.content(), 350, "점검내용", new TextField());
        gridBuilder.addText(properties.reason(), 200, "설명", new TextField());
        gridBuilder.addLong(properties.seq(), 60, "순서", new LongField());
        return gridBuilder.getGrid();
    }
    public void retrieve() {
        GridRetrieveData<Chk02_DailyListModel> service = new GridRetrieveData<Chk02_DailyListModel>(grid.getStore());
        service.execute("chk.Chk02_DailyList.selectByAdmin");
    }
}
""",
        encoding="utf-8",
    )

    # GridInsertRow Java
    (svc_dir / "GridInsertRow.java").write_text(
        """package myApp.client.service;
public class GridInsertRow<T> {
    public void insertRow(Grid<T> grid, GridDataModel insertModel){
        this.grid = grid;
        this.insertModel = insertModel;
        ServiceRequest request = new ServiceRequest("getSeq");
        ServiceCall service = new ServiceCall();
        service.execute(request, this);
    }
    public void insertRow(Grid<T> grid, GridDataModel insertModel, InterfaceCallbackResult callback){
        this.callback = callback;
        this.insertRow(grid, insertModel);
    }
}
""",
        encoding="utf-8",
    )

    screens_dir = src_index_dir / "chk" / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)
    (screens_dir / "Chk02_Tab_DailyListAdmin.md").write_text(
        """### Chk02_Tab_DailyListAdmin
#### 이벤트
- **[E0]** 생성자 초기 로드
- **[E1]** 조회 버튼
""",
        encoding="utf-8",
    )

    events._ALL_DBML_PARSED_TABLES = None
    return src_root, src_index_dir


def test_037_1_model_wildcard_table_column_verification(tmp_path: Path):
    """037-1: analysis model --sql 에서 테이블.* 매칭 시 실제 DB 테이블 컬럼 존재 여부 검증."""
    src_root, src_index = _setup_chk02_fixture(tmp_path)
    obj = model.resolve(
        "Chk02_DailyListModel",
        {"src": src_root, "src_index": src_index, "sql": "chk02_daily_list.selectByAdmin"},
    )
    rendered = model.render(obj, fmt="md")
    assert "| content | content | String | chk02_content | ✅(chk02_daily_list.*) |" in rendered
    assert "| reason | reason | String | chk02_reason | ⚠ 테이블에 열 없음 |" in rendered
    assert "| note | note | String | chk02_note | ⚠ 테이블에 열 없음 |" in rendered
    assert "| adminYn | adminYn |  | 계산(getter L17-20) | 계산 |" in rendered


def test_037_2_grid_column_verification(tmp_path: Path):
    """037-2: analysis grid 에서 컬럼 검증(✅ / 계산 / ⚠ 테이블에 없음) 표시."""
    src_root, src_index = _setup_chk02_fixture(tmp_path)
    obj = grid.resolve(
        "Chk02_Tab_DailyListAdmin",
        {"src": src_root, "src_index": src_index, "check_columns": True},
    )
    rendered = grid.render(obj, fmt="md", opts={"check_columns": True})
    assert "컬럼 검증" in rendered
    assert "| 1 | adminYn |" in rendered and "| 계산 |" in rendered
    assert "| 4 | reason |" in rendered and "| ⚠ 테이블에 없음 |" in rendered
    assert "| 3 | content |" in rendered and "| ✅ |" in rendered



def test_037_3_port_sql_calculated_getter(tmp_path: Path):
    """037-3: port-sql --cols 에 계산 getter가 포함될 때 주석, SQL 후보, 반환 타입 반영."""
    src_root, _ = _setup_chk02_fixture(tmp_path)
    res = port_sql(
        "chk02_daily_list.selectByAdmin",
        src_root=src_root,
        cols=["adminYn", "classTreeName", "content", "seq"],
        getter_defaults=True,
        dto_package="kr.co.kfs.asseterp.biz.chk.dto",
    )
    assert res.ok
    out = res.data["output"]
    assert "// getAdminYn L17-20: companyId == 0 || adminDailyListId != 0" in out
    assert "Boolean adminYn" in out
    assert "-- getAdminYn L17-20: (chk02_company_id = 0 OR COALESCE(chk02_admin_daily_list_id,0) <> 0) AS admin_yn" in out


def test_037_4_method_overload_short_code_and_delegation(tmp_path: Path):
    """037-4: analysis method -o code 에서 짧은 오버로드/위임 관계 본문 동시 출력 및 Exit 0."""
    src_root, src_index = _setup_chk02_fixture(tmp_path)
    obj = method.resolve(
        "GridInsertRow.insertRow",
        {"src": src_root, "src_index": src_index, "output": "code"},
    )
    rendered = method.render(obj, fmt="code", opts={"output": "code"})
    assert "#1:" in rendered
    assert "#2:" in rendered and "→ #1 위임" in rendered
    assert "// #1 (" in rendered
    assert "// #2 (" in rendered
    assert "this.insertRow(grid, insertModel);" in rendered


def test_037_5_ui_tobe_e0_missing_hint(tmp_path: Path):
    """037-5: analysis ui --tobe 에서 E0(미구현) 발생 시 생성자 이벤트 주석 안내 출력."""
    src_root, src_index = _setup_chk02_fixture(tmp_path)
    tobe_dir = tmp_path / "tobe"
    tobe_dir.mkdir(parents=True, exist_ok=True)
    (tobe_dir / "Chk02_Tab_DailyListAdmin.tsx").write_text(
        """// AS-IS: Chk02_Tab_DailyListAdmin.java
export function Chk02_Tab_DailyListAdmin() {
    // [E1] 조회
    return <div />;
}
""",
        encoding="utf-8",
    )
    obj = ui.resolve(
        "Chk02_Tab_DailyListAdmin",
        {"src": src_root, "src_index": src_index, "tobe": str(tobe_dir)},
    )
    rendered = ui.render(obj, fmt="md")
    assert "E0(미구현)" in rendered
    assert "E0은 생성자 이벤트 — 대응 코드 근처에 `// [E0] …` 주석을 달면 된다" in rendered

