from pathlib import Path

from yunhee.tools.test.signature import (
    get_method_signature,
    parse_mapper_java_file,
)

# 집 PC 환경의 AssetERP 소스 루트가 존재할 경우 테스트, 없을 경우 인라인 샘플 테스트
SAMPLE_JAVA = """
package kr.co.kfs.asseterp.biz.emp.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.time.LocalDate;
import java.util.List;

@Mapper
public interface EmpDeductMapper {
    /** AS-IS emp36_add_deduct.addDeductTypeInsert — 이전 이력 복사 + 빠진 타입 0으로 채움 */
    int insertAddDeductTypes(@Param("deductId") Long deductId,
                             @Param("personId") Long personId,
                             @Param("startDate") LocalDate startDate,
                             @Param("companyId") Long companyId,
                             @Param("itemTypeCodeName") String itemTypeCodeName);
}
"""

SAMPLE_FRM = """
package kr.co.kfs.asseterp.biz.frm.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.time.LocalDate;
import java.util.List;

@Mapper
public interface FrmListMapper {
    List<Object> selectIcsNotice(@Param("companyId") Long companyId, @Param("empId") Long empId,
                                  @Param("orgCd") Long orgCd, @Param("selectDate") LocalDate selectDate);
}
"""

SAMPLE_BATCH = """
package kr.co.kfs.asseterp.biz.batch.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.time.LocalDate;

public interface BatchSchMapper {
    int insertSch04List(@Param("companyId") Long companyId, @Param("stdDate") LocalDate stdDate);
}
"""

def test_parse_emp_deduct(tmp_path: Path):
    f = tmp_path / "EmpDeductMapper.java"
    f.write_text(SAMPLE_JAVA, encoding="utf-8")
    sigs = parse_mapper_java_file(f)
    assert "insertAddDeductTypes" in sigs
    sig = sigs["insertAddDeductTypes"]
    assert len(sig.params) == 5
    p_dict = {p.name: (p.java_type, p.pg_type) for p in sig.params}
    assert p_dict["deductId"] == ("Long", "numeric")
    assert p_dict["personId"] == ("Long", "numeric")
    assert p_dict["startDate"] == ("LocalDate", "date")
    assert p_dict["companyId"] == ("Long", "numeric")
    assert p_dict["itemTypeCodeName"] == ("String", "text")

def test_parse_frm_list(tmp_path: Path):
    f = tmp_path / "FrmListMapper.java"
    f.write_text(SAMPLE_FRM, encoding="utf-8")
    sigs = parse_mapper_java_file(f)
    assert "selectIcsNotice" in sigs
    sig = sigs["selectIcsNotice"]
    assert len(sig.params) == 4
    p_dict = {p.name: (p.java_type, p.pg_type) for p in sig.params}
    assert p_dict["companyId"] == ("Long", "numeric")
    assert p_dict["empId"] == ("Long", "numeric")
    assert p_dict["orgCd"] == ("Long", "numeric")
    assert p_dict["selectDate"] == ("LocalDate", "date")

def test_parse_batch_sch(tmp_path: Path):
    f = tmp_path / "BatchSchMapper.java"
    f.write_text(SAMPLE_BATCH, encoding="utf-8")
    sigs = parse_mapper_java_file(f)
    assert "insertSch04List" in sigs
    sig = sigs["insertSch04List"]
    assert len(sig.params) == 2
    p_dict = {p.name: (p.java_type, p.pg_type) for p in sig.params}
    assert p_dict["companyId"] == ("Long", "numeric")
    assert p_dict["stdDate"] == ("LocalDate", "date")


def test_real_asseterp_signatures():
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return
    sig1 = get_method_signature("kr.co.kfs.asseterp.biz.emp.mapper.EmpDeductMapper", "insertAddDeductTypes", src_root=real_root)
    assert sig1 is not None
    assert "deductId" in sig1.param_map
    assert sig1.param_map["deductId"].pg_type == "numeric"
    assert sig1.param_map["startDate"].pg_type == "date"
    assert sig1.param_map["itemTypeCodeName"].pg_type == "text"

    sig2 = get_method_signature("kr.co.kfs.asseterp.biz.frm.mapper.FrmListMapper", "selectIcsNotice", src_root=real_root)
    assert sig2 is not None
    assert sig2.param_map["companyId"].pg_type == "numeric"
    assert sig2.param_map["selectDate"].pg_type == "date"

    sig3 = get_method_signature("kr.co.kfs.asseterp.biz.batch.mapper.BatchSchMapper", "insertSch04List", src_root=real_root)
    assert sig3 is not None
    assert sig3.param_map["companyId"].pg_type == "numeric"
    assert sig3.param_map["stdDate"].pg_type == "date"
