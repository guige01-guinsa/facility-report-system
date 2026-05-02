from __future__ import annotations

import os
import re
import sqlite3
import json
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
MAX_ATTACHMENT_BYTES = int(os.getenv("NOTICE_BOARD_MAX_ATTACHMENT_MB", "20")) * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_ATTACHMENT_SUFFIXES = ALLOWED_IMAGE_SUFFIXES | {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".hwp", ".hwpx", ".txt"}

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
    line: str | None = None
    floor: str | None = None
    specific_location: str | None = None
    board_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    removal_due_date: str | None = None
    advertiser: str | None = None
    contact: str | None = None
    status: str | None = None
    note: str | None = None


class NoticeLocationRequest(BaseModel):
    building: str
    line: str
    floor: str
    sort_order: int = Field(0, ge=0, le=9999)


class NoticeSpecificLocationRequest(BaseModel):
    name: str
    sort_order: int = Field(0, ge=0, le=9999)


class NoticeLocationGenerateRequest(BaseModel):
    buildings: str
    lines: str
    floors: str
    excluded_floors: str | None = None
    sort_order_start: int = Field(0, ge=0, le=9999)
    dry_run: bool = False


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


def table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


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
              line TEXT,
              floor TEXT,
              specific_location TEXT,
              board_name TEXT,
              start_date TEXT NOT NULL,
              end_date TEXT NOT NULL,
              removal_due_date TEXT,
              advertiser TEXT,
              contact TEXT,
              status TEXT NOT NULL DEFAULT 'posted',
              note TEXT,
              image_url TEXT,
              attachment_url TEXT,
              attachment_filename TEXT,
              attachment_content_type TEXT,
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
        columns = table_columns(con, "board_posts")

        def add_column(name: str, definition: str) -> None:
            if name not in columns:
                con.execute(f"ALTER TABLE board_posts ADD COLUMN {name} {definition}")
                columns.add(name)

        add_column("site_code", "TEXT NOT NULL DEFAULT 'APT1100'")
        add_column("line", "TEXT")
        add_column("floor", "TEXT")
        add_column("specific_location", "TEXT")
        add_column("board_name", "TEXT")
        add_column("removal_due_date", "TEXT")
        add_column("advertiser", "TEXT")
        add_column("contact", "TEXT")
        add_column("note", "TEXT")
        add_column("image_url", "TEXT")
        add_column("attachment_url", "TEXT")
        add_column("attachment_filename", "TEXT")
        add_column("attachment_content_type", "TEXT")
        add_column("removal_image_url", "TEXT")
        add_column("removal_note", "TEXT")
        add_column("created_by", "TEXT")
        add_column("removed_by", "TEXT")
        add_column("removed_at", "TEXT")
        con.execute("UPDATE board_posts SET floor = COALESCE(NULLIF(floor, ''), board_name) WHERE floor IS NULL OR floor = ''")
        con.execute("UPDATE board_posts SET attachment_url = image_url WHERE (attachment_url IS NULL OR attachment_url = '') AND image_url IS NOT NULL")
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_board_posts_site_status_end
            ON board_posts(site_code, status, end_date, removal_due_date)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_board_posts_site_category_location
            ON board_posts(site_code, category, location, line, floor, specific_location)
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS notice_location_options (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              site_code TEXT NOT NULL DEFAULT 'APT1100',
              building TEXT NOT NULL,
              line TEXT NOT NULL,
              floor TEXT NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_locations_unique
            ON notice_location_options(site_code, building, line, floor)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notice_locations_order
            ON notice_location_options(site_code, sort_order, building, line, floor)
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS notice_specific_location_options (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              site_code TEXT NOT NULL DEFAULT 'APT1100',
              name TEXT NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_specific_locations_unique
            ON notice_specific_location_options(site_code, name)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notice_specific_locations_order
            ON notice_specific_location_options(site_code, sort_order, name)
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


async def save_notice_attachment(file: UploadFile | None) -> dict[str, str] | None:
    if not file or not file.filename:
        return None
    payload = await file.read()
    if not payload:
        return None
    if len(payload) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="게시파일은 20MB 이하만 업로드할 수 있습니다.")
    suffix = Path(file.filename).suffix.lower() or ".bin"
    if suffix not in ALLOWED_ATTACHMENT_SUFFIXES:
        raise HTTPException(status_code=400, detail="게시파일은 이미지, PDF, Word, Excel, PPT, HWP, TXT 형식만 사용할 수 있습니다.")
    target_dir = UPLOAD_DIR / "notices"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (target_dir / stored_name).write_bytes(payload)
    content_type = file.content_type or "application/octet-stream"
    return {
        "url": f"/uploads/notices/{stored_name}",
        "filename": Path(file.filename).name,
        "content_type": content_type,
        "is_image": "1" if suffix in ALLOWED_IMAGE_SUFFIXES or content_type.startswith("image/") else "0",
    }


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
    data["floor"] = data.get("floor") or data.get("board_name")
    data["attachment_url"] = data.get("attachment_url") or data.get("image_url")
    if data["attachment_url"] and not data.get("attachment_filename"):
        data["attachment_filename"] = Path(str(data["attachment_url"])).name
    data["attachment_content_type"] = data.get("attachment_content_type") or ("image/*" if data.get("image_url") else None)
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


def location_option_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def specific_location_option_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def normalize_specific_location_payload(payload: NoticeSpecificLocationRequest) -> dict[str, Any]:
    return {
        "name": normalize_text(payload.name, "특정위치", 120, required=True),
        "sort_order": payload.sort_order,
    }


def build_location_tree(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    tree: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        building = row["building"]
        line = row["line"]
        floor = row["floor"]
        tree.setdefault(building, {}).setdefault(line, [])
        if floor not in tree[building][line]:
            tree[building][line].append(floor)
    return tree


def normalize_location_payload(payload: NoticeLocationRequest) -> dict[str, Any]:
    return {
        "building": normalize_text(payload.building, "동", 80, required=True),
        "line": normalize_text(payload.line, "라인", 80, required=True),
        "floor": normalize_text(payload.floor, "층", 80, required=True),
        "sort_order": payload.sort_order,
    }


def normalize_notice_location_target(raw: Any) -> dict[str, str | None]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="선택한 위치 정보를 다시 확인해 주세요.")
    location = normalize_text(raw.get("location") or raw.get("building"), "동", 120, required=True)
    line = normalize_text(raw.get("line"), "라인", 80, required=True)
    floor = normalize_text(raw.get("floor") or raw.get("board_name"), "층", 80)
    return {"location": location, "line": line, "floor": floor}


def parse_notice_location_targets(location_targets_json: str | None) -> list[dict[str, str | None]]:
    text = str(location_targets_json or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="선택한 위치 정보 형식을 읽지 못했습니다.")
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=400, detail="선택한 위치 정보가 비어 있습니다.")
    deduped: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in payload:
        normalized = normalize_notice_location_target(item)
        key = (
            normalized["location"] or "",
            normalized["line"] or "",
            normalized["floor"] or "",
        )
        if key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def split_spec_tokens(spec: str | None) -> list[str]:
    raw = str(spec or "").replace("\r", "\n")
    tokens = [token.strip() for chunk in raw.split("\n") for token in chunk.split(",")]
    return [token for token in tokens if token]


