import re
from datetime import datetime, date
from typing import Iterable
from dateutil import parser as date_parser

ANDROID_PATTERN = re.compile(r"^(?P<date>\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.)\s(?P<time>오전|오후)?\s?(?P<hour>\d{1,2}):(?P<minute>\d{2}),?\s(?P<user>[^:]+)\s?:\s(?P<message>.*)$")
IOS_PATTERN = re.compile(r"^\[(?P<user>[^\]]+)\]\s\[(?P<ampm>오전|오후)\s(?P<hour>\d{1,2}):(?P<minute>\d{2})\]\s(?P<message>.*)$")
DATE_HEADER_PATTERN = re.compile(r"^-+\s*(?P<date>\d{4}년\s\d{1,2}월\s\d{1,2}일|\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.)\s*.*-+$")


def _to_24h(hour: int, ampm: str | None) -> int:
    if ampm == "오후" and hour != 12:
        return hour + 12
    if ampm == "오전" and hour == 12:
        return 0
    return hour


def _parse_korean_date(value: str) -> date:
    cleaned = value.replace("년", ".").replace("월", ".").replace("일", ".")
    cleaned = re.sub(r"\s+", "", cleaned)
    return date_parser.parse(cleaned, yearfirst=True).date()


def parse_kakao_chat(text: str) -> list[dict]:
    """Parse exported KakaoTalk text into normalized message rows.

    Supports common Android lines like:
    2026. 4. 1. 오전 9:12, 홍길동 : 내용

    Supports common iOS lines after date headers like:
    --------------- 2026년 4월 1일 수요일 ---------------
    [홍길동] [오전 9:12] 내용
    """
    messages: list[dict] = []
    current_date: date | None = None
    last_message: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff ")
        if not line:
            continue

        header = DATE_HEADER_PATTERN.match(line)
        if header:
            current_date = _parse_korean_date(header.group("date"))
            last_message = None
            continue

        android = ANDROID_PATTERN.match(line)
        if android:
            msg_date = _parse_korean_date(android.group("date"))
            hour = _to_24h(int(android.group("hour")), android.group("time"))
            minute = int(android.group("minute"))
            dt = datetime(msg_date.year, msg_date.month, msg_date.day, hour, minute)
            last_message = {
                "datetime": dt.isoformat(timespec="minutes"),
                "date": msg_date.isoformat(),
                "time": f"{hour:02d}:{minute:02d}",
                "user": android.group("user").strip(),
                "message": android.group("message").strip(),
            }
            messages.append(last_message)
            continue

        ios = IOS_PATTERN.match(line)
        if ios and current_date:
            hour = _to_24h(int(ios.group("hour")), ios.group("ampm"))
            minute = int(ios.group("minute"))
            dt = datetime(current_date.year, current_date.month, current_date.day, hour, minute)
            last_message = {
                "datetime": dt.isoformat(timespec="minutes"),
                "date": current_date.isoformat(),
                "time": f"{hour:02d}:{minute:02d}",
                "user": ios.group("user").strip(),
                "message": ios.group("message").strip(),
            }
            messages.append(last_message)
            continue

        if last_message:
            last_message["message"] += "\n" + line

    return messages


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
