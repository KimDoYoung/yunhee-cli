"""결재 상신 및 승인 원스톱 자동화 도구 (`biz-appr`).

업무 행(휴가, 연장근무, 오후근무, 연봉계약 등)에 대한 전자결재 상신(문서 생성 및 본문 조립)과
업무 행 결재 ID 연결, 결재자 승인(또는 반려)을 한 번에 실행한다.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from yunhee.tools import api_client

# 기본 링크코드별 업무 행 연결 API 매핑 (061 #3, #9)
DEFAULT_LINK_APIS: dict[str, dict[str, str]] = {
    "A74": {"path": "/api/v1/att/overtime-reqs/me/{ref}/appr", "style": "query"},
    "A73": {"path": "/api/v1/att/pm-works/{ref}/appr", "style": "query"},
    "D01": {"path": "/api/v1/pay/annuals/{ref}/appr-id", "style": "body"},
    "A02": {"path": "/api/v1/pay/relate-apprs/{ref}/appr-id", "style": "body"},
    "A05": {"path": "/api/v1/pay/relate-apprs/{ref}/appr-id", "style": "body"},
    "X01": {"path": "/api/v1/pay/tax-withholdings/{ref}/appr-id", "style": "body"},
    "A63": {"path": "/api/v1/pay/expenses/appr-id", "style": "ids-body"},
    "A64": {"path": "/api/v1/pay/expenses/settle-appr-id", "style": "ids-body"},
}


def find_link_path_candidates(link_code: str, root_dir: Any = None) -> list[str]:
    """해당 링크 코드 또는 시스템 내에서 결재 연동 가능한 PUT .../appr-id 또는 .../appr API 후보를 탐색한다 (064 #10)."""
    # 알려진 연동 코드별 후보 매핑 테이블 (FND / ICS / TDM 등)
    KNOWN_CANDIDATES: dict[str, list[str]] = {
        "A27": ["/api/v1/ics/checklist-confirms/relate-apprs/appr-id"],
        "A32": ["/api/v1/ics/compliance-reports/appr-id"],
        "A60": ["/api/v1/est/pf-contracts/{ref}/plan-appr-id"],
        "A61": ["/api/v1/est/pf-contracts/{ref}/plan-appr-id"],
    }
    if link_code in KNOWN_CANDIDATES:
        return KNOWN_CANDIDATES[link_code]

    from pathlib import Path

    from yunhee.config import WORK_DIR
    from yunhee.tools.biz.endpoints import collect_endpoints

    rd = Path(root_dir) if root_dir else WORK_DIR
    try:
        eps = collect_endpoints(root_dir=rd)
        cands: list[str] = []
        for ep in eps:
            p = ep.get("path", "")
            if ep.get("method") == "PUT" and p.endswith(("/appr-id", "/appr")):
                cands.append(p)
        return cands
    except Exception:  # noqa: BLE001
        return []


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
    ref_id: int | str | None = None,
    as_user: str = "401",
    company: str = "kalpa",
    approvers: list[str] | None = None,
    password: str | None = None,
    class_id: int | str | None = None,
    confirm: bool = False,
    reject: str | None = None,
    link_path: str | None = None,
    link_style: str | None = None,
    dry_run: bool = False,
    pre: str | None = None,
    seed_args: list[str] | None = None,
    title: str | None = None,
    content: str | None = None,
    link_body: str | None = None,
) -> list[str]:
    """전자결재 상신 및 승인/반려 전체 흐름을 실행하고 결과 요약 라인 목록을 반환한다."""
    if approvers is None:
        approvers = []
    output_lines: list[str] = []

    # 0. --pre 처리 (061 #4: 상신 전 업무 행 생성 API 호출)
    if pre:
        parts = pre.strip().split(maxsplit=2)
        if len(parts) < 2:
            raise ValueError("오류: --pre 형식은 '<METHOD> <path> [<json>]' 이어야 합니다.")
        pre_method = parts[0].upper()
        pre_path = parts[1]
        pre_body = json.loads(parts[2]) if len(parts) > 2 else None

        if dry_run:
            output_lines.append(f"사전 호출(dry-run): {pre_method} {pre_path} 본문 {json.dumps(pre_body, ensure_ascii=False) if pre_body else '{}'}")
            if not ref_id:
                ref_id = 999999
        else:
            res_pre = api_client.request_api(
                method=pre_method,
                path=pre_path,
                as_role=as_user,
                company_code=company,
                password=password,
                json_body=pre_body,
            )
            if not res_pre.ok:
                raise ValueError(f"사전 호출 실패 ({pre_method} {pre_path}): {res_pre.error}")
            pre_data = (res_pre.data or {}).get("data")
            if pre_data is None and isinstance(res_pre.data, dict) and "text" in res_pre.data:
                try:
                    pre_data = json.loads(res_pre.data["text"]).get("data")
                except Exception:  # noqa: BLE001, S110
                    pass
            if pre_data is None:
                raise ValueError(f"사전 호출 응답에 data(행 ID)가 없습니다: {res_pre.data}")
            ref_id = pre_data
            output_lines.append(f"사전 생성 성공: ref={ref_id}")

    if not ref_id:
        raise ValueError("오류: --ref 또는 --pre 중 하나를 지정해야 합니다.")

    # 복수 ref_id 처리 (061 #9)
    ids: list[int] = []
    if isinstance(ref_id, (list, tuple)):
        ids = [int(x) for x in ref_id]
    elif isinstance(ref_id, str) and "," in ref_id:
        ids = [int(x.strip()) for x in ref_id.split(",") if x.strip()]
    else:
        ids = [int(ref_id)]
    primary_ref = ids[0]

    # 연결 경로 확인
    link_info = DEFAULT_LINK_APIS.get(link_code, {})
    l_path = link_path or link_info.get("path")
    l_style = link_style or link_info.get("style", "query")

    if not l_path:
        cands = find_link_path_candidates(link_code)
        cand_msg = f" (후보: {', '.join(cands[:5])})" if cands else ""
        raise ValueError(f"⚠ 링크코드 {link_code}의 연결 API를 모릅니다 — --link-path로 주세요{cand_msg}")

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
    seed_params: dict[str, str] = {
        "classTreeId": str(class_tree_id),
        "linkCode": link_code,
        "refId": str(primary_ref),
    }
    if len(ids) > 1 or l_style == "ids-body":
        seed_params["ids"] = ",".join(str(i) for i in ids)
    if seed_args:
        for sa in seed_args:
            if "=" in sa:
                sak, sav = sa.split("=", 1)
                seed_params[sak.strip()] = sav.strip()

    res_seed = api_client.request_api(
        "GET",
        "/api/v1/apr/apprs/link-seed",
        params=seed_params,
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
    if not isinstance(seed_data, dict):
        seed_data = {}

    doc_title = title or seed_data.get("title") or f"{link_code} 신청서"
    doc_content = content or seed_data.get("content") or "<p>(본문 없음)</p>"
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
        try:
            _, _, apr_info = api_client.resolve_user_credentials(apr_u, company_code=company, password=password)
        except Exception as e:
            raise ValueError(f"결재자({apr_u}) 로그인 실패: {e}") from e
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
        "title": doc_title,
        "content": doc_content,
        "effectDate": effect_date,
        "regDate": reg_date,
        "signCompany": sign_company,
        "confirmed": True,
        "steps": steps,
    }

    target_path = ""
    link_body_desc = ""
    if l_path:
        target_path = l_path.replace("{ref}", str(primary_ref)).replace("{id}", str(primary_ref))
        if link_body:
            rendered_lb = link_body.replace("{ref}", str(primary_ref)).replace("{id}", str(primary_ref)).replace("{apprId}", str(appr_id))
            link_body_desc = f"{target_path} (본문: {rendered_lb})"
        elif l_style == "ids-body":
            link_body_desc = f"{target_path} (본문: {json.dumps({'ids': ids, 'apprId': appr_id})})"
        elif l_style == "body":
            link_body_desc = f"{target_path} (본문: {json.dumps({'apprId': appr_id})})"
        else:
            link_body_desc = f"{target_path}?apprId={appr_id}"
    else:
        candidates = find_link_path_candidates(link_code)
        cand_str = ", ".join(f"PUT {c}" for c in candidates) if candidates else "알 수 없음"
        link_body_desc = f"(연결 경로 미정 — 후보: {cand_str})"

    if dry_run:
        output_lines.append(f"드라이런 페이로드 (PUT /api/v1/apr/apprs/{appr_id}):\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        if l_path:
            output_lines.append(f"연결 PUT {link_body_desc}")
        else:
            cands = find_link_path_candidates(link_code)
            cand_msg = f" — 후보: {', '.join(f'PUT {c}' for c in cands)}" if cands else ""
            output_lines.append(f"상신은 했으나 업무 행 연결 없음{cand_msg} (--link-path로 지정)")
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

    output_lines.append(f"상신 apprId={appr_id} 「{doc_title}」 상태 10")

    # 7. 업무 행에 결재 ID 연결
    if not l_path:
        cands = find_link_path_candidates(link_code)
        cand_msg = f" — 후보: {', '.join(f'PUT {c}' for c in cands)}" if cands else ""
        output_lines.append(f"상신은 했으나 업무 행 연결 없음{cand_msg} (--link-path로 지정)")
    elif link_body:
        rendered_lb = link_body.replace("{ref}", str(primary_ref)).replace("{id}", str(primary_ref)).replace("{apprId}", str(appr_id))
        try:
            lb_json = json.loads(rendered_lb)
            res_link = api_client.request_api(
                "PUT",
                target_path,
                as_role=as_user,
                company_code=company,
                password=password,
                json_body=lb_json,
            )
        except Exception:  # noqa: BLE001
            res_link = api_client.request_api(
                "PUT",
                target_path,
                as_role=as_user,
                company_code=company,
                password=password,
                data=rendered_lb,
            )
        if not res_link.ok:
            output_lines.append(f"⚠ 업무 행 연결 실패 (PUT {target_path}): {res_link.error}")
        else:
            output_lines.append(f"연결 PUT {target_path} → 200")
    elif l_style == "ids-body":
        res_link = api_client.request_api(
            "PUT",
            target_path,
            as_role=as_user,
            company_code=company,
            password=password,
            json_body={"ids": ids, "apprId": appr_id},
        )
        if not res_link.ok:
            output_lines.append(f"⚠ 업무 행 연결 실패 (PUT {target_path}): {res_link.error}")
        else:
            output_lines.append(f"연결 PUT {target_path} → 200")
    elif l_style == "body":
        res_link = api_client.request_api(
            "PUT",
            target_path,
            as_role=as_user,
            company_code=company,
            password=password,
            json_body={"apprId": appr_id},
        )
        if not res_link.ok:
            output_lines.append(f"⚠ 업무 행 연결 실패 (PUT {target_path}): {res_link.error}")
        else:
            output_lines.append(f"연결 PUT {target_path} → 200")
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

    # 8. 결재자 승인 또는 반려
    if confirm or reject:
        for i, apr_u in enumerate(approvers):
            is_last = (i == len(approvers) - 1)
            if reject and is_last:
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