def normalize_building_label(token: str) -> str:
    text = token.strip()
    if re.fullmatch(r"\d+", text):
        return f"{text}동"
    return text


def normalize_line_label(token: str) -> str:
    text = token.strip()
    if not text:
        return text
    if "라인" in text:
        return text
    if re.fullmatch(r"[\d\s\-~]+", text):
        return f"{text}라인"
    return text


def normalize_floor_label(token: str) -> str:
    text = token.strip()
    if not text:
        return text
    upper = text.upper().replace(" ", "")
    if re.fullmatch(r"B\d+", upper):
        return upper
    if re.fullmatch(r"\d+", text):
        return f"{int(text)}층"
    if re.fullmatch(r"\d+층", text):
        return f"{int(text[:-1])}층"
    return text


def expand_buildings(spec: str) -> list[str]:
    result: list[str] = []
    for token in split_spec_tokens(spec):
        match = re.fullmatch(r"(\d+)\s*(동)?\s*[-~]\s*(\d+)\s*(동)?", token)
        if match:
            start = int(match.group(1))
            end = int(match.group(3))
            step = 1 if start <= end else -1
            width = max(len(match.group(1)), len(match.group(3)))
            for value in range(start, end + step, step):
                result.append(f"{value:0{width}d}동")
            continue
        result.append(normalize_building_label(token))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in result:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def expand_lines(spec: str) -> list[str]:
    result = [normalize_line_label(token) for token in split_spec_tokens(spec)]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in result:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def expand_floors(spec: str | None) -> list[str]:
    result: list[str] = []
    for token in split_spec_tokens(spec):
        compact = token.strip().replace(" ", "")
        basement_match = re.fullmatch(r"B(\d+)\s*[-~]\s*B(\d+)", compact, flags=re.IGNORECASE)
        if basement_match:
            start = int(basement_match.group(1))
            end = int(basement_match.group(2))
            step = 1 if start <= end else -1
            for value in range(start, end + step, step):
                result.append(f"B{value}")
            continue
        floor_range_match = re.fullmatch(r"(\d+)(층)?\s*[-~]\s*(\d+)(층)?", compact)
        if floor_range_match:
            start = int(floor_range_match.group(1))
            end = int(floor_range_match.group(3))
            step = 1 if start <= end else -1
            for value in range(start, end + step, step):
                result.append(f"{value}층")
            continue
        result.append(normalize_floor_label(token))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in result:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def generate_location_rows(payload: NoticeLocationGenerateRequest) -> list[dict[str, Any]]:
    buildings = expand_buildings(normalize_text(payload.buildings, "동 범위", 2000, required=True) or "")
    lines = expand_lines(normalize_text(payload.lines, "라인 목록", 2000, required=True) or "")
    floors = expand_floors(normalize_text(payload.floors, "층 범위", 4000, required=True))
    excluded = set(expand_floors(payload.excluded_floors))
    filtered_floors = [floor for floor in floors if floor not in excluded]
    if not buildings:
        raise HTTPException(status_code=400, detail="동 범위를 다시 확인해 주세요.")
    if not lines:
        raise HTTPException(status_code=400, detail="라인 목록을 다시 확인해 주세요.")
    if not filtered_floors:
        raise HTTPException(status_code=400, detail="생성할 층이 없습니다. 제외층을 다시 확인해 주세요.")

    rows: list[dict[str, Any]] = []
    sort_order = payload.sort_order_start
    for building in buildings:
        for line in lines:
            for floor in filtered_floors:
                rows.append(
                    {
                        "building": building,
                        "line": line,
                        "floor": floor,
                        "sort_order": sort_order,
                    }
                )
                sort_order += 1
    return rows


