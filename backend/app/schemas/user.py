import re
import uuid

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    login_name: str
    password: str


ALLOWED_EMAIL_DOMAINS = {"rwth-aachen.de"}


class RegisterRequest(BaseModel):
    username: str | None
    email: str
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if " " in v:
            raise ValueError("Username must not contain spaces")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Please enter a valid email address")
        domain = v.rsplit("@", 1)[-1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            raise ValueError("Registration is restricted to RWTH email addresses")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    username: str | None
    picture: str | None
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
