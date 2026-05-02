from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("NOTICE_BOARD_DB_PATH", str(BASE_DIR / "data" / "notice_board.db")))
UPLOAD_DIR = Path(os.getenv("NOTICE_BOARD_UPLOAD_DIR", str(BASE_DIR / "uploads")))
MAX_IMAGE_BYTES = int(os.getenv("NOTICE_BOARD_MAX_IMAGE_MB", "8")) * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

router = APIRouter(prefix="/api/notices", tags=["notice-board"])

NOTICE_CATEGORIES = {
    "notice": "안내",
    "announcement": "공고문",
    "move": "전입/전출",
    "commercial": "상업게시물",
    "other": "기타",
}

NOTICE_STATUSES = {
    "draft": "임시",
    "scheduled": "게시 예정",
    "posted": "게시 중",
    "removal_due": "철거 대상",
    "expired": "기간 만료",
    "removed": "철거 완료",
    "unauthorized": "무단 게시",
}


class ClosingConnection(sqlite3.Connection):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


class NoticeUpdateRequest(BaseModel):
    category: str | None = None
    title: str | None = None
    description: str | None = None
    location: str | None = None
    board_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    removal_due_date: str | None = None
    advertiser: str | None = None
    contact: str | None = None
    status: str | None = None
    note: str | None = None


