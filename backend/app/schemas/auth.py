import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=15)
    gender: Literal["Male", "Female", "Other"] | None = None
    date_of_birth: date | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v and not re.match(r"^\+?[6-9]\d{9}$", v.replace(" ", "")):
            raise ValueError("Invalid Indian phone number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return RegisterRequest.validate_password(v)


class VerifyEmailRequest(BaseModel):
    token: str


class MFASetupResponse(BaseModel):
    secret: str
    qr_uri: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    phone: str | None
    is_verified: bool
    mfa_enabled: bool
    is_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str


class BrokerConnectRequest(BaseModel):
    broker: Literal["dhan", "groww", "fyers", "upstox"]
    api_key: str | None = None
    api_secret: str | None = None
    access_token: str | None = None
    client_id: str | None = None


class BrokerConnectionResponse(BaseModel):
    id: UUID
    broker: str
    is_active: bool
    health_status: str
    client_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
