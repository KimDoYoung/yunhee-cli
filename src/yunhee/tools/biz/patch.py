"""조회 후 수정 저장 도구 (`biz-patch`).

API에서 기존 객체/목록을 GET으로 가져와 지정된 필드만 원래 타입에 맞게 안전하게 수정하고,
읽기 전용 필드 제거 후 PUT(또는 POST)으로 저장한다.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from yunhee.tools import api_client


def _coerce_value(old_val: Any, new_val_str: str) -> Any:
    """원래 값의 데이터 타입을 존중하여 새 문자열 값을 변환한다."""
    if isinstance(old_val, bool):
        return new_val_str.lower() in ("true", "1", "yes", "y")
    if isinstance(old_val, int):
        try:
            return int(new_val_str)
        except ValueError:
            return new_val_str
    if isinstance(old_val, float):
        try:
            return float(new_val_str)
        except ValueError:
            return new_val_str
    if isinstance(old_val, str):
        if old_val.lower() == "true" or old_val.lower() == "false":
            if new_val_str.lower() in ("true", "1", "yes", "y"):
                return "true"
            if new_val_str.lower() in ("false", "0", "no", "n"):
                return "false"
        return new_val_str

    # 원래 값이 None인 경우 추론
    if new_val_str.lower() == "true":
        return True
    if new_val_str.lower() == "false":
        return False
    try:
        return int(new_val_str)
    except ValueError:
        pass
    try:
        return float(new_val_str)
    except ValueError:
        pass
    return new_val_str


def _matches_where(row: dict[str, Any], where_conds: list[str]) -> bool:
    for cond in where_conds:
        if "=" not in cond:
            continue
        wk, wv = cond.split("=", 1)
        wk, wv = wk.strip(), wv.strip()
        val = row.get(wk)
        if str(val) != wv:
            return False
    return True


def run_patch(
    path: str,
    sets: list[str],
    where: list[str] | None = None,
    is_list: bool = False,
    put_path: str | None = None,
    drop_suffixes: list[str] | None = None,
    keep_keys: list[str] | None = None,
    method: str = "PUT",
    as_user: str = "admin",
    company: str = "kalpa",
    password: str | None = None,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """GET으로 데이터를 조회하여 일부 필드를 수정하고 저장한다."""
    output_lines: list[str] = []
    warnings: list[str] = []

    drop_suffixes = drop_suffixes or ["Nm"]

    # 1. GET 데이터 조회
    kw: dict[str, Any] = {"as_role": as_user, "company_code": company}
    if password:
        kw["password"] = password

    res_get = api_client.request_api("GET", path, **kw)
    if not res_get.ok:
        raise ValueError(f"조회 실패 (GET {path}): {res_get.error}")

    data = res_get.data.get("data") if isinstance(res_get.data, dict) else None
    if data is None:
        try:
            txt_obj = json.loads(res_get.data.get("text", "{}"))
            data = txt_obj.get("data")
        except Exception:  # noqa: BLE001
            data = None

    if data is None and isinstance(res_get.data, dict):
        data = res_get.data

    # 2. 대상 객체 선택
    target_dict: dict[str, Any]
    if is_list:
        if not isinstance(data, list):
            raise ValueError(f"--list 옵션이 지정되었으나 응답 데이터가 목록이 아닙니다: {type(data)}")
        where_conds = where or []
        matched = [r for r in data if isinstance(r, dict) and _matches_where(r, where_conds)]
        if len(matched) == 0:
            raise ValueError(f"--where 조건({where_conds})에 일치하는 행이 0개입니다.")
        if len(matched) > 1:
            raise ValueError(f"--where 조건({where_conds})에 일치하는 행이 {len(matched)}개입니다. 조건을 구체화하세요.")
        target_dict = copy.deepcopy(matched[0])
    else:
        if isinstance(data, list):
            raise ValueError("응답이 목록 형태입니다. --list 및 --where 옵션을 사용하세요.")
        if not isinstance(data, dict):
            raise ValueError(f"응답 데이터가 객체 형태가 아닙니다: {type(data)}")
        target_dict = copy.deepcopy(data)

    before_dict = copy.deepcopy(target_dict)

    # 3. --set 필드 적용
    changes: list[str] = []
    for s in sets:
        if "=" not in s:
            continue
        sk, sv = s.split("=", 1)
        sk, sv = sk.strip(), sv.strip()
        old_v = target_dict.get(sk)
        new_v = _coerce_value(old_v, sv)
        if sk not in target_dict:
            warnings.append(f"기존 데이터에 없는 키 '{sk}'를 새로 추가합니다.")
        target_dict[sk] = new_v
        changes.append(f"{sk}: {old_v!r} → {new_v!r}")

    # 4. drop_suffixes 및 keep_keys 필터링
    clean_dict: dict[str, Any] = {}
    for k, v in target_dict.items():
        if keep_keys and k not in keep_keys:
            continue
        if any(k.endswith(suffix) for suffix in drop_suffixes):
            continue
        clean_dict[k] = v

    output_lines.extend(changes)

    # 5. 페이로드 준비
    final_payload: Any = [clean_dict] if is_list else clean_dict

    target_put_path = put_path or path
    if dry_run:
        output_lines.append(
            f"드라이런 페이로드 ({method} {target_put_path}):\n"
            + json.dumps(final_payload, ensure_ascii=False, indent=2)
        )
        return output_lines, warnings

    # 6. 저장 실행
    res_save = api_client.request_api(
        method,
        target_put_path,
        json_body=final_payload,
        **kw,
    )
    if not res_save.ok:
        raise ValueError(f"저장 실패 ({method} {target_put_path}): {res_save.error}")

    output_lines.append(f"저장 완료 ({method} {target_put_path})")

    # 7. 사후 비교 검증: 바꾸지 않은 칸이 지워졌는지 확인
    try:
        res_after = api_client.request_api("GET", path, **kw)
        if res_after.ok and res_after.data:
            after_data = res_after.data.get("data")
            if is_list and isinstance(after_data, list):
                after_matched = [r for r in after_data if isinstance(r, dict) and _matches_where(r, where or [])]
                after_obj = after_matched[0] if after_matched else None
            elif isinstance(after_data, dict):
                after_obj = after_data
            else:
                after_obj = None

            if isinstance(after_obj, dict):
                wiped: list[str] = []
                for k, b_val in before_dict.items():
                    # 수정한 키는 제외
                    if any(s.split("=")[0].strip() == k for s in sets):
                        continue
                    if b_val is not None and b_val != "" and after_obj.get(k) is None:
                        wiped.append(k)
                if wiped:
                    warnings.append(f"서버가 보내지 않은 칸을 지웠을 수 있습니다: {wiped}")
    except Exception:  # noqa: BLE001, S110
        pass

    return output_lines, warnings