@router.on_event("startup")
def startup_notice_db() -> None:
    init_notice_db()


@router.get("/meta")
def notice_meta():
    return {"categories": NOTICE_CATEGORIES, "statuses": NOTICE_STATUSES}


@router.get("/specific-locations")
def list_notice_specific_locations():
    init_notice_db()
    with connect() as con:
        rows = con.execute(
            """
            SELECT *
            FROM notice_specific_location_options
            ORDER BY sort_order, name, id
            """
        ).fetchall()
    return {"items": [specific_location_option_dict(row) for row in rows]}


@router.post("/specific-locations")
def create_notice_specific_location(payload: NoticeSpecificLocationRequest):
    init_notice_db()
    values = normalize_specific_location_payload(payload)
    with connect() as con:
        try:
            cur = con.execute(
                """
                INSERT INTO notice_specific_location_options(name, sort_order)
                VALUES (?, ?)
                """,
                (values["name"], values["sort_order"]),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="이미 등록된 특정위치입니다.")
        row = con.execute("SELECT * FROM notice_specific_location_options WHERE id = ?", (cur.lastrowid,)).fetchone()
        con.commit()
    return specific_location_option_dict(row)


@router.delete("/specific-locations/{option_id}")
def delete_notice_specific_location(option_id: int):
    init_notice_db()
    with connect() as con:
        existing = con.execute("SELECT * FROM notice_specific_location_options WHERE id = ?", (option_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="특정위치 옵션을 찾을 수 없습니다.")
        con.execute("DELETE FROM notice_specific_location_options WHERE id = ?", (option_id,))
        con.commit()
    return {"deleted": True, "id": option_id}


@router.get("/locations")
def list_notice_locations():
    init_notice_db()
    with connect() as con:
        rows = con.execute(
            """
            SELECT *
            FROM notice_location_options
            ORDER BY sort_order, building, line, floor, id
            """
        ).fetchall()
    items = [location_option_dict(row) for row in rows]
    return {"items": items, "tree": build_location_tree(items)}


@router.post("/locations")
def create_notice_location(payload: NoticeLocationRequest):
    init_notice_db()
    values = normalize_location_payload(payload)
    with connect() as con:
        try:
            cur = con.execute(
                """
                INSERT INTO notice_location_options(building, line, floor, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (values["building"], values["line"], values["floor"], values["sort_order"]),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="이미 등록된 동/라인/층입니다.")
        row = con.execute("SELECT * FROM notice_location_options WHERE id = ?", (cur.lastrowid,)).fetchone()
        con.commit()
    return location_option_dict(row)


@router.post("/locations/generate")
def generate_notice_locations(payload: NoticeLocationGenerateRequest):
    init_notice_db()
    rows = generate_location_rows(payload)
    if payload.dry_run:
        return {
            "items": rows[:120],
            "preview_count": len(rows),
            "truncated": len(rows) > 120,
        }

    inserted = 0
    skipped = 0
    with connect() as con:
        for row in rows:
            try:
                con.execute(
                    """
                    INSERT INTO notice_location_options(building, line, floor, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row["building"], row["line"], row["floor"], row["sort_order"]),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        con.commit()
    return {"inserted": inserted, "skipped": skipped, "requested": len(rows)}


@router.patch("/locations/{location_id}")
def update_notice_location(location_id: int, payload: NoticeLocationRequest):
    init_notice_db()
    values = normalize_location_payload(payload)
    with connect() as con:
        existing = con.execute("SELECT * FROM notice_location_options WHERE id = ?", (location_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="위치 옵션을 찾을 수 없습니다.")
        try:
            con.execute(
                """
                UPDATE notice_location_options
                SET building = ?, line = ?, floor = ?, sort_order = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (values["building"], values["line"], values["floor"], values["sort_order"], location_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="이미 등록된 동/라인/층입니다.")
        row = con.execute("SELECT * FROM notice_location_options WHERE id = ?", (location_id,)).fetchone()
        con.commit()
    return location_option_dict(row)


@router.delete("/locations/{location_id}")
def delete_notice_location(location_id: int):
    init_notice_db()
    with connect() as con:
        existing = con.execute("SELECT * FROM notice_location_options WHERE id = ?", (location_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="위치 옵션을 찾을 수 없습니다.")
        con.execute("DELETE FROM notice_location_options WHERE id = ?", (location_id,))
        con.commit()
    return {"deleted": True, "id": location_id}


@router.delete("/locations/building/{building}")
def delete_notice_locations_by_building(building: str):
    target = normalize_text(building, "동", 80, required=True)
    with connect() as con:
        existing = con.execute(
            "SELECT COUNT(*) AS count FROM notice_location_options WHERE building = ?",
            (target,),
        ).fetchone()
        if not existing or int(existing["count"]) == 0:
            raise HTTPException(status_code=404, detail="삭제할 동 데이터를 찾을 수 없습니다.")
        con.execute("DELETE FROM notice_location_options WHERE building = ?", (target,))
        con.commit()
    return {"deleted": True, "building": target}


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
              OR COALESCE(line, '') LIKE ?
              OR COALESCE(floor, '') LIKE ?
              OR COALESCE(specific_location, '') LIKE ?
              OR COALESCE(board_name, '') LIKE ?
              OR COALESCE(attachment_filename, '') LIKE ?
              OR COALESCE(advertiser, '') LIKE ?
              OR COALESCE(contact, '') LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like, like, like, like, like])
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
    line: str | None = Form(None),
    floor: str | None = Form(None),
    specific_location: str | None = Form(None),
    board_name: str | None = Form(None),
    start_date: str = Form(...),
    end_date: str = Form(...),
    removal_due_date: str | None = Form(None),
    advertiser: str | None = Form(None),
    contact: str | None = Form(None),
    status: str | None = Form("posted"),
    note: str | None = Form(None),
    location_targets_json: str | None = Form(None),
    image: UploadFile | None = File(None),
    attachment: UploadFile | None = File(None),
):
    init_notice_db()
    normalized_category = normalize_category(category)
    normalized_title = normalize_text(title, "제목", 120, required=True)
    location_targets = parse_notice_location_targets(location_targets_json)
    normalized_location = normalize_text(location, "동", 120, required=not location_targets)
    normalized_line = normalize_text(line, "라인", 80, required=not location_targets)
    normalized_floor = normalize_text(floor or board_name, "층", 80)
    normalized_start = normalize_date_value(start_date, "게시 시작일", required=True)
    normalized_end = normalize_date_value(end_date, "게시 종료일", required=True)
    normalized_removal_due = normalize_date_value(removal_due_date, "철거 예정일")
    validate_period(normalized_start, normalized_end, normalized_removal_due)
    attachment_file = await save_notice_attachment(attachment or image)
    attachment_url = attachment_file["url"] if attachment_file else None
    image_url = attachment_url if attachment_file and attachment_file["is_image"] == "1" else None
    targets = location_targets or [{"location": normalized_location, "line": normalized_line, "floor": normalized_floor}]
    created_rows: list[sqlite3.Row] = []
    with connect() as con:
        normalized_description = normalize_text(description, "내용", 1000)
        normalized_advertiser = normalize_text(advertiser, "게시자", 80)
        normalized_contact = normalize_text(contact, "연락처", 80)
        normalized_specific_location = normalize_text(specific_location, "특정위치", 120)
        normalized_status = normalize_status(status)
        normalized_note = normalize_text(note, "메모", 500)
        for target in targets:
            cur = con.execute(
                """
                INSERT INTO board_posts
                (category, title, description, location, line, floor, specific_location, board_name, start_date, end_date, removal_due_date,
                 advertiser, contact, status, note, image_url, attachment_url, attachment_filename, attachment_content_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_category,
                    normalized_title,
                    normalized_description,
                    target["location"],
                    target["line"],
                    target["floor"],
                    normalized_specific_location,
                    target["floor"],
                    normalized_start,
                    normalized_end,
                    normalized_removal_due,
                    normalized_advertiser,
                    normalized_contact,
                    normalized_status,
                    normalized_note,
                    image_url,
                    attachment_url,
                    attachment_file["filename"] if attachment_file else None,
                    attachment_file["content_type"] if attachment_file else None,
                ),
            )
            created_rows.append(con.execute("SELECT * FROM board_posts WHERE id = ?", (cur.lastrowid,)).fetchone())
        con.commit()
    notices = [notice_dict(row) for row in created_rows]
    if len(notices) == 1:
        return notices[0]
    return {"created_count": len(notices), "items": notices}


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
            "location": normalize_text(values.get("location"), "동", 120, required=True),
            "line": normalize_text(values.get("line"), "라인", 80, required=True),
            "floor": normalize_text(values.get("floor") or values.get("board_name"), "층", 80),
            "specific_location": normalize_text(values.get("specific_location"), "특정위치", 120),
            "board_name": normalize_text(values.get("floor") or values.get("board_name"), "층", 80),
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
            SET category = ?, title = ?, description = ?, location = ?, line = ?, floor = ?, specific_location = ?, board_name = ?,
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
