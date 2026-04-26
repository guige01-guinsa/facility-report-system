from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from openai import OpenAI

from .config import resolve_openai_model, settings

WORK_KEYWORDS = [
    "완료",
    "조치",
    "수리",
    "교체",
    "점검",
    "확인",
    "민원",
    "누수",
    "청소",
    "보수",
    "작업",
    "처리",
    "고장",
    "파손",
    "불량",
    "복구",
    "설치",
    "철거",
    "방문",
    "출동",
    "견적",
    "배관",
    "전기",
    "소방",
    "승강기",
    "차단기",
    "주차장",
    "CCTV",
]

LOCATION_PATTERNS = [
    re.compile(r"\d{1,4}\s?동"),
    re.compile(r"\d{1,4}\s?호"),
    re.compile(r"지하\s?\d?층"),
    re.compile(r"\d{2,3}[가-힣]\d{4}"),
]

TRIVIAL_PATTERN = re.compile(
    r"^(네|넵|예|아니요|아뇨|확인|확인했습니다|알겠습니다|감사합니다|수고하세요|수고하셨습니다|ok|OK|오케이|네네)[\s.!~]*$"
)
PHOTO_NOTICE_PATTERN = re.compile(r"(사진|동영상|이미지)\s?(\d+장)?(을|를)?\s?(보냈습니다|전송했습니다|올렸습니다)?$")
SYSTEM_NOTICE_TOKENS = ["님이 들어왔습니다", "님이 나갔습니다", "님을 내보냈습니다", "메시지를 삭제", "삭제된 메시지"]
AI_CLASSIFICATION_TIMEOUT_SECONDS = 16
AI_CLASSIFICATION_MAX_MESSAGES = 240
AI_CLASSIFICATION_MAX_CHARS = 220

FILENAME_TIME_PATTERNS = [
    re.compile(
        r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})[_\-. ]?(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})"
    ),
    re.compile(
        r"(?P<year>20\d{2})[-_.](?P<month>\d{1,2})[-_.](?P<day>\d{1,2})[_\-. ](?P<hour>\d{1,2})[-_.:](?P<minute>\d{2})(?:[-_.:](?P<second>\d{2}))?"
    ),
]


def decode_uploaded_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def build_review_session(
    messages: list[dict],
    images: list[dict],
    image_metadata: str | None = None,
    *,
    use_ai: bool = False,
    ai_model: str | None = None,
) -> dict:
    metadata_rows = _load_image_metadata(image_metadata)
    reviewed_messages = [_review_message(index, msg) for index, msg in enumerate(messages)]
    ai_used = False
    ai_error = ""
    selected_ai_model = resolve_openai_model(ai_model)
    if use_ai and settings.openai_api_key and reviewed_messages:
        try:
            ai_used = _refine_messages_with_ai(reviewed_messages, selected_ai_model)
        except Exception as exc:  # pragma: no cover - network/provider failure falls back to rules.
            ai_error = str(exc)[:160]

    reviewed_images = [_review_image(index, image, metadata_rows) for index, image in enumerate(images)]
    matches = _match_images_to_messages(reviewed_images, reviewed_messages)

    return {
        "messages": reviewed_messages,
        "images": reviewed_images,
        "matches": matches,
        "summary": _summarize(reviewed_messages, reviewed_images, matches, ai_used, ai_error, selected_ai_model),
    }


def build_image_review_session(
    reviewed_messages: list[dict],
    images: list[dict],
    image_metadata: str | None = None,
) -> dict:
    metadata_rows = _load_image_metadata(image_metadata)
    reviewed_images = [_review_image(index, image, metadata_rows) for index, image in enumerate(images)]
    matches = _match_images_to_messages(reviewed_images, reviewed_messages)
    return {
        "images": reviewed_images,
        "matches": matches,
        "summary": _summarize(reviewed_messages, reviewed_images, matches, False, "", ""),
    }


