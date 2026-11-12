"""결재 상신 및 승인 원스톱 자동화 도구 (`biz-appr`).

업무 행(휴가, 연장근무, 오후근무, 연봉계약 등)에 대한 전자결재 상신(문서 생성 및 본문 조립)과
업무 행 결재 ID 연결, 결재자 승인(또는 반려)을 한 번에 실행한다.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from yunhee.tools import api_client

# 기본 링크코드별 업무 행 연결 API 매핑
DEFAULT_LINK_APIS: dict[str, dict[str, str]] = {
    "A74": {"path": "/api/v1/att/overtime-reqs/me/{ref}/appr", "style": "query"},
    "A73": {"path": "/api/v1/att/pm-works/{ref}/appr", "style": "query"},
    "D01": {"path": "/api/v1/pay/annuals/{ref}/appr-id", "style": "body"},
}


def get_class_tree_id(link_code: str, company_id: int | str, db_name: str | None = None) -> int | None:
    """dcr30_link 테이블에서 회사의 링크코드에 연결된 classTreeId를 조회한다."""
    try:
        import psycopg
        from psycopg.rows import dict_row

        from yunhee.tools.sql_runner import get_connection_string

        db_url = get_connection_string(db_name)
        if not db_url:
            return None

        with psycopg.connect(db_url, autocommit=False) as conn:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT dcr30_class_tree_id
                    FROM dcr30_link
                    WHERE dcr30_company_id = %s AND dcr30_link_cd = %s
                    LIMIT 1;
                    """,
                    (int(company_id), link_code),
                )
                row = cur.fetchone()
                if row and row.get("dcr30_class_tree_id"):
                    return int(row["dcr30_class_tree_id"])
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def run_appr(
    link_code: str,
    ref_id: int | str,
    as_user: str,
    company: str,
    approvers: list[str],
    password: str | None = None,
    class_id: int | str | None = None,
    confirm: bool = False,
    reject: str | None = None,
    link_path: str | None = None,
    link_style: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """전자결재 상신 및 승인/반려 전체 흐름을 실행하고 결과 요약 라인 목록을 반환한다."""
    output_lines: list[str] = []

    # 1. 상신자 계정 정보 조회
    _user, _pw, user_info = api_client.resolve_user_credentials(as_user, company_code=company, password=password)
    comp_id = user_info.get("company_id", 0)
    user_id = user_info.get("user_id")

    # 2. 문서 분류 ID 결정
    class_tree_id: int | None = None
    if class_id:
        class_tree_id = int(class_id)
    else:
        class_tree_id = get_class_tree_id(link_code, comp_id)

    if not class_tree_id:
        raise ValueError(
            f"오류: 회사 관리자가 #1280 문서분류지정에서 {link_code} 분류를 지정해야 합니다 — "
            f"yunhee api PUT /api/v1/dcr/links -b '[{{\"linkId\":<id>,\"classTreeId\":<분류>}}]' -u admin -c {company}"
        )

    output_lines.append(f"분류 {class_tree_id} (dcr30_link {link_code})")

    # 3. 신규 문서 번호 및 첫 결재 단계 ID 발급
    res_new = api_client.request_api(
        "GET",
        "/api/v1/apr/apprs/new",
        params={"classTreeId": str(class_tree_id)},
        as_role=as_user,
        company_code=company,
        password=password,
    )
    if not res_new.ok:
        raise ValueError(f"신규 결재 문서 생성 실패: {res_new.error}")

    new_data = (res_new.data or {}).get("data") if isinstance(res_new.data, dict) else {}
    if not isinstance(new_data, dict):
        new_data = {}

    appr_id = new_data.get("apprId")
    if not appr_id:
        # text 파싱 시도
        try:
            txt_obj = json.loads(res_new.data.get("text", "{}"))
            new_data = txt_obj.get("data", {})
            appr_id = new_data.get("apprId")
        except Exception:  # noqa: BLE001, S110
            pass

    if not appr_id:
        raise ValueError(f"결재 문서 ID 발급 실패 (응답 본문 확인 필요): {res_new.data}")

    first_step_id = 0
    if new_data.get("steps") and isinstance(new_data["steps"], list) and len(new_data["steps"]) > 0:
        first_step_id = new_data["steps"][0].get("apprStepId", 0)

    # 4. link-seed 조회
    res_seed = api_client.request_api(
        "GET",
        "/api/v1/apr/apprs/link-seed",
        params={
            "classTreeId": str(class_tree_id),
            "linkCode": link_code,
            "refId": str(ref_id),
        },
        as_role=as_user,
        company_code=company,
        password=password,
    )
    seed_data = (res_seed.data or {}).get("data") if isinstance(res_seed.data, dict) else {}
    if not isinstance(seed_data, dict):
        try:
            txt_obj = json.loads(res_seed.data.get("text", "{}"))
            seed_data = txt_obj.get("data", {})
        except Exception:  # noqa: BLE001
            seed_data = {}

    title = seed_data.get("title") or f"{link_code} 신청서"
    content = seed_data.get("content") or "<p>(본문 없음)</p>"
    now_utc = datetime.datetime.now(tz=datetime.UTC)
    raw_effect = seed_data.get("effectDate")
    if not raw_effect:
        effect_date = now_utc.date().isoformat() + "T00:00:00"
    elif "T" not in raw_effect:
        effect_date = raw_effect + "T00:00:00"
    else:
        effect_date = raw_effect

    reg_date = seed_data.get("regDate") or now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    sign_company = seed_data.get("signCompany") or company

    # 5. steps 결재선 조립
    steps: list[dict[str, Any]] = [
        {
            "apprStepId": first_step_id,
            "stepTypeCode": "00",
            "seq": "001",
            "stepStatusCode": "10",
            "stepEmpId": user_id,
            "lockYn": "false",
        }
    ]

    for idx, apr_u in enumerate(approvers):
        _, _, apr_info = api_client.resolve_user_credentials(apr_u, company_code=company, password=password)
        apr_emp_id = apr_info.get("user_id")
        steps.append({
            "stepTypeCode": "10",
            "seq": f"{idx + 2:03d}",
            "stepStatusCode": "10",
            "stepEmpId": apr_emp_id,
            "lockYn": "false",
        })

    payload = {
        "mode": "request",
        "classTreeId": class_tree_id,
        "linkCode": link_code,
        "title": title,
        "content": content,
        "effectDate": effect_date,
        "regDate": reg_date,
        "signCompany": sign_company,
        "confirmed": True,
        "steps": steps,
    }

    if dry_run:
        output_lines.append(f"드라이런 페이로드 (PUT /api/v1/apr/apprs/{appr_id}):\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        return output_lines

    # 6. 상신 PUT 호출
    res_put = api_client.request_api(
        "PUT",
        f"/api/v1/apr/apprs/{appr_id}",
        as_role=as_user,
        company_code=company,
        password=password,
        json_body=payload,
    )
    if not res_put.ok:
        raise ValueError(f"결재 상신 실패 (PUT /api/v1/apr/apprs/{appr_id}): {res_put.error}")

    output_lines.append(f"상신 apprId={appr_id} 「{title}」 상태 10")

    # 7. 업무 행에 결재 ID 연결
    link_info = DEFAULT_LINK_APIS.get(link_code, {})
    l_path = link_path or link_info.get("path")
    l_style = link_style or link_info.get("style", "query")

    if l_path:
        target_path = l_path.replace("{ref}", str(ref_id)).replace("{id}", str(ref_id))
        if l_style == "body":
            res_link = api_client.request_api(
                "PUT",
                target_path,
                as_role=as_user,
                company_code=company,
                password=password,
                json_body={"apprId": appr_id},
            )
        else:
            res_link = api_client.request_api(
                "PUT",
                target_path,
                as_role=as_user,
                company_code=company,
                password=password,
                params={"apprId": str(appr_id)},
            )
        if not res_link.ok:
            output_lines.append(f"⚠ 업무 행 연결 실패 (PUT {target_path}): {res_link.error}")
        else:
            output_lines.append(f"연결 PUT {target_path} → 200")
    else:
        output_lines.append(f"연결 API를 찾지 못했습니다. --link-path '/api/v1/.../{ref_id}/appr' --link-style query|body 로 지정하세요.")

    # 8. 결재자 승인 또는 반려
    if confirm or reject:
        for i, apr_u in enumerate(approvers):
            is_last = (i == len(approvers) - 1)
            if reject and is_last:
                # 마지막 결재자가 반려
                confirm_body = {"action": "reject", "message": reject}
                res_act = api_client.request_api(
                    "POST",
                    f"/api/v1/apr/apprs/{appr_id}/confirm",
                    as_role=apr_u,
                    company_code=company,
                    password=password,
                    json_body=confirm_body,
                )
                if not res_act.ok:
                    raise ValueError(f"결재 반려 실패 ({apr_u}): {res_act.error}")
                output_lines.append(f"반려 {apr_u} → 반려 완료")
            else:
                confirm_body = {"action": "confirm"}
                res_act = api_client.request_api(
                    "POST",
                    f"/api/v1/apr/apprs/{appr_id}/confirm",
                    as_role=apr_u,
                    company_code=company,
                    password=password,
                    json_body=confirm_body,
                )
                if not res_act.ok:
                    raise ValueError(f"결재 승인 실패 ({apr_u}): {res_act.error}")
                output_lines.append(f"승인 {apr_u} → 30 완료")

    return output_lines
