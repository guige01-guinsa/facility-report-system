from __future__ import annotations

import json
import os
import sqlite3
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("FACILITY_TASK_DB_PATH", str(BASE_DIR / "data" / "facility_tasks.db")))
UPLOAD_DIR = Path(os.getenv("FACILITY_TASK_UPLOAD_DIR", os.getenv("NOTICE_BOARD_UPLOAD_DIR", str(BASE_DIR / "uploads"))))
MAX_EVIDENCE_BYTES = int(os.getenv("FACILITY_TASK_MAX_EVIDENCE_MB", "20")) * 1024 * 1024
ALLOWED_EVIDENCE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".hwp", ".hwpx", ".txt"}

router = APIRouter(prefix="/api/facility-tasks", tags=["facility-tasks"])

TASK_CATEGORIES = {
    "statutory": "법정점검",
    "regular": "정기점검",
    "safety": "시설안전점검",
    "fire": "소방점검",
    "mechanical": "기계설비유지",
    "other": "기타",
}

RECURRENCE_TYPES = {
    "none": "반복 없음",
    "daily": "매일",
    "weekly": "매주",
    "monthly": "매월",
    "quarterly": "분기",
    "half_yearly": "반기",
    "yearly": "매년",
    "custom_days": "사용자 지정",
}

PRIORITIES = {
    "statutory": "법정",
    "high": "중요",
    "normal": "일반",
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


class TaskCreateRequest(BaseModel):
    title: str
    category: str = "regular"
    description: str | None = None
    assignee: str | None = None
    priority: str = "normal"
    due_date: str
    recurrence_type: str = "monthly"
    recurrence_interval_days: int | None = Field(None, ge=1, le=3650)
    reminder_days: list[int] = Field(default_factory=lambda: [30, 7, 1, 0])
    evidence_required: bool = False


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    description: str | None = None
    assignee: str | None = None
    priority: str | None = None
    due_date: str | None = None
    recurrence_type: str | None = None
    recurrence_interval_days: int | None = Field(None, ge=1, le=3650)
    reminder_days: list[int] | None = None
    evidence_required: bool | None = None
    active: bool | None = None


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def init_facility_task_db() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS facility_tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              site_code TEXT NOT NULL DEFAULT 'APT1100',
              title TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'regular',
              description TEXT,
              assignee TEXT,
              priority TEXT NOT NULL DEFAULT 'normal',
              due_date TEXT NOT NULL,
              recurrence_type TEXT NOT NULL DEFAULT 'monthly',
              recurrence_interval_days INTEGER,
              reminder_days TEXT NOT NULL DEFAULT '[30,7,1,0]',
              evidence_required INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1,
              last_completed_at TEXT,
              completion_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        columns = table_columns(con, "facility_tasks")

        def add_column(name: str, definition: str) -> None:
            if name not in columns:
                con.execute(f"ALTER TABLE facility_tasks ADD COLUMN {name} {definition}")
                columns.add(name)

        add_column("site_code", "TEXT NOT NULL DEFAULT 'APT1100'")
        add_column("description", "TEXT")
        add_column("assignee", "TEXT")
        add_column("priority", "TEXT NOT NULL DEFAULT 'normal'")
        add_column("recurrence_interval_days", "INTEGER")
        add_column("reminder_days", "TEXT NOT NULL DEFAULT '[30,7,1,0]'")
        add_column("evidence_required", "INTEGER NOT NULL DEFAULT 0")
        add_column("active", "INTEGER NOT NULL DEFAULT 1")
        add_column("last_completed_at", "TEXT")
        add_column("completion_count", "INTEGER NOT NULL DEFAULT 0")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS facility_task_completions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER NOT NULL,
              due_date TEXT NOT NULL,
              completed_at TEXT NOT NULL DEFAULT (datetime('now')),
              note TEXT,
              evidence_url TEXT,
              evidence_filename TEXT,
              evidence_content_type TEXT,
              FOREIGN KEY(task_id) REFERENCES facility_tasks(id)
            )
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_facility_tasks_active_due
            ON facility_tasks(site_code, active, due_date, category, priority)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_facility_task_completions_task
            ON facility_task_completions(task_id, completed_at)
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


