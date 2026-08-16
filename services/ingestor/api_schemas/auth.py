from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


ROLE_PATTERN = r"^(user|manager|admin)$"


class UserCreate(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "alice",
                    "email": "alice@example.com",
                    "password": "securePass1!",
                    "role": "user",
                    "tenant_id": None,
                }
            ]
        }
    }

    username: str = Field(
        min_length=3,
        max_length=64,
        description="Unique username used for authentication.",
        examples=["alice"],
    )
    email: EmailStr = Field(
        description="User email address. Must be unique.",
        examples=["alice@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Plaintext password. Minimum 8 characters.",
        examples=["securePass1!"],
    )
    role: str = Field(
        "user",
        pattern=ROLE_PATTERN,
        description="Ignored on public registration; an administrator assigns roles.",
        examples=["user"],
    )
    tenant_id: int | None = Field(
        None,
        description="Ignored on public registration; an administrator assigns tenants.",
        examples=[None],
    )


class RoleAssignment(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "admin",
                }
            ]
        }
    }

    role: str = Field(
        pattern=ROLE_PATTERN,
        description="Role to assign. Must match one of the allowed role names.",
        examples=["admin"],
    )


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Primary key of the user.", examples=[1])
    username: str = Field(
        description="Unique username used for authentication.",
        examples=["alice"],
    )
    email: str = Field(
        description="User email address.",
        examples=["alice@example.com"],
    )
    role: str | None = Field(
        None,
        description="Effective role in the current domain.",
        examples=["user"],
    )
    tenant_id: int | None = Field(
        None,
        description="Tenant ID associated with the user.",
        examples=[1],
    )
    is_active: bool = Field(
        description="Whether the user account is active.",
        examples=[True],
    )
    created_at: datetime = Field(
        description="ISO 8601 timestamp of when the user was created.",
        examples=["2024-01-15T10:30:00Z"],
    )


class UserUpdate(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "alice_new@example.com",
                    "is_active": True,
                }
            ]
        }
    }

    email: EmailStr | None = Field(
        None,
        description="New email address. Must be unique if provided.",
        examples=["alice_new@example.com"],
    )
    is_active: bool | None = Field(
        None,
        description="Whether the user account is active.",
        examples=[True],
    )


class TokenResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "eyJhbGciOi...",
                    "refresh_token": "eyJhbGciOi...",
                    "token_type": "bearer",
                }
            ]
        }
    }

    access_token: str = Field(
        description="Short-lived JWT access token.",
        examples=["eyJhbGciOi..."],
    )
    refresh_token: str = Field(
        description="Long-lived refresh token used to obtain new access tokens.",
        examples=["eyJhbGciOi..."],
    )
    token_type: str = Field(
        "bearer",
        description="Token type. Fixed to bearer.",
        examples=["bearer"],
    )


class RefreshRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "refresh_token": "eyJhbGciOi...",
                }
            ]
        }
    }

    refresh_token: str = Field(
        description="Valid refresh token issued during login.",
        examples=["eyJhbGciOi..."],
    )


class LogoutRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "refresh_token": "eyJhbGciOi...",
                }
            ]
        }
    }

    refresh_token: str | None = Field(
        None,
        description="Refresh token to revoke. If omitted, only the session cookie is invalidated.",
        examples=["eyJhbGciOi..."],
    )


class UserListResponse(BaseModel):
    model_config = {"from_attributes": False}

    users: list[UserResponse] = Field(
        description="List of user summaries.",
    )
    total: int = Field(
        description="Total number of users matching the query.",
        examples=[42],
    )


__all__ = [
    "ROLE_PATTERN",
    "UserCreate",
    "RoleAssignment",
    "UserResponse",
    "UserUpdate",
    "TokenResponse",
    "RefreshRequest",
    "LogoutRequest",
    "UserListResponse",
]
