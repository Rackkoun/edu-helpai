# file src/backend/config.py
from pathlib import Path
from functools import lru_cache
from pydantic import field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

# project paths
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"

# ensure directories exists
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """
    App configuration

    Environment variables override these defaults
    """

    # app
    APP_NAME: str = "Edu-HelpAI"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # database
    DATABASE_URL: str = f"sqlite:///{DATA_DIR}/edu_helpai.db"
    DB_ECHO: bool = False

    # ollama
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral:7b"
    OLLAMA_TIMEOUT: int = 120

    # embeddings
    EMBEDDING_MODEL: str = "nomic-embed-text"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # RAG settings
    RAG_TOP_K: int = 5  # number of chunk to retrieve
    MAX_TOKENS: int = 4096

    # mlflow
    MLFLOW_TRACKING_URI: str = f"sqlite:///{DATA_DIR}/mlflow.db"
    MLFLOW_EXPERIMENT_NAME: str = "edu-helpai-chat"

    # security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # paths
    UPLOAD_DIR: Path = UPLOADS_DIR
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50Mb

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_validator(cls, v: str) -> str:
        """The secret key must not be weak"""
        weak_sk = {"dev-secret-key", "secret", "changeme", "password", ""}
        if v in weak_sk or len(v) < 32:
            raise ValueError(
                "SECRET_KEY is too weak or is a known default."
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",  # load from .env file
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # allow extra env vars without error
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    """
    return Settings()


settings = get_settings()
