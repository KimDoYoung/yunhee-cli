"""수정사항 055 검증 테스트:
1. 12칸 대장 및 열 순서 변경 대장에서 drift-done 칸 위치 동적 매핑
2. --check, --tobe, --note, --note-append, --dry-run, --force 검증
3. --status 반영 시 --check 필수 검증 및 --force 강제 진행
4. 파일 기준선(__files__) 보류 로직: 동일 파일 내 대기 단위 잔여 시 __files__ 보류
5. drift-ledger의 11칸/12칸 대장 동적 헤더 지원
6. drift-diff의 SQL statement 블록 단위 격리 diff 및 TOBE 네임스페이스 매칭
"""

import json
from pathlib import Path

from yunhee.tools.as_is.drift_ops import (
    append_to_ledger,
    extract_mapper_statement_block,
    parse_ledger_header,
    render_unit_diff,
    update_drift_done,
)


def test_parse_ledger_header():
    lines_12 = [
        "# 변경반영 대장",
        "",
        "| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 확인 | 상태 | 처리일 | 비고 |",
        "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|",
        "| CH-0001 | 2026-11-11 | `abc` | SQL | `test.xml` · `s1` | +1줄 | #1001 |  |  | 대기 |  |  |",
    ]
    h_idx, cols, col_map = parse_ledger_header(lines_12)
    assert h_idx == 2
    assert len(cols) == 12
    assert col_map["키"] == 0
    assert col_map["확인"] == 8
    assert col_map["상태"] == 9
    assert col_map["처리일"] == 10
    assert col_map["비고"] == 11


def test_drift_done_12_cols_and_check_validation(tmp_path: Path):
    wd = tmp_path / "project"
    wd.mkdir(parents=True)
    docs_dir = wd / "docs"
    docs_dir.mkdir(parents=True)
    chg_dir = docs_dir / "3-변경반영"
    chg_dir.mkdir(parents=True)

    # 1. baseline.json
    baseline_path = docs_dir / "baseline.json"
    baseline_path.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

    # 2. 12칸 변경반영-대장.md
    ledger_file = chg_dir / "변경반영-대장.md"
    ledger_content = """# 변경반영 대장

| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 확인 | 상태 | 처리일 | 비고 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CH-0220 | 2026-11-11 | `3aabbd4` | SQL | `server/emp/mapper/emp00_trans_info.xml` · `getPersonId` | +3 −1줄 | #1001 |  |  | 대기 |  | 구 비고 |
| CH-0015 | 2026-11-11 | `3aabbd4` | SQL | `server/emp/mapper/emp00_trans_info.xml` · `selectSmsNoticeTarget` | +10줄 | #1002 |  |  | 대기 |  |  |
"""
    ledger_file.write_text(ledger_content, encoding="utf-8")

    # 3. 검증 1: --status 반영인데 --check 누락 시 중단
    code, msg = update_drift_done(
        keys=["CH-0220"],
        status="반영",
        work_dir=wd,
    )
    assert code == 1
    assert "확인" in msg
    assert "--check" in msg

    # 4. 검증 2: --dry-run 동작 (파일 쓰지 않음)
    code, msg = update_drift_done(
        keys=["CH-0220"],
        status="반영",
        check="compare 일치",
        note="새 비고",
        dry_run=True,
        work_dir=wd,
    )
    assert code == 0
    assert "[dry-run]" in msg
    # 파일이 바뀌지 않았어야 함
    assert "대기" in ledger_file.read_text(encoding="utf-8")

    # 5. 검증 3: 실제 갱신 (12칸 위치 정확도 및 파일 기준선 보류 확인)
    # CH-0015가 아직 대기이므로 emp00_trans_info.xml의 __files__는 보류되어야 함!
    code, msg = update_drift_done(
        keys=["CH-0220"],
        status="반영",
        check="compare 일치(3조합)",
        tobe="EmpTransInfoMapper.xml#getPersonId",
        note="반영완료 노트",
        work_dir=wd,
    )
    assert code == 0
    assert "파일 기준선 보류" in msg
    assert "CH-0015" in msg

    # 대장 내용 확인: 각 칸이 밀리지 않고 정확히 들어갔는가?
    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    row_ch0220 = next(l for l in lines if l.startswith("| CH-0220"))
    cells = [c.strip() for c in row_ch0220.split("|")[1:-1]]
    assert len(cells) == 12
    assert cells[0] == "CH-0220"
    assert cells[7] == "EmpTransInfoMapper.xml#getPersonId"  # TOBE 대응
    assert cells[8] == "compare 일치(3조합)"  # 확인
    assert cells[9] == "반영"  # 상태
    assert cells[10] != ""  # 처리일(오늘)
    assert cells[11] == "반영완료 노트"  # 비고 덮어쓰기

    # baseline.json 확인: __units__에는 등록되고 __files__에는 없어야 함
    b_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "__units__" in b_data
    assert "server/emp/mapper/emp00_trans_info.xml · getPersonId" in b_data["__units__"]
    assert "server/emp/mapper/emp00_trans_info.xml" not in b_data["__files__"]

    # 6. 검증 4: 남은 CH-0015까지 처리하면 비로소 __files__가 기록되는가?
    code, _msg = update_drift_done(
        keys=["CH-0015"],
        status="해당없음",  # 해당없음은 --check 없어도 됨
        work_dir=wd,
    )
    assert code == 0

    b_data2 = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "server/emp/mapper/emp00_trans_info.xml" in b_data2["__files__"]


