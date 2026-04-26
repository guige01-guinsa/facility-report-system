from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    allowed_origins: str = "http://localhost:3000"
    allowed_origin_regex: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