def _load_image_metadata(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _review_message(index: int, msg: dict) -> dict:
    text = str(msg.get("message") or "").strip()
    compact = re.sub(r"\s+", " ", text)
    matched_keywords = [keyword for keyword in WORK_KEYWORDS if keyword.lower() in compact.lower()]
    location_hits = [pattern.pattern for pattern in LOCATION_PATTERNS if pattern.search(compact)]

    reasons: list[str] = []
    score = 0.1
    status = "review"

    if any(token in compact for token in SYSTEM_NOTICE_TOKENS):
        status = "excluded"
        score = 0.96
        reasons.append("카카오톡 시스템 알림")
    elif TRIVIAL_PATTERN.match(compact):
        status = "excluded"
        score = 0.94
        reasons.append("짧은 확인/인사 대화")
    elif PHOTO_NOTICE_PATTERN.match(compact) and not matched_keywords:
        status = "excluded"
        score = 0.88
        reasons.append("사진 전송 알림으로 보고서 본문에서는 제외")
    else:
        if matched_keywords:
            score += min(0.46, 0.12 * len(matched_keywords))
            reasons.append("업무 키워드 포함: " + ", ".join(matched_keywords[:4]))
        if location_hits:
            score += 0.14
            reasons.append("동/호수/장소 또는 차량번호 형식 포함")
        if len(compact) >= 14:
            score += 0.1
        if any(token in compact for token in ("완료", "조치", "처리", "수리", "교체")):
            score += 0.13
            reasons.append("완료/조치 표현 포함")
        if any(token in compact for token in ("요청", "부탁", "해주세요", "확인요", "확인 바랍니다")):
            score += 0.08
            reasons.append("요청/확인 표현 포함")

        if score >= 0.58:
            status = "work"
        elif score < 0.24 and len(compact) <= 8:
            status = "excluded"
            reasons.append("업무 단서가 부족한 짧은 대화")

    if not reasons:
        reasons.append("업무 여부 확인 필요")

    return {
        "id": f"m{index + 1}",
        "datetime": msg.get("datetime"),
        "date": msg.get("date"),
        "time": msg.get("time"),
        "user": msg.get("user"),
        "message": text,
        "summary": compact[:90],
        "status": status,
        "confidence": round(min(score, 0.99), 2),
        "keywords": matched_keywords,
        "reasons": reasons,
    }


def _refine_messages_with_ai(messages: list[dict], ai_model: str) -> bool:
    candidates = [
        msg
        for msg in messages
        if not (msg.get("status") == "excluded" and float(msg.get("confidence") or 0) >= 0.8)
    ][:AI_CLASSIFICATION_MAX_MESSAGES]
    if not candidates:
        return False

    compact = [
        {
            "id": msg["id"],
            "date": msg.get("date"),
            "time": msg.get("time"),
            "user": msg.get("user"),
            "message": str(msg.get("message") or "")[:AI_CLASSIFICATION_MAX_CHARS],
            "rule_status": msg.get("status"),
        }
        for msg in candidates
    ]
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=AI_CLASSIFICATION_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=ai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "시설관리 업무보고서용 카카오톡 대화를 분류합니다. "
                    "status는 work, review, excluded 중 하나만 사용하세요. "
                    "사담, 인사, 단순 확인, 사진 전송 알림은 excluded입니다. "
                    "업무 사실, 위치, 조치, 요청, 완료 내용은 work입니다."
                ),
            },
            {
                "role": "user",
                "content": (
                    "다음 JSON 배열을 분류해 JSON 객체로만 답하세요. "
                    "형식: {\"items\":[{\"id\":\"m1\",\"status\":\"work\",\"confidence\":0.82,\"reason\":\"...\"}]}\n"
                    + json.dumps(compact, ensure_ascii=False)
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    rows = parsed.get("items", [])
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    changed = False
    for msg in candidates:
        row = by_id.get(msg["id"])
        if not row:
            continue
        status = row.get("status")
        if status not in {"work", "review", "excluded"}:
            continue
        msg["status"] = status
        if isinstance(row.get("confidence"), int | float):
            msg["confidence"] = round(max(0.0, min(0.99, float(row["confidence"]))), 2)
        reason = str(row.get("reason") or "").strip()
        if reason:
            msg["reasons"] = [f"AI 분류: {reason}"] + msg["reasons"][:2]
        changed = True
    return changed


def _review_image(index: int, image: dict, metadata_rows: list[dict]) -> dict:
    metadata = metadata_rows[index] if index < len(metadata_rows) else {}
    filename = str(image.get("filename") or metadata.get("filename") or f"image_{index + 1}")
    captured_at, source = _extract_image_time(filename, metadata)
    return {
        "id": f"i{index + 1}",
        "filename": filename,
        "content_type": image.get("content_type") or metadata.get("type") or "",
        "size": int(image.get("size") or metadata.get("size") or 0),
        "captured_at": captured_at.isoformat(timespec="minutes") if captured_at else None,
        "captured_at_source": source,
        "excluded": False,
    }


def _extract_image_time(filename: str, metadata: dict) -> tuple[datetime | None, str | None]:
    for pattern in FILENAME_TIME_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        try:
            groups = match.groupdict(default="0")
            return (
                datetime(
                    int(groups["year"]),
                    int(groups["month"]),
                    int(groups["day"]),
                    int(groups["hour"]),
                    int(groups["minute"]),
                    int(groups.get("second") or 0),
                ),
                "filename",
            )
        except ValueError:
            pass

    for key in ("lastModifiedIso", "last_modified_iso", "lastModified", "last_modified"):
        value = metadata.get(key)
        parsed = _parse_datetime_value(value)
        if parsed:
            return parsed, "browser_file_modified"
    return None, None


def _parse_datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value) / 1000).replace(tzinfo=None)
        except (ValueError, OSError):
            return None
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    return None


