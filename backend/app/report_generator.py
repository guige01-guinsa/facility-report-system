import json
from openai import OpenAI
from .config import resolve_openai_model, settings

SYSTEM_PROMPT = """
당신은 아파트/시설관리 현장 대화를 업무보고서로 정리하는 전문 비서입니다.
대화에서 사실로 확인 가능한 내용만 추출하고, 추정이 필요한 경우 '추정'이라고 표시하세요.
개인 연락처, 민감정보, 불필요한 사담은 보고서에서 제외하세요.
""".strip()

REPORT_PROMPT = """
아래 카카오톡 대화 내역을 기간별 업무보고서로 작성하세요.

요구 형식:
# 업무보고서
- 기간:
- 대화 건수:

## 1. 핵심 요약
3~7개 bullet

## 2. 완료 업무
표 형식: 날짜 | 업무 | 담당자 | 근거 대화

## 3. 진행/미완료 업무
표 형식: 날짜 | 업무 | 담당자 | 현재 상태 | 다음 조치

## 4. 주요 이슈/위험
표 형식: 이슈 | 영향 | 권장 조치

## 5. 담당자별 업무 정리
담당자별 bullet

## 6. 보고서용 문장
관리사무소 보고서에 그대로 붙여넣기 좋은 정중한 문체로 작성

대화 JSON:
{chat_json}
""".strip()

REVIEWED_REPORT_PROMPT = """
아래는 사용자가 검토한 시설관리 업무보고서 자료입니다.
status가 excluded인 대화와 excluded가 true인 이미지는 보고서에서 제외하세요.
사진은 실제 이미지 설명이 아니라 파일명과 사용자가 확정한 역할만 근거로 다루세요.
확실한 사실과 추정을 구분하고, 불필요한 사담/개인정보는 빼세요.

요구 형식:
# 작업보고서
- 기간:
- 작업 대화:
- 첨부 사진:

## 1. 작업 요약
3~7개 bullet

## 2. 작업 내역
표 형식: 일시 | 위치/대상 | 작업 내용 | 상태 | 첨부 사진

## 3. 확인 필요 항목
신뢰도가 낮거나 사용자가 review로 둔 항목만 정리

## 4. 보고서용 문장
관리사무소 보고서에 그대로 붙여넣기 좋은 문체로 작성

검토 데이터 JSON:
{review_json}
""".strip()


def generate_report(messages: list[dict], start_date: str | None, end_date: str | None) -> str:
    if not messages:
        return "# 업무보고서\n\n선택한 기간에 분석할 대화가 없습니다."

    if not settings.openai_api_key:
        return _fallback_report(messages, start_date, end_date)

    try:
        client = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=20)
        compact = messages[-1200:]
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": REPORT_PROMPT.format(chat_json=json.dumps(compact, ensure_ascii=False))},
            ],
        )
        return response.choices[0].message.content or "보고서 생성 결과가 비어 있습니다."
    except Exception as exc:  # pragma: no cover - provider/network failures fall back to deterministic output.
        return _fallback_report(messages, start_date, end_date, _safe_ai_error(exc))


def _safe_ai_error(exc: Exception) -> str:
    text = str(exc).replace(settings.openai_api_key, "[redacted]") if settings.openai_api_key else str(exc)
    return text[:220]


def generate_reviewed_report(
    messages: list[dict],
    images: list[dict],
    matches: list[dict],
    start_date: str | None,
    end_date: str | None,
    ai_model: str | None = None,
) -> str:
    review = _compact_review(messages, images, matches, start_date, end_date)
    if not review["items"]:
        return "# 작업보고서\n\n보고서에 포함할 작업 대화가 없습니다."

    if not settings.openai_api_key:
        return _fallback_reviewed_report(review)

    try:
        client = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=20)
        response = client.chat.completions.create(
            model=resolve_openai_model(ai_model),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": REVIEWED_REPORT_PROMPT.format(review_json=json.dumps(review, ensure_ascii=False))},
            ],
        )
        return response.choices[0].message.content or "보고서 생성 결과가 비어 있습니다."
    except Exception as exc:  # pragma: no cover - provider/network failures fall back to deterministic output.
        return _fallback_reviewed_report(review, _safe_ai_error(exc))


