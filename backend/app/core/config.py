"""
Application Settings & Configuration.
"""

import os
from typing import List, Union, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "Academia Shield API"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    
    # PostgreSQL / Database
    POSTGRES_USER: str = Field(default="postgres")
    POSTGRES_PASSWORD: str = Field(default="postgres")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="academia_shield")
    DATABASE_URL: str = Field(default="")

    # JWT Security
    JWT_SECRET: str = Field(default="super_secret_jwt_key_change_in_production_min32chars")
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "academia-shield"
    JWT_AUDIENCE: str = "academia-shield-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # Server & CORS
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    SHOW_DOCS: bool = True
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "https://academia-shield.vercel.app"
    ]

    # Production Domain & HTTPS
    PRODUCTION_DOMAIN: str = "api.academiashield.com"
    PUBLIC_BASE_URL: str = "https://api.academiashield.com"
    REQUIRE_HTTPS: bool = False  # Set to True in production
    
    # Release Management & Signing
    CURRENT_AGENT_VERSION: str = "2.3.0"
    RELEASE_SIGNING_PRIVATE_KEY: Optional[str] = None  # Outside repo / injected in prod env
    WINDOWS_MIN_OS: str = "Windows 10 Build 19041"
    MACOS_MIN_OS: str = "macOS 12.0 Monterey"

    model_config = SettingsConfigDict(
        env_file=[
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
            ".env"
        ],
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        return v

settings = Settings()