def normalize_date(value: str | None, label: str) -> str:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 날짜를 다시 확인해 주세요.")
    return text


def normalize_category(value: str | None) -> str:
    category = str(value or "regular").strip()
    if category not in TASK_CATEGORIES:
        raise HTTPException(status_code=400, detail="업무 구분을 다시 확인해 주세요.")
    return category


def normalize_recurrence(value: str | None) -> str:
    recurrence = str(value or "monthly").strip()
    if recurrence not in RECURRENCE_TYPES:
        raise HTTPException(status_code=400, detail="반복주기를 다시 확인해 주세요.")
    return recurrence


def normalize_priority(value: str | None) -> str:
    priority = str(value or "normal").strip()
    if priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail="중요도를 다시 확인해 주세요.")
    return priority


def normalize_reminders(values: list[int] | None) -> list[int]:
    cleaned = sorted({max(0, min(3650, int(value))) for value in (values or [])}, reverse=True)
    return cleaned or [7, 1, 0]


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def next_due_date(current_due: str, recurrence_type: str, custom_days: int | None, completed_on: date | None = None) -> str | None:
    if recurrence_type == "none":
        return None
    base = date.fromisoformat(current_due)
    completed = completed_on or date.today()
    if recurrence_type == "daily":
        candidate = base + timedelta(days=1)
    elif recurrence_type == "weekly":
        candidate = base + timedelta(days=7)
    elif recurrence_type == "monthly":
        candidate = add_months(base, 1)
    elif recurrence_type == "quarterly":
        candidate = add_months(base, 3)
    elif recurrence_type == "half_yearly":
        candidate = add_months(base, 6)
    elif recurrence_type == "yearly":
        candidate = add_months(base, 12)
    elif recurrence_type == "custom_days":
        candidate = base + timedelta(days=custom_days or 1)
    else:
        raise HTTPException(status_code=400, detail="반복주기를 다시 확인해 주세요.")

    while candidate <= completed:
        if recurrence_type == "daily":
            candidate += timedelta(days=1)
        elif recurrence_type == "weekly":
            candidate += timedelta(days=7)
        elif recurrence_type == "monthly":
            candidate = add_months(candidate, 1)
        elif recurrence_type == "quarterly":
            candidate = add_months(candidate, 3)
        elif recurrence_type == "half_yearly":
            candidate = add_months(candidate, 6)
        elif recurrence_type == "yearly":
            candidate = add_months(candidate, 12)
        else:
            candidate += timedelta(days=custom_days or 1)
    return candidate.isoformat()


async def save_evidence(file: UploadFile | None) -> dict[str, str] | None:
    if not file or not file.filename:
        return None
    payload = await file.read()
    if not payload:
        return None
    if len(payload) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="증빙파일은 20MB 이하만 업로드할 수 있습니다.")
    suffix = Path(file.filename).suffix.lower() or ".bin"
    if suffix not in ALLOWED_EVIDENCE_SUFFIXES:
        raise HTTPException(status_code=400, detail="증빙파일 형식을 다시 확인해 주세요.")
    target_dir = UPLOAD_DIR / "facility-task-evidence"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (target_dir / stored_name).write_bytes(payload)
    return {
        "url": f"/uploads/facility-task-evidence/{stored_name}",
        "filename": Path(file.filename).name,
        "content_type": file.content_type or "application/octet-stream",
    }


def task_status(due_date: str, active: bool, today: date | None = None) -> tuple[str, int]:
    current = today or date.today()
    if not active:
        return "paused", 9999
    due = date.fromisoformat(due_date)
    delta = (due - current).days
    if delta < 0:
        return "overdue", delta
    if delta == 0:
        return "today", delta
    if delta <= 7:
        return "week", delta
    if delta <= 30:
        return "month", delta
    return "later", delta


def parse_reminders(raw: str | None) -> list[int]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [int(item) for item in data]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


