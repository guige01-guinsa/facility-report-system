from pydantic_settings import BaseSettings

OPENAI_MODEL_OPTIONS = [
    {
        "id": "gpt-5-nano",
        "label": "저렴/빠름",
        "description": "대화 분류와 간단한 요약에 권장",
    },
    {
        "id": "gpt-5-mini",
        "label": "균형",
        "description": "비용은 늘지만 애매한 문장 판단 보강",
    },
    {
        "id": "gpt-5.2",
        "label": "정확도 우선",
        "description": "가장 무겁고 비싼 선택지",
    },
]
OPENAI_MODEL_IDS = {row["id"] for row in OPENAI_MODEL_OPTIONS}


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_admin_key: str = ""
    openai_model: str = "gpt-5-nano"
    allowed_origins: str = "http://localhost:3000"
    allowed_origin_regex: str = ""

    class Config:
        env_file = ".env"

settings = Settings()


def resolve_openai_model(model: str | None = None) -> str:
    candidate = (model or settings.openai_model or "gpt-5-nano").strip()
    if candidate in OPENAI_MODEL_IDS:
        return candidate
    fallback = (settings.openai_model or "gpt-5-nano").strip()
    return fallback if fallback in OPENAI_MODEL_IDS else "gpt-5-nano"
