from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings

OPENAI_BASE_URL = "https://api.openai.com"


def get_openai_usage_snapshot(days: int = 7) -> dict:
    key = settings.openai_admin_key.strip()
    if not key:
        return {
            "configured": False,
            "status": "not_configured",
            "message": "OPENAI_ADMIN_KEY가 설정되지 않아 앱 안에서 사용량을 조회할 수 없습니다.",
            "usage_dashboard_url": "https://platform.openai.com/usage",
            "billing_url": "https://platform.openai.com/settings/organization/billing",
            "limits_url": "https://platform.openai.com/settings/organization/limits",
        }

    now = datetime.now(timezone.utc)
    start_time = int((now - timedelta(days=days)).timestamp())
    try:
        usage = _get_json(
            key,
            "/v1/organization/usage/completions",
            {"start_time": str(start_time), "bucket_width": "1d", "limit": str(days)},
        )
        costs = _get_json(
            key,
            "/v1/organization/costs",
            {"start_time": str(start_time), "bucket_width": "1d", "limit": str(days)},
        )
    except urllib.error.HTTPError as exc:
        return _error_response(exc.code, _safe_error_body(exc))
    except urllib.error.URLError as exc:
        return {
            "configured": True,
            "status": "network_error",
            "message": f"OpenAI 사용량 조회 네트워크 오류: {exc.reason}",
        }

    return {
        "configured": True,
        "status": "ok",
        "days": days,
        "generated_at": now.isoformat(timespec="seconds"),
        "usage": _summarize_usage(usage),
        "costs": _summarize_costs(costs),
        "usage_dashboard_url": "https://platform.openai.com/usage",
        "billing_url": "https://platform.openai.com/settings/organization/billing",
        "limits_url": "https://platform.openai.com/settings/organization/limits",
    }


def _get_json(key: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{OPENAI_BASE_URL}{path}?{query}",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _summarize_usage(payload: dict) -> dict:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "requests": 0,
    }
    for result in _iter_results(payload):
        totals["input_tokens"] += int(result.get("input_tokens") or 0)
        totals["output_tokens"] += int(result.get("output_tokens") or 0)
        totals["cached_tokens"] += int(result.get("input_cached_tokens") or 0)
        totals["requests"] += int(result.get("num_model_requests") or 0)
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


def _summarize_costs(payload: dict) -> dict:
    total = 0.0
    currency = "usd"
    for result in _iter_results(payload):
        amount = result.get("amount") or {}
        total += float(amount.get("value") or 0)
        currency = str(amount.get("currency") or currency)
    return {"total": round(total, 6), "currency": currency.upper()}


def _iter_results(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for bucket in payload.get("data", []):
        if isinstance(bucket, dict):
            rows.extend(row for row in bucket.get("results", []) if isinstance(row, dict))
    return rows


def _safe_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return body[:300]


def _error_response(status_code: int, body: str) -> dict[str, Any]:
    if status_code in {401, 403}:
        message = "사용량 조회 권한이 없습니다. 조직 관리자 권한의 OPENAI_ADMIN_KEY가 필요합니다."
    elif status_code == 429:
        message = "OpenAI 사용량 조회 API도 한도에 걸렸습니다. 잠시 후 다시 시도하세요."
    else:
        message = f"OpenAI 사용량 조회 실패: HTTP {status_code}"
    return {
        "configured": True,
        "status": "error",
        "status_code": status_code,
        "message": message,
        "detail": body,
        "usage_dashboard_url": "https://platform.openai.com/usage",
        "billing_url": "https://platform.openai.com/settings/organization/billing",
        "limits_url": "https://platform.openai.com/settings/organization/limits",
    }