def task_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["active"] = bool(data.get("active"))
    data["evidence_required"] = bool(data.get("evidence_required"))
    data["reminder_days"] = parse_reminders(data.get("reminder_days"))
    status, d_day = task_status(data["due_date"], data["active"])
    data["computed_status"] = status
    data["d_day"] = d_day
    data["category_label"] = TASK_CATEGORIES.get(data.get("category"), data.get("category") or "-")
    data["recurrence_label"] = RECURRENCE_TYPES.get(data.get("recurrence_type"), data.get("recurrence_type") or "-")
    data["priority_label"] = PRIORITIES.get(data.get("priority"), data.get("priority") or "-")
    return data


def require_task(con: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = con.execute("SELECT * FROM facility_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")
    return dict(row)


def task_values(payload: TaskCreateRequest | TaskUpdateRequest, current: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(current or {})
    fields = payload.model_fields_set if isinstance(payload, TaskUpdateRequest) else set(payload.model_fields)
    for field in fields:
        source[field] = getattr(payload, field)
    recurrence_type = normalize_recurrence(source.get("recurrence_type"))
    custom_days = source.get("recurrence_interval_days")
    if recurrence_type == "custom_days" and not custom_days:
        raise HTTPException(status_code=400, detail="사용자 지정 반복은 일수를 입력해 주세요.")
    return {
        "title": normalize_text(source.get("title"), "업무명", 120, required=True),
        "category": normalize_category(source.get("category")),
        "description": normalize_text(source.get("description"), "내용", 1000),
        "assignee": normalize_text(source.get("assignee"), "담당자", 80),
        "priority": normalize_priority(source.get("priority")),
        "due_date": normalize_date(source.get("due_date"), "예정일"),
        "recurrence_type": recurrence_type,
        "recurrence_interval_days": custom_days,
        "reminder_days": json.dumps(normalize_reminders(source.get("reminder_days")), separators=(",", ":")),
        "evidence_required": 1 if source.get("evidence_required") else 0,
        "active": 1 if source.get("active", True) else 0,
    }


@router.on_event("startup")
def startup_facility_task_db() -> None:
    init_facility_task_db()


@router.get("/meta")
def facility_task_meta():
    return {"categories": TASK_CATEGORIES, "recurrence_types": RECURRENCE_TYPES, "priorities": PRIORITIES}


@router.get("/summary")
def facility_task_summary():
    init_facility_task_db()
    with connect() as con:
        rows = con.execute("SELECT * FROM facility_tasks WHERE active = 1").fetchall()
    tasks = [task_dict(row) for row in rows]
    return {
        "total": len(tasks),
        "overdue": sum(1 for task in tasks if task["computed_status"] == "overdue"),
        "today": sum(1 for task in tasks if task["computed_status"] == "today"),
        "week": sum(1 for task in tasks if task["computed_status"] == "week"),
        "month": sum(1 for task in tasks if task["computed_status"] in {"week", "month"}),
        "statutory": sum(1 for task in tasks if task["category"] == "statutory" or task["priority"] == "statutory"),
        "evidence_required": sum(1 for task in tasks if task["evidence_required"]),
    }


@router.get("")
def list_facility_tasks(scope: str = "attention", q: str = "", limit: int = 200):
    init_facility_task_db()
    limit = min(max(limit, 1), 300)
    query = q.strip()
    where = []
    params: list[Any] = []
    if scope != "all":
        where.append("active = 1")
    if query:
        like = f"%{query}%"
        where.append("(title LIKE ? OR COALESCE(description, '') LIKE ? OR COALESCE(assignee, '') LIKE ?)")
        params.extend([like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT *
            FROM facility_tasks
            {where_sql}
            ORDER BY active DESC, due_date ASC, CASE priority WHEN 'statutory' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    tasks = [task_dict(row) for row in rows]
    if scope == "attention":
        tasks = [task for task in tasks if task["computed_status"] in {"overdue", "today", "week"}]
    elif scope == "overdue":
        tasks = [task for task in tasks if task["computed_status"] == "overdue"]
    elif scope == "today":
        tasks = [task for task in tasks if task["computed_status"] == "today"]
    elif scope == "week":
        tasks = [task for task in tasks if task["computed_status"] in {"today", "week"}]
    elif scope == "month":
        tasks = [task for task in tasks if task["computed_status"] in {"today", "week", "month"}]
    return tasks


@router.post("")
def create_facility_task(payload: TaskCreateRequest):
    init_facility_task_db()
    values = task_values(payload)
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO facility_tasks
            (title, category, description, assignee, priority, due_date, recurrence_type, recurrence_interval_days, reminder_days, evidence_required, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["title"],
                values["category"],
                values["description"],
                values["assignee"],
                values["priority"],
                values["due_date"],
                values["recurrence_type"],
                values["recurrence_interval_days"],
                values["reminder_days"],
                values["evidence_required"],
                values["active"],
            ),
        )
        row = con.execute("SELECT * FROM facility_tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
        con.commit()
    return task_dict(row)


@router.patch("/{task_id}")
def update_facility_task(task_id: int, payload: TaskUpdateRequest):
    init_facility_task_db()
    with connect() as con:
        current = require_task(con, task_id)
        values = task_values(payload, current)
        con.execute(
            """
            UPDATE facility_tasks
            SET title = ?, category = ?, description = ?, assignee = ?, priority = ?, due_date = ?,
                recurrence_type = ?, recurrence_interval_days = ?, reminder_days = ?, evidence_required = ?,
                active = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                values["title"],
                values["category"],
                values["description"],
                values["assignee"],
                values["priority"],
                values["due_date"],
                values["recurrence_type"],
                values["recurrence_interval_days"],
                values["reminder_days"],
                values["evidence_required"],
                values["active"],
                task_id,
            ),
        )
        row = con.execute("SELECT * FROM facility_tasks WHERE id = ?", (task_id,)).fetchone()
        con.commit()
    return task_dict(row)


@router.post("/{task_id}/complete")
async def complete_facility_task(
    task_id: int,
    note: str | None = Form(None),
    evidence: UploadFile | None = File(None),
):
    init_facility_task_db()
    evidence_file = await save_evidence(evidence)
    completed_on = date.today()
    with connect() as con:
        current = require_task(con, task_id)
        if current.get("evidence_required") and not evidence_file:
            raise HTTPException(status_code=400, detail="이 업무는 증빙파일이 필요합니다.")
        next_due = next_due_date(current["due_date"], current["recurrence_type"], current.get("recurrence_interval_days"), completed_on)
        con.execute(
            """
            INSERT INTO facility_task_completions(task_id, due_date, note, evidence_url, evidence_filename, evidence_content_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                current["due_date"],
                normalize_text(note, "완료 메모", 1000),
                evidence_file["url"] if evidence_file else None,
                evidence_file["filename"] if evidence_file else None,
                evidence_file["content_type"] if evidence_file else None,
            ),
        )
        con.execute(
            """
            UPDATE facility_tasks
            SET due_date = COALESCE(?, due_date), active = ?, last_completed_at = datetime('now'),
                completion_count = completion_count + 1, updated_at = datetime('now')
            WHERE id = ?
            """,
            (next_due, 1 if next_due else 0, task_id),
        )
        row = con.execute("SELECT * FROM facility_tasks WHERE id = ?", (task_id,)).fetchone()
        con.commit()
    return {"completed": True, "next_task": task_dict(row)}


@router.delete("/{task_id}")
def pause_facility_task(task_id: int):
    init_facility_task_db()
    with connect() as con:
        require_task(con, task_id)
        con.execute("UPDATE facility_tasks SET active = 0, updated_at = datetime('now') WHERE id = ?", (task_id,))
        con.commit()
    return {"deleted": True, "id": task_id}


@router.get("/{task_id}/completions")
def list_facility_task_completions(task_id: int):
    init_facility_task_db()
    with connect() as con:
        require_task(con, task_id)
        rows = con.execute(
            """
            SELECT *
            FROM facility_task_completions
            WHERE task_id = ?
            ORDER BY completed_at DESC, id DESC
            LIMIT 50
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]
