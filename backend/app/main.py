from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .config import settings
from .kakao_parser import parse_kakao_chat, filter_by_date
from .report_generator import generate_report

app = FastAPI(title="Facility Report System", version="0.1.0")

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

@app.get("/health")
def health():
    return {"status": "ok"}

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
    text = raw.decode("utf-8", errors="ignore")
    messages = parse_kakao_chat(text)
    filtered = filter_by_date(messages, start_date, end_date)
    return {"filename": file.filename, "total": len(messages), "filtered": len(filtered), "report": generate_report(filtered, start_date, end_date)}
