from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./expenses.db"
    session_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # or "strict" for production
    session_cookie_name: str = "expenses_session"
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
