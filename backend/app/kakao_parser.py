import re
from datetime import datetime, date
from typing import Iterable
from dateutil import parser as date_parser

DATE_VALUE = r"(?:\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.?|\d{4}년\s?\d{1,2}월\s?\d{1,2}일|\d{4}-\d{1,2}-\d{1,2})"
ANDROID_PATTERN = re.compile(rf"^(?P<date>{DATE_VALUE})\s(?P<time>오전|오후)?\s?(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}}),?\s(?P<user>[^:]+)\s?:\s(?P<message>.*)$")
IOS_FULL_PATTERN = re.compile(rf"^\[(?P<user>[^\]]+)\]\s\[(?P<date>{DATE_VALUE})\s(?P<ampm>오전|오후)\s(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}})\]\s(?P<message>.*)$")
IOS_PATTERN = re.compile(r"^\[(?P<user>[^\]]+)\]\s\[(?P<ampm>오전|오후)\s(?P<hour>\d{1,2}):(?P<minute>\d{2})\]\s(?P<message>.*)$")
DATE_HEADER_PATTERN = re.compile(rf"^-+\s*(?P<date>{DATE_VALUE})\s*.*-+$")
PLAIN_DATE_HEADER_PATTERN = re.compile(rf"^(?P<date>{DATE_VALUE})(?:\s+[월화수목금토일]요일)?$")
TIME_USER_PATTERN = re.compile(r"^(?P<ampm>오전|오후)?\s?(?P<hour>\d{1,2}):(?P<minute>\d{2}),?\s(?P<user>[^:]+)\s?:\s(?P<message>.*)$")
BRACKET_TIME_USER_PATTERN = re.compile(r"^\[(?P<ampm>오전|오후)\s(?P<hour>\d{1,2}):(?P<minute>\d{2})\]\s(?P<user>[^:]+)\s?:\s(?P<message>.*)$")


def _to_24h(hour: int, ampm: str | None) -> int:
    if ampm == "오후" and hour != 12:
        return hour + 12
    if ampm == "오전" and hour == 12:
        return 0
    return hour


def _parse_korean_date(value: str) -> date:
    cleaned = value.replace("년", ".").replace("월", ".").replace("일", ".").replace("-", ".")
    cleaned = re.sub(r"\s+", "", cleaned)
    return date_parser.parse(cleaned, yearfirst=True).date()


def _message_row(msg_date: date, hour: int, minute: int, user: str, message: str) -> dict:
    dt = datetime(msg_date.year, msg_date.month, msg_date.day, hour, minute)
    return {
        "datetime": dt.isoformat(timespec="minutes"),
        "date": msg_date.isoformat(),
        "time": f"{hour:02d}:{minute:02d}",
        "user": user.strip(),
        "message": message.strip(),
    }


def parse_kakao_chat(text: str) -> list[dict]:
    """Parse exported KakaoTalk text into normalized message rows.

    Supports common Android lines like:
    2026. 4. 1. 오전 9:12, 홍길동 : 내용

Supports common iOS lines after date headers like:
    --------------- 2026년 4월 1일 수요일 ---------------
    [홍길동] [오전 9:12] 내용

    Also supports exported lines where every iOS row includes the date:
    [홍길동] [2026. 4. 1. 오전 9:12] 내용
    """
    messages: list[dict] = []
    current_date: date | None = None
    last_message: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff ")
        if not line:
            continue

        header = DATE_HEADER_PATTERN.match(line) or PLAIN_DATE_HEADER_PATTERN.match(line)
        if header:
            current_date = _parse_korean_date(header.group("date"))
            last_message = None
            continue

        android = ANDROID_PATTERN.match(line)
        if android:
            msg_date = _parse_korean_date(android.group("date"))
            hour = _to_24h(int(android.group("hour")), android.group("time"))
            minute = int(android.group("minute"))
            last_message = _message_row(msg_date, hour, minute, android.group("user"), android.group("message"))
            messages.append(last_message)
            continue

        ios_full = IOS_FULL_PATTERN.match(line)
        if ios_full:
            msg_date = _parse_korean_date(ios_full.group("date"))
            hour = _to_24h(int(ios_full.group("hour")), ios_full.group("ampm"))
            minute = int(ios_full.group("minute"))
            last_message = _message_row(msg_date, hour, minute, ios_full.group("user"), ios_full.group("message"))
            messages.append(last_message)
            continue

        ios = IOS_PATTERN.match(line)
        if ios and current_date:
            hour = _to_24h(int(ios.group("hour")), ios.group("ampm"))
            minute = int(ios.group("minute"))
            last_message = _message_row(current_date, hour, minute, ios.group("user"), ios.group("message"))
            messages.append(last_message)
            continue

        time_user = TIME_USER_PATTERN.match(line)
        if time_user and current_date:
            hour = _to_24h(int(time_user.group("hour")), time_user.group("ampm"))
            minute = int(time_user.group("minute"))
            last_message = _message_row(current_date, hour, minute, time_user.group("user"), time_user.group("message"))
            messages.append(last_message)
            continue

        bracket_time_user = BRACKET_TIME_USER_PATTERN.match(line)
        if bracket_time_user and current_date:
            hour = _to_24h(int(bracket_time_user.group("hour")), bracket_time_user.group("ampm"))
            minute = int(bracket_time_user.group("minute"))
            last_message = _message_row(current_date, hour, minute, bracket_time_user.group("user"), bracket_time_user.group("message"))
            messages.append(last_message)
            continue

        if last_message:
            last_message["message"] += "\n" + line

    return messages


def parse_diagnostics(text: str) -> dict:
    lines = [line.strip("\ufeff ") for line in text.splitlines() if line.strip("\ufeff ")]
    preview = []
    for line in lines[:12]:
        preview.append(_mask_preview_line(line))
    return {
        "non_empty_lines": len(lines),
        "preview_lines": preview,
        "recognized_formats": [
            "2026. 4. 25. 오후 2:28, 이름 : 내용",
            "2026년 4월 25일 오후 2:28, 이름 : 내용",
            "--------------- 2026년 4월 25일 토요일 ---------------",
            "[이름] [오후 2:28] 내용",
            "오후 2:28, 이름 : 내용",
        ],
    }


def _mask_preview_line(line: str) -> str:
    masked = re.sub(r"\d{2,3}-\d{3,4}-\d{4}", "***-****-****", line)
    masked = re.sub(r"\d{2,3}[가-힣]\d{4}", "***차****", masked)
    return masked[:160]


def filter_by_date(messages: Iterable[dict], start_date: str | None, end_date: str | None) -> list[dict]:
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    filtered = []
    for msg in messages:
        msg_date = date.fromisoformat(msg["date"])
        if start and msg_date < start:
            continue
        if end and msg_date > end:
            continue
        filtered.append(msg)
    return filtered
