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
