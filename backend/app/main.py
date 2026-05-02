import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import OPENAI_MODEL_OPTIONS, settings
from .kakao_parser import parse_diagnostics, parse_kakao_chat, filter_by_date
from .notice_board import UPLOAD_DIR, router as notice_board_router
from .openai_usage import get_openai_usage_snapshot
from .report_generator import generate_report, generate_reviewed_report
from .review_builder import build_image_review_session, build_review_session, decode_uploaded_text

app = FastAPI(title="Facility Report System", version="0.1.0")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.include_router(notice_board_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_origin_regex=settings.allowed_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportRequest(BaseModel):
    text: str
    start_date: str | None = None
    end_date: str | None = None

class ReviewedReportRequest(BaseModel):
    messages: list[dict]
    images: list[dict] = []
    matches: list[dict] = []
    start_date: str | None = None
    end_date: str | None = None
    ai_model: str | None = None


async def _upload_image_rows(images: list[UploadFile] | None) -> list[dict]:
    image_rows = []
    for image in images or []:
        raw_image = await image.read()
        image_rows.append(
            {
                "filename": image.filename,
                "content_type": image.content_type,
                "size": len(raw_image),
            }
        )
    return image_rows

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/openai-usage")
def openai_usage(days: int = 7):
    days = max(1, min(days, 31))
    return get_openai_usage_snapshot(days)

@app.get("/api/openai-models")
def openai_models():
    return {"default": settings.openai_model, "models": OPENAI_MODEL_OPTIONS}

@app.post("/api/parse")
def parse_text(payload: ReportRequest):
    messages = parse_kakao_chat(payload.text)
    filtered = filter_by_date(messages, payload.start_date, payload.end_date)
    return {"total": len(messages), "filtered": len(filtered), "messages": filtered[:200]}

@app.post("/api/report")
def report(payload: ReportRequest):
    messages = parse_kakao_chat(payload.text)
    filtered = filter_by_date(messages, payload.start_date, payload.end_date)
    return {"total": len(messages), "filtered": len(filtered), "report": generate_report(filtered, payload.start_date, payload.end_date)}

@app.post("/api/report-file")
async def report_file(file: UploadFile = File(...), start_date: str | None = Form(None), end_date: str | None = Form(None)):
    raw = await file.read()
    text = decode_uploaded_text(raw)
    messages = parse_kakao_chat(text)
    filtered = filter_by_date(messages, start_date, end_date)
    return {"filename": file.filename, "total": len(messages), "filtered": len(filtered), "report": generate_report(filtered, start_date, end_date)}

@app.post("/api/review-file")
async def review_file(
    chat_file: UploadFile | None = File(None),
    images: list[UploadFile] | None = File(None),
    text: str | None = Form(None),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
    image_metadata: str | None = Form(None),
    use_ai: bool = Form(False),
    ai_model: str | None = Form(None),
):
    if chat_file:
        raw = await chat_file.read()
        chat_text = decode_uploaded_text(raw)
        filename = chat_file.filename
    else:
        chat_text = text or ""
        filename = None

    if not chat_text.strip():
        raise HTTPException(status_code=400, detail="카카오톡 txt 파일 또는 대화 내용을 입력하세요.")

    image_rows = await _upload_image_rows(images)

    messages = parse_kakao_chat(chat_text)
    filtered = filter_by_date(messages, start_date, end_date)
    review = build_review_session(filtered, image_rows, image_metadata, use_ai=use_ai, ai_model=ai_model)
    return {
        "filename": filename,
        "total": len(messages),
        "filtered": len(filtered),
        "parse_diagnostics": parse_diagnostics(chat_text) if not messages else None,
        **review,
    }

@app.post("/api/review-images")
async def review_images(
    messages_json: str = Form(...),
    images: list[UploadFile] | None = File(None),
    image_metadata: str | None = Form(None),
):
    try:
        messages = json.loads(messages_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="대화 상태 JSON을 읽을 수 없습니다.")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="먼저 카톡 대화를 분석하세요.")

    image_rows = await _upload_image_rows(images)
    review = build_image_review_session(messages, image_rows, image_metadata)
    return {
        "messages": messages,
        **review,
    }

@app.post("/api/report-reviewed")
def report_reviewed(payload: ReviewedReportRequest):
    return {
        "report": generate_reviewed_report(
            payload.messages,
            payload.images,
            payload.matches,
            payload.start_date,
            payload.end_date,
            payload.ai_model,
        )
    }