class RemovalRequest(BaseModel):
    removal_note: str | None = Field(None, max_length=500)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def init_notice_db() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS board_posts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              site_code TEXT NOT NULL DEFAULT 'APT1100',
              category TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT,
              location TEXT NOT NULL,
              board_name TEXT,
              start_date TEXT NOT NULL,
              end_date TEXT NOT NULL,
              removal_due_date TEXT,
              advertiser TEXT,
              contact TEXT,
              status TEXT NOT NULL DEFAULT 'posted',
              note TEXT,
              image_url TEXT,
              removal_image_url TEXT,
              removal_note TEXT,
              created_by TEXT,
              removed_by TEXT,
              removed_at TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_board_posts_site_status_end
            ON board_posts(site_code, status, end_date, removal_due_date)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_board_posts_site_category_location
            ON board_posts(site_code, category, location)
            """
        )
        con.commit()


def normalize_text(value: str | None, label: str, max_len: int, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise HTTPException(status_code=400, detail=f"{label}을 입력해 주세요.")
        return None
    if len(text) > max_len:
        raise HTTPException(status_code=400, detail=f"{label}은 {max_len}자 이내로 입력해 주세요.")
    return text


def normalize_category(value: str | None) -> str:
    category = str(value or "").strip().lower()
    if category not in NOTICE_CATEGORIES:
        raise HTTPException(status_code=400, detail="게시물 분류를 다시 확인해 주세요.")
    return category


def normalize_status(value: str | None, *, fallback: str = "posted") -> str:
    status = str(value or fallback).strip().lower()
    if status not in NOTICE_STATUSES:
        raise HTTPException(status_code=400, detail="게시물 상태를 다시 확인해 주세요.")
    return status


def normalize_date_value(value: str | None, label: str, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise HTTPException(status_code=400, detail=f"{label}을 입력해 주세요.")
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise HTTPException(status_code=400, detail=f"{label}은 YYYY-MM-DD 형식으로 입력해 주세요.")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 날짜를 다시 확인해 주세요.")
    return text


def validate_period(start_date: str, end_date: str, removal_due_date: str | None) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="게시 종료일은 시작일 이후여야 합니다.")
    if removal_due_date and removal_due_date < end_date:
        raise HTTPException(status_code=400, detail="철거 예정일은 게시 종료일 이후로 입력해 주세요.")


async def save_notice_image(image: UploadFile | None, folder: str) -> str | None:
    if not image or not image.filename:
        return None
    payload = await image.read()
    if not payload:
        return None
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="사진은 8MB 이하만 업로드할 수 있습니다.")
    suffix = Path(image.filename).suffix.lower() or ".jpg"
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="사진은 jpg, png, webp, gif 형식만 사용할 수 있습니다.")
    target_dir = UPLOAD_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (target_dir / filename).write_bytes(payload)
    return f"/uploads/{folder}/{filename}"


def computed_status(row: dict[str, Any], today: date | None = None) -> str:
    current = today or date.today()
    status = row.get("status") or "posted"
    if status in {"draft", "removed", "unauthorized"}:
        return status
    start = date.fromisoformat(row["start_date"])
    end = date.fromisoformat(row["end_date"])
    removal_due = date.fromisoformat(row["removal_due_date"]) if row.get("removal_due_date") else end
    if current < start:
        return "scheduled"
    if current <= end:
        return "posted"
    if current >= removal_due:
        return "removal_due"
    return "expired"


def notice_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    status = computed_status(data)
    data["computed_status"] = status
    data["status_label"] = NOTICE_STATUSES.get(status, status)
    data["category_label"] = NOTICE_CATEGORIES.get(data.get("category"), data.get("category") or "-")
    return data


def require_notice(con: sqlite3.Connection, notice_id: int) -> dict[str, Any]:
    row = con.execute("SELECT * FROM board_posts WHERE id = ?", (notice_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return dict(row)


@router.on_event("startup")
def startup_notice_db() -> None:
    init_notice_db()


@router.get("/meta")
def notice_meta():
    return {"categories": NOTICE_CATEGORIES, "statuses": NOTICE_STATUSES}


@router.get("/summary")
def notice_summary():
    init_notice_db()
    with connect() as con:
        rows = con.execute("SELECT * FROM board_posts ORDER BY id DESC").fetchall()
    notices = [notice_dict(row) for row in rows]
    return {
        "total": len(notices),
        "posted": sum(1 for row in notices if row["computed_status"] == "posted"),
        "removal_due": sum(1 for row in notices if row["computed_status"] == "removal_due"),
        "expired": sum(1 for row in notices if row["computed_status"] == "expired"),
        "scheduled": sum(1 for row in notices if row["computed_status"] == "scheduled"),
        "unauthorized": sum(1 for row in notices if row["computed_status"] == "unauthorized"),
    }


@router.get("")
def list_notices(
    q: str = "",
    category: str = "",
    status: str = "",
    location: str = "",
    limit: int = 100,
    offset: int = 0,
):
    init_notice_db()
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    where: list[str] = []
    params: list[Any] = []
    if category:
        where.append("category = ?")
        params.append(normalize_category(category))
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location.strip()}%")
    query = q.strip()
    if query:
        like = f"%{query}%"
        where.append(
            """
            (
              title LIKE ?
              OR COALESCE(description, '') LIKE ?
              OR location LIKE ?
              OR COALESCE(board_name, '') LIKE ?
              OR COALESCE(advertiser, '') LIKE ?
              OR COALESCE(contact, '') LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.extend([limit, offset])
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT *
            FROM board_posts
            {where_sql}
            ORDER BY
              CASE status WHEN 'removed' THEN 9 WHEN 'draft' THEN 8 ELSE 0 END,
              COALESCE(removal_due_date, end_date) ASC,
              id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    notices = [notice_dict(row) for row in rows]
    if status:
        normalized = normalize_status(status)
        notices = [row for row in notices if row["computed_status"] == normalized or row["status"] == normalized]
    return notices


@router.post("")
async def create_notice(
    category: str = Form(...),
    title: str = Form(...),
    description: str | None = Form(None),
    location: str = Form(...),
    board_name: str | None = Form(None),
    start_date: str = Form(...),
    end_date: str = Form(...),
    removal_due_date: str | None = Form(None),
    advertiser: str | None = Form(None),
    contact: str | None = Form(None),
    status: str | None = Form("posted"),
    note: str | None = Form(None),
    image: UploadFile | None = File(None),
):
    init_notice_db()
    normalized_category = normalize_category(category)
    normalized_title = normalize_text(title, "제목", 120, required=True)
    normalized_location = normalize_text(location, "위치", 120, required=True)
    normalized_start = normalize_date_value(start_date, "게시 시작일", required=True)
    normalized_end = normalize_date_value(end_date, "게시 종료일", required=True)
    normalized_removal_due = normalize_date_value(removal_due_date, "철거 예정일")
    validate_period(normalized_start, normalized_end, normalized_removal_due)
    image_url = await save_notice_image(image, "notices")
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO board_posts
            (category, title, description, location, board_name, start_date, end_date, removal_due_date,
             advertiser, contact, status, note, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_category,
                normalized_title,
                normalize_text(description, "내용", 1000),
                normalized_location,
                normalize_text(board_name, "게시판명", 80),
                normalized_start,
                normalized_end,
                normalized_removal_due,
                normalize_text(advertiser, "게시자", 80),
                normalize_text(contact, "연락처", 80),
                normalize_status(status),
                normalize_text(note, "메모", 500),
                image_url,
            ),
        )
        row = con.execute("SELECT * FROM board_posts WHERE id = ?", (cur.lastrowid,)).fetchone()
        con.commit()
    return notice_dict(row)