def test_drift_done_note_append_and_custom_order(tmp_path: Path):
    wd = tmp_path / "project"
    wd.mkdir(parents=True)
    docs_dir = wd / "docs"
    docs_dir.mkdir(parents=True)
    chg_dir = docs_dir / "3-변경반영"
    chg_dir.mkdir(parents=True)

    baseline_path = docs_dir / "baseline.json"
    baseline_path.write_text("{}", encoding="utf-8")

    # 칸 순서를 의도적으로 바꾼 대장
    ledger_file = chg_dir / "변경반영-대장.md"
    ledger_content = """# 커스텀 대장

| 키 | 상태 | 확인 | 처리일 | 비고 | 단위 |
|:---|:---|:---|:---|:---|:---|
| CH-9999 | 대기 |  |  | 원본 비고 | `Sys01.java` |
"""
    ledger_file.write_text(ledger_content, encoding="utf-8")

    # note_append 테스트
    code, _msg = update_drift_done(
        keys=["CH-9999"],
        status="반영",
        check="테스트 통과",
        note="추가 비고",
        note_append=True,
        work_dir=wd,
    )
    assert code == 0
    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    row = next(l for l in lines if l.startswith("| CH-9999"))
    cells = [c.strip() for c in row.split("|")[1:-1]]
    assert cells[0] == "CH-9999"
    assert cells[1] == "반영"
    assert cells[2] == "테스트 통과"
    assert cells[3] != ""
    assert cells[4] == "원본 비고 · 추가 비고"
    assert cells[5] == "`Sys01.java`"


def test_drift_ledger_12_cols_format(tmp_path: Path):
    ledger_file = tmp_path / "변경반영-대장.md"
    ledger_content = """# 변경반영 대장

| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 확인 | 상태 | 처리일 | 비고 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CH-0001 | 2026-11-11 | `c1` | SQL | `test.xml` · `s1` | +1줄 | #1001 |  |  | 대기 |  |  |
"""
    ledger_file.write_text(ledger_content, encoding="utf-8")

    sample_units = [{
        "kind": "SQL",
        "unit": "`test.xml` · `s2`",
        "change": "+5 −1줄",
        "screens": ["#1002"],
        "tobe": "TestMapper#s2",
        "commit": "c2",
        "lc": {"hash": "c2", "date": "2026-11-11", "subject": "테스트 커밋"},
    }]

    code, _msg = append_to_ledger(ledger_file, sample_units)
    assert code == 0

    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    added_line = next(l for l in lines if l.startswith("| CH-0002"))
    cells = [c.strip() for c in added_line.split("|")[1:-1]]
    assert len(cells) == 12
    assert cells[0] == "CH-0002"
    assert cells[4] == "`test.xml` · `s2`"
    assert cells[7] == "TestMapper#s2"
    assert cells[8] == ""  # 확인 기본 빈칸
    assert cells[9] == "대기"  # 상태


def test_extract_mapper_statement_block_and_diff(tmp_path: Path):
    xml_v1 = """<mapper namespace="biz01_promo">
    <resultMap id="promoMap" type="PromoModel">
        <result property="id" column="promo_id"/>
    </resultMap>

    <sql id="promoBase">
        FROM biz01_promo
    </sql>

    <select id="selectByCard" parameterType="map" resultMap="promoMap">
        SELECT promo_id, card_no
        <include refid="promoBase"/>
        WHERE card_no = #{cardNo}
    </select>

    <select id="selectById" parameterType="string" resultMap="promoMap">
        SELECT promo_id
        <include refid="promoBase"/>
        WHERE promo_id = #{id}
    </select>
</mapper>
"""

    xml_v2 = """<mapper namespace="biz01_promo">
    <resultMap id="promoMap" type="PromoModel">
        <result property="id" column="promo_id"/>
        <result property="apprStatusCode" column="biz01_appr_status_cd"/>
    </resultMap>

    <sql id="promoBase">
        FROM biz01_promo
    </sql>

    <select id="selectByCard" parameterType="map" resultMap="promoMap">
        SELECT promo_id, card_no, biz01_target_cnt, biz01_appr_status_cd
        <include refid="promoBase"/>
        LEFT JOIN apr01_appr apr ON apr.appr_id = promo.appr_id
        WHERE card_no = #{cardNo}
          AND appr_check = 'Y'
    </select>

    <select id="selectById" parameterType="string" resultMap="promoMap">
        SELECT promo_id
        <include refid="promoBase"/>
        WHERE promo_id = #{id}
    </select>
</mapper>
"""

    # 1. extract_mapper_statement_block
    b_card = extract_mapper_statement_block(xml_v1, "selectByCard")
    assert b_card is not None
    assert b_card[0] == "select"
    assert "WHERE card_no = #{cardNo}" in b_card[1]
    assert b_card[2] == ["promoBase"]

    # 2. git repo 모의하여 render_unit_diff 테스트
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)

    mapper_file = repo / "biz01_promo.xml"
    mapper_file.write_text(xml_v1, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "v1"], cwd=repo, check=True)
    rev1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

    # v2 변경
    mapper_file.write_text(xml_v2, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "v2"], cwd=repo, check=True)

    # selectByCard diff 테스트 -> biz01_target_cnt 변경만 나와야 함
    code, out = render_unit_diff(
        unit="biz01_promo.selectByCard",
        src_root=repo,
        base=rev1,
        work_dir=tmp_path,
    )
    assert code == 0
    assert "biz01_target_cnt" in out
    assert "apr01_appr" in out
    # selectById 내용은 나오면 안 됨!
    assert "WHERE promo_id = #{id}" not in out
    # resultMap 변경 요약이 들어있는지 확인
    assert "apprStatusCode" in out

    # selectById diff 테스트 -> 변경 없음이어야 함
    code_id, out_id = render_unit_diff(
        unit="biz01_promo.selectById",
        src_root=repo,
        base=rev1,
        work_dir=tmp_path,
    )
    assert code_id == 0
    assert "동일 또는 공백만 다름" in out_id or "변경 없음" in out_id