def _match_images_to_messages(images: list[dict], messages: list[dict]) -> list[dict]:
    candidates = [msg for msg in messages if msg.get("status") in {"work", "review"}]
    if not candidates:
        return [
            _unmatched_image_match(image, ["매칭할 작업 후보 대화가 없습니다."])
            for image in images
        ]

    matches: list[dict] = []
    for image in images:
        captured_at = _parse_datetime_value(image.get("captured_at"))
        if not captured_at:
            matches.append(_unmatched_image_match(image, ["사진 촬영/저장 시간을 확인할 수 없습니다."]))
            continue

        scored = []
        for msg in candidates:
            msg_dt = _parse_datetime_value(msg.get("datetime"))
            if not msg_dt:
                continue
            score, reasons = _score_image_message(captured_at, image, msg_dt, msg)
            if score > 0:
                scored.append((score, msg, reasons))

        if not scored:
            matches.append(_unmatched_image_match(image, ["같은 날짜의 작업 후보 대화가 없습니다."]))
            continue

        scored.sort(key=lambda row: row[0], reverse=True)
        score, msg, reasons = scored[0]
        confidence = min(99, max(1, round(score)))
        if confidence >= 75:
            status = "confirmed"
        elif confidence >= 45:
            status = "needs_review"
        else:
            status = "unmatched"
            msg = None
            reasons = ["시간 차이가 커서 자동 연결하지 않았습니다."] + reasons[:1]

        matches.append(
            {
                "image_id": image["id"],
                "message_id": msg["id"] if msg else None,
                "confidence": confidence,
                "status": status,
                "role": _infer_image_role(msg) if msg else "evidence",
                "reasons": reasons[:4],
            }
        )
    return matches


def _score_image_message(captured_at: datetime, image: dict, msg_dt: datetime, msg: dict) -> tuple[float, list[str]]:
    diff_minutes = (captured_at - msg_dt).total_seconds() / 60
    abs_minutes = abs(diff_minutes)
    same_date = captured_at.date() == msg_dt.date()
    if not same_date:
        return 0, []

    if abs_minutes <= 5:
        time_score = 58
    elif abs_minutes <= 15:
        time_score = 50
    elif abs_minutes <= 30:
        time_score = 42
    elif abs_minutes <= 90:
        time_score = 28
    elif abs_minutes <= 180:
        time_score = 17
    else:
        time_score = 7

    if image.get("captured_at_source") == "browser_file_modified":
        time_score *= 0.72

    if -20 <= diff_minutes <= 120:
        time_score += 8

    message_score = float(msg.get("confidence") or 0.0) * 28
    if msg.get("status") == "work":
        message_score += 8
    if msg.get("keywords"):
        message_score += min(8, len(msg["keywords"]) * 2)

    total = min(99, time_score + message_score)
    direction = "후" if diff_minutes >= 0 else "전"
    reasons = [
        f"사진 시간이 대화 {direction} {round(abs_minutes)}분",
        "대화가 작업 후보" if msg.get("status") == "work" else "대화가 확인 필요 후보",
    ]
    if image.get("captured_at_source") == "browser_file_modified":
        reasons.append("파일 저장시간 기준이라 확인 필요")
    return total, reasons


def _infer_image_role(msg: dict | None) -> str:
    if not msg:
        return "evidence"
    text = str(msg.get("message") or "")
    if any(token in text for token in ("완료", "조치", "처리", "수리", "교체", "복구")):
        return "after"
    if "작업 전" in text or "전 사진" in text:
        return "before"
    if "작업 중" in text:
        return "during"
    return "evidence"


def _unmatched_image_match(image: dict, reasons: list[str]) -> dict:
    return {
        "image_id": image["id"],
        "message_id": None,
        "confidence": 0,
        "status": "unmatched",
        "role": "evidence",
        "reasons": reasons,
    }


def _summarize(messages: list[dict], images: list[dict], matches: list[dict], ai_used: bool, ai_error: str, ai_model: str) -> dict:
    return {
        "total_messages": len(messages),
        "work_messages": sum(1 for msg in messages if msg.get("status") == "work"),
        "review_messages": sum(1 for msg in messages if msg.get("status") == "review"),
        "excluded_messages": sum(1 for msg in messages if msg.get("status") == "excluded"),
        "total_images": len(images),
        "confirmed_matches": sum(1 for match in matches if match.get("status") == "confirmed"),
        "needs_review_matches": sum(1 for match in matches if match.get("status") == "needs_review"),
        "unmatched_images": sum(1 for match in matches if match.get("status") == "unmatched"),
        "ai_used": ai_used,
        "ai_error": ai_error,
        "ai_model": ai_model if ai_used else "",
    }