@router.patch("/{notice_id}")
def update_notice(notice_id: int, payload: NoticeUpdateRequest):
    init_notice_db()
    fields = payload.model_fields_set
    if not fields:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
    with connect() as con:
        current = require_notice(con, notice_id)
        values = dict(current)
        for field in fields:
            values[field] = getattr(payload, field)

        normalized_start = normalize_date_value(values.get("start_date"), "게시 시작일", required=True)
        normalized_end = normalize_date_value(values.get("end_date"), "게시 종료일", required=True)
        normalized_removal_due = normalize_date_value(values.get("removal_due_date"), "철거 예정일")
        validate_period(normalized_start, normalized_end, normalized_removal_due)

        updates = {
            "category": normalize_category(values.get("category")),
            "title": normalize_text(values.get("title"), "제목", 120, required=True),
            "description": normalize_text(values.get("description"), "내용", 1000),
            "location": normalize_text(values.get("location"), "위치", 120, required=True),
            "board_name": normalize_text(values.get("board_name"), "게시판명", 80),
            "start_date": normalized_start,
            "end_date": normalized_end,
            "removal_due_date": normalized_removal_due,
            "advertiser": normalize_text(values.get("advertiser"), "게시자", 80),
            "contact": normalize_text(values.get("contact"), "연락처", 80),
            "status": normalize_status(values.get("status")),
            "note": normalize_text(values.get("note"), "메모", 500),
        }
        con.execute(
            """
            UPDATE board_posts
            SET category = ?, title = ?, description = ?, location = ?, board_name = ?,
                start_date = ?, end_date = ?, removal_due_date = ?, advertiser = ?, contact = ?,
                status = ?, note = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (*updates.values(), notice_id),
        )
        row = con.execute("SELECT * FROM board_posts WHERE id = ?", (notice_id,)).fetchone()
        con.commit()
    return notice_dict(row)


@router.post("/{notice_id}/remove")
async def remove_notice(
    notice_id: int,
    removal_note: str | None = Form(None),
    removal_image: UploadFile | None = File(None),
):
    init_notice_db()
    image_url = await save_notice_image(removal_image, "notice-removals")
    with connect() as con:
        require_notice(con, notice_id)
        con.execute(
            """
            UPDATE board_posts
            SET status = 'removed', removal_note = ?, removal_image_url = COALESCE(?, removal_image_url),
                removed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (normalize_text(removal_note, "철거 메모", 500), image_url, notice_id),
        )
        row = con.execute("SELECT * FROM board_posts WHERE id = ?", (notice_id,)).fetchone()
        con.commit()
    return notice_dict(row)


@router.delete("/{notice_id}")
def delete_notice(notice_id: int):
    init_notice_db()
    with connect() as con:
        require_notice(con, notice_id)
        con.execute("DELETE FROM board_posts WHERE id = ?", (notice_id,))
        con.commit()
    return {"deleted": True, "id": notice_id}
