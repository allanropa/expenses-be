from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.domain.money import normalize_currency


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str


class SessionResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class SettingsResponse(BaseModel):
    reporting_currency: str
    timezone: str


class SettingsUpdateRequest(BaseModel):
    reporting_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("reporting_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value) if value else value


class HealthResponse(BaseModel):
    status: str
    database: str