def _fallback_report(messages: list[dict], start_date: str | None, end_date: str | None, ai_error: str = "") -> str:
    period = f"{start_date or messages[0]['date']} ~ {end_date or messages[-1]['date']}"
    by_user: dict[str, int] = {}
    keywords = ["완료", "확인", "점검", "수리", "민원", "누수", "청소", "교체", "조치", "보고"]
    candidates = []
    for msg in messages:
        by_user[msg["user"]] = by_user.get(msg["user"], 0) + 1
        if any(k in msg["message"] for k in keywords):
            candidates.append(msg)
    mode_note = "- AI 호출을 사용할 수 없어 규칙 기반 요약으로 생성되었습니다." if ai_error else "- OPENAI_API_KEY가 설정되지 않아 규칙 기반 요약으로 생성되었습니다."
    lines = [
        "# 업무보고서",
        f"- 기간: {period}",
        f"- 대화 건수: {len(messages)}건",
        "",
        "## 1. 핵심 요약",
        f"- 업무 관련 후보 대화 {len(candidates)}건이 확인되었습니다.",
        mode_note,
        "",
        "## 2. 업무 후보",
        "| 날짜 | 담당자 | 내용 |",
        "|---|---|---|",
    ]
    for msg in candidates[:50]:
        text = msg["message"].replace("\n", " ")[:120]
        lines.append(f"| {msg['date']} {msg['time']} | {msg['user']} | {text} |")
    lines += ["", "## 3. 담당자별 대화 건수"]
    for user, count in sorted(by_user.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {user}: {count}건")
    if ai_error:
        lines += ["", "## AI 생성 참고", f"- AI 호출 실패로 규칙 기반 보고서를 생성했습니다: {ai_error}"]
    return "\n".join(lines)


def _compact_review(
    messages: list[dict],
    images: list[dict],
    matches: list[dict],
    start_date: str | None,
    end_date: str | None,
) -> dict:
    image_by_id = {image.get("id"): image for image in images if not image.get("excluded")}
    matches_by_message: dict[str, list[dict]] = {}
    unmatched_images = []
    for match in matches:
        image = image_by_id.get(match.get("image_id"))
        if not image:
            continue
        row = {
            "filename": image.get("filename"),
            "captured_at": image.get("captured_at"),
            "role": match.get("role"),
            "match_status": match.get("status"),
            "confidence": match.get("confidence"),
        }
        message_id = match.get("message_id")
        if message_id:
            matches_by_message.setdefault(message_id, []).append(row)
        else:
            unmatched_images.append(row)

    items = []
    for msg in messages:
        if msg.get("status") == "excluded":
            continue
        items.append(
            {
                "datetime": msg.get("datetime"),
                "date": msg.get("date"),
                "time": msg.get("time"),
                "user": msg.get("user"),
                "message": msg.get("message"),
                "status": msg.get("status"),
                "confidence": msg.get("confidence"),
                "images": matches_by_message.get(msg.get("id"), []),
            }
        )
    return {
        "period": {
            "start_date": start_date or (items[0]["date"] if items else None),
            "end_date": end_date or (items[-1]["date"] if items else None),
        },
        "items": items,
        "unmatched_images": unmatched_images,
    }


def _fallback_reviewed_report(review: dict, ai_error: str = "") -> str:
    period = review["period"]
    items = review["items"]
    image_count = sum(len(item["images"]) for item in items)
    lines = [
        "# 작업보고서",
        f"- 기간: {period.get('start_date') or '-'} ~ {period.get('end_date') or '-'}",
        f"- 작업 대화: {len(items)}건",
        f"- 첨부 사진: {image_count}장",
        "",
        "## 1. 작업 요약",
        "- 사용자가 확정/유지한 대화와 사진 매칭을 기준으로 정리했습니다.",
        "- AI 호출을 사용할 수 없어 규칙 기반 보고서로 생성되었습니다.",
        "",
        "## 2. 작업 내역",
        "| 일시 | 담당자 | 작업 내용 | 첨부 사진 |",
        "|---|---|---|---|",
    ]
    for item in items[:80]:
        text = str(item.get("message") or "").replace("\n", " ")[:140]
        filenames = ", ".join(str(image.get("filename")) for image in item.get("images", [])[:8]) or "-"
        lines.append(f"| {item.get('date')} {item.get('time')} | {item.get('user')} | {text} | {filenames} |")

    review_items = [item for item in items if item.get("status") == "review"]
    lines += ["", "## 3. 확인 필요 항목"]
    if review_items:
        for item in review_items[:20]:
            lines.append(f"- {item.get('date')} {item.get('time')} {item.get('message')}")
    else:
        lines.append("- 별도 확인 필요 항목이 없습니다.")

    if review.get("unmatched_images"):
        lines += ["", "## 4. 미매칭 사진"]
        for image in review["unmatched_images"][:30]:
            lines.append(f"- {image.get('filename')}")
    if ai_error:
        lines += ["", "## AI 생성 참고", f"- AI 호출 실패 사유: {ai_error}"]
    return "\n".join(lines)
