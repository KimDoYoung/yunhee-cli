from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import outliner


def test_outline_java(tmp_path: Path):
    java_code = """package com.example.demo;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/roles")
public class RoleController {

    @GetMapping
    public List<RoleDto> getRoles(@RequestParam String keyword) {
        return List.of();
    }

    @PostMapping
    public RoleDto createRole(@RequestBody RoleDto dto) {
        return dto;
    }
}
"""
    f = tmp_path / "RoleController.java"
    f.write_text(java_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "@RestController" in joined
    assert '@RequestMapping("/api/v1/roles")' in joined
    assert "class RoleController" in joined
    assert "@GetMapping" in joined
    assert "getRoles" in joined
    assert "@PostMapping" in joined
    assert "createRole" in joined


def test_outline_mybatis_xml(tmp_path: Path):
    xml_code = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="kr.co.kfs.RoleMapper">

    <select id="selectByCondition" resultType="kr.co.kfs.RoleDto">
        SELECT * FROM sys04_role
    </select>

    <insert id="insert">
        INSERT INTO sys04_role (id, name) VALUES (#{id}, #{name})
    </insert>

    <update id="update">
        UPDATE sys04_role SET name = #{name} WHERE id = #{id}
    </update>

    <delete id="delete">
        DELETE FROM sys04_role WHERE id = #{id}
    </delete>
</mapper>
"""
    f = tmp_path / "RoleMapper.xml"
    f.write_text(xml_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert '<mapper namespace="kr.co.kfs.RoleMapper">' in joined
    assert "select #selectByCondition (resultType=RoleDto)" in joined
    assert "insert #insert" in joined
    assert "update #update" in joined
    assert "delete #delete" in joined


def test_outline_typescript(tmp_path: Path):
    ts_code = """export interface Role {
    id: string;
    name: string;
}

export type RoleStatus = 'ACTIVE' | 'INACTIVE';

export async function fetchRoles(): Promise<Role[]> {
    return [];
}

export const updateRole = async (role: Role): Promise<void> => {
    // update
};
"""
    f = tmp_path / "roleApi.ts"
    f.write_text(ts_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "export interface Role" in joined
    assert "export type RoleStatus" in joined
    assert "export function fetchRoles" in joined
    assert "export const updateRole" in joined


def test_outline_directory_and_cli(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "A.java").write_text("public class A { public void run() {} }", encoding="utf-8")
    (sub / "B.xml").write_text('<mapper namespace="B"><select id="find"/></mapper>', encoding="utf-8")

    res = outliner.outline_path(tmp_path)
    assert res.ok is True
    assert "A.java" in res.data
    assert "class A" in res.data
    assert "B.xml" in res.data
    assert "select #find" in res.data

    runner_cli = CliRunner()
    cli_res = runner_cli.invoke(cli.app, ["outline", str(tmp_path)])
    assert cli_res.exit_code == 0
    assert "A.java" in cli_res.output


def test_outline_java_multiline_params_and_dot_types(tmp_path: Path):
    java_code = """package com.example.demo;

@RestController
@RequestMapping("/api/v1/sys")
public class SysRoleController {

    @GetMapping("/roles")
    public List<MenuRes.Level1> getMenus(
            @RequestParam(name = "companyId", required = false) Long companyId,
            @RequestParam(defaultValue = "10") Integer limit
    ) {
        return List.of();
    }

    @PutMapping("/roles/{roleId}/menus")
    public ResponseEntity<Void> updateRoleMenus(
            @AuthenticationPrincipal User user,
            @PathVariable("roleId") Long roleId,
            @RequestBody @Valid List<RoleRow> rows
    ) {
        return ResponseEntity.ok().build();
    }
}
"""
    f = tmp_path / "SysRoleController.java"
    f.write_text(java_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    # 점이 든 반환형 보존 확인
    assert "List<MenuRes.Level1> getMenus(Long companyId, Integer limit)" in joined
    # 멀티라인 파라미터 및 타입+이름 보존 확인
    assert "ResponseEntity<Void> updateRoleMenus(User user, Long roleId, List<RoleRow> rows)" in joined


def test_outline_java_interface_methods(tmp_path: Path):
    java_code = """package com.example.demo.mapper;

import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SysRoleMapper {

    List<SysRole> selectRoles(SysRoleParam param);

    SysRole selectRoleById(Long roleId);

    int insertRole(SysRole role);

    int updateRole(SysRole role);
}
"""
    f = tmp_path / "SysRoleMapper.java"
    f.write_text(java_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "interface SysRoleMapper" in joined
    assert "List<SysRole> selectRoles(SysRoleParam param)" in joined
    assert "SysRole selectRoleById(Long roleId)" in joined
    assert "int insertRole(SysRole role)" in joined
    assert "int updateRole(SysRole role)" in joined


def test_outline_tsx_api_object_and_components(tmp_path: Path):
    tsx_code = """import React from 'react';

export interface RoleProps {
    roleId: number;
}

export const sysApi = {
    searchRoles: async (param: SysRoleParam) => {
        return [];
    },
    getMenus: (companyId: number) => {
        return [];
    },
    updateRoleMenus: async (user: string, roleId: number, rows: RoleRow[]) => {
        // do update
    }
};

export const RoleAdmin: React.FC<RoleProps> = ({ roleId }) => {
    return <div>Role Admin {roleId}</div>;
};

export const SimpleView: React.FC = () => {
    return <div>Simple View</div>;
};
"""
    f = tmp_path / "RoleAdmin.tsx"
    f.write_text(tsx_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "export interface RoleProps" in joined
    assert "export const sysApi = {" in joined
    assert "searchRoles: (param: SysRoleParam)" in joined
    assert "getMenus: (companyId: number)" in joined
    assert "updateRoleMenus: (user: string, roleId: number, rows: RoleRow[])" in joined
    assert "export const RoleAdmin: React.FC<RoleProps>" in joined
    assert "export const SimpleView: React.FC" in joined


def test_outline_ts_generics(tmp_path: Path):
    ts_code = """export function useTreeGrid<T extends object>(options: TreeGridOptions<T>) {
    return {};
}

export function useGridCrud<T extends object>(options: GridCrudOptions<T>) {
    return {};
}

export const editableCol = <T,>(col: ColDef<T>): ColDef<T> => {
    return col;
};
"""
    f = tmp_path / "useGrid.ts"
    f.write_text(ts_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "export function useTreeGrid<T extends object>(options: TreeGridOptions<T>)" in joined
    assert "export function useGridCrud<T extends object>(options: GridCrudOptions<T>)" in joined
    assert "export const editableCol = <T,>(col: ColDef<T>) =>" in joined


def test_outline_java_enum_constants(tmp_path: Path):
    enum_code = """package com.example.demo.error;

public enum ErrorCode {
    UNAUTHORIZED(401, "인증 필요"),
    LOGIN_FAILED(401, "로그인 실패"),
    ACCOUNT_LOCKED(403, "계정 잠김"),
    FORBIDDEN(403, "권한 없음"),
    NOT_FOUND(404, "리소스 없음"),
    METHOD_NOT_ALLOWED(405, "허용되지 않는 메서드"),
    CONFLICT(409, "충돌"),
    INVALID_INPUT(400, "잘못된 입력"),
    INTERNAL_ERROR(500, "서버 오류");

    private final int status;
    private final String message;

    ErrorCode(int status, String message) {
        this.status = status;
        this.message = message;
    }

    public boolean isAuthError() {
        return this == UNAUTHORIZED || this == LOGIN_FAILED;
    }
}
"""
    f = tmp_path / "ErrorCode.java"
    f.write_text(enum_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "enum ErrorCode" in joined
    assert "constants(9): UNAUTHORIZED, LOGIN_FAILED, ACCOUNT_LOCKED, FORBIDDEN, NOT_FOUND, METHOD_NOT_ALLOWED, CONFLICT, INVALID_INPUT, ..., INTERNAL_ERROR" in joined
    assert "ErrorCode(int status, String message)" in joined
    assert "boolean isAuthError()" in joined
    # 상수가 메서드로 오인되어 거대한 한 줄이 생기지 않았는지 확인
    assert "UNAUTHORIZED(" not in [line.split(":")[-1].strip() for line in lines if "constants" not in line]


def test_outline_java_record_components(tmp_path: Path):
    record_code = """package com.example.demo.model;

public record Tenant(String host, String code, CompanyRes company, boolean admin) {

    public boolean isValid() {
        return host != null && !host.isBlank();
    }
}

class Service {
    public record RotationResult(RotationStatus status, String refreshId) {}
}
"""
    f = tmp_path / "Tenant.java"
    f.write_text(record_code, encoding="utf-8")

    lines = outliner.outline_file(f)
    joined = "\n".join(lines)
    assert "record Tenant(String host, String code, CompanyRes company, boolean admin)" in joined
    assert "boolean isValid()" in joined
    assert "record RotationResult(RotationStatus status, String refreshId)" in joined
    # record Tenant(...) 가 메서드로 중복 추출되지 않았는지 확인
    tenant_lines = [line for line in lines if "Tenant" in line]
    assert len(tenant_lines) == 1

