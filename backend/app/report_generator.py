import json
from openai import OpenAI
from .config import settings

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


def generate_report(messages: list[dict], start_date: str | None, end_date: str | None) -> str:
    if not messages:
        return "# 업무보고서\n\n선택한 기간에 분석할 대화가 없습니다."

    if not settings.openai_api_key:
        return _fallback_report(messages, start_date, end_date)

    client = OpenAI(api_key=settings.openai_api_key)
    compact = messages[-1200:]
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": REPORT_PROMPT.format(chat_json=json.dumps(compact, ensure_ascii=False))},
        ],
    )
    return response.choices[0].message.content or "보고서 생성 결과가 비어 있습니다."


def _fallback_report(messages: list[dict], start_date: str | None, end_date: str | None) -> str:
    period = f"{start_date or messages[0]['date']} ~ {end_date or messages[-1]['date']}"
    by_user: dict[str, int] = {}
    keywords = ["완료", "확인", "점검", "수리", "민원", "누수", "청소", "교체", "조치", "보고"]
    candidates = []
    for msg in messages:
        by_user[msg["user"]] = by_user.get(msg["user"], 0) + 1
        if any(k in msg["message"] for k in keywords):
            candidates.append(msg)
    lines = [
        "# 업무보고서",
        f"- 기간: {period}",
        f"- 대화 건수: {len(messages)}건",
        "",
        "## 1. 핵심 요약",
        f"- 업무 관련 후보 대화 {len(candidates)}건이 확인되었습니다.",
        "- OPENAI_API_KEY가 설정되지 않아 규칙 기반 요약으로 생성되었습니다.",
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
    return "\n".join(lines)
