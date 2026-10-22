from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    app_env: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./expenses.db"
    session_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_name: str = "expenses_session"
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = ""

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
