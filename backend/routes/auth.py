"""
routes/auth.py
============================================================
FastAPI router — Authentication endpoints.

Endpoints
---------
POST /auth/register   — create a new account
POST /auth/login      — exchange credentials for tokens
POST /auth/refresh    — rotate access token via refresh cookie
POST /auth/logout     — revoke both tokens + clear cookie
============================================================
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    logout_token,
    verify_password,
)
from database import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    is_token_blocked,
)

# ── Router ────────────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])

# ── Cookie settings ───────────────────────────────────────────
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


# ══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ══════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ══════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ══════════════════════════════════════════════════════════════

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")


def _validate_email(email: str) -> None:
    """Raise 422 if *email* doesn't look like a valid address."""
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email format.",
        )


def _validate_password(password: str) -> None:
    """
    Raise 422 if *password* does not meet complexity requirements:
      - At least 8 characters
      - Contains at least one letter
      - Contains at least one digit
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long.",
        )
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one letter.",
        )
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one number.",
        )


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── POST /auth/register ───────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """
    Create a new user account.

    - Validates email format and password complexity.
    - Returns **409** if the e-mail is already registered.
    - Stores a bcrypt hash (cost 12) — never the plain password.
    """
    _validate_email(body.email)
    _validate_password(body.password)

    # Conflict check
    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    pw_hash = hash_password(body.password)
    user_id = create_user(
        email=body.email,
        password_hash=pw_hash,
        full_name=body.full_name,
    )

    return {"message": "registered", "user_id": user_id}


# ── POST /auth/login ──────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response):
    """
    Exchange email + password for an access token.

    - Access token is returned in the JSON body.
    - Refresh token is set as an **httpOnly** cookie (7 days, SameSite=lax).
    """
    # Look up user — generic 401 to avoid user-enumeration
    user = get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"],
    )
    refresh_token = create_refresh_token(user_id=user["id"])

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,   # set to True behind HTTPS in production
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserOut(
            id=user["id"],
            email=user["email"],
            full_name=user.get("full_name"),
            role=user["role"],
        ),
    )


# ── POST /auth/refresh ────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME)):
    """
    Issue a new access token using the refresh token stored in the
    httpOnly cookie.

    - Returns **401** if the cookie is missing, expired, wrong type,
      or has been revoked.
    """
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # decode_token already raises 401 on invalid / expired tokens
    payload = decode_token(refresh_token)

    # Ensure this is actually a refresh token, not an access token
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti: str | None = payload.get("jti")
    user_id: str | None = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject revoked refresh tokens
    if is_token_blocked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user to embed up-to-date email + role in the new token
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access_token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"],
    )

    return TokenResponse(access_token=new_access_token, token_type="bearer")


# ── POST /auth/logout ─────────────────────────────────────────
@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Revoke the current access token and the refresh token cookie.

    - Adds both JTIs to the blocklist.
    - Clears the refresh token cookie.
    - Requires a valid ``Authorization: Bearer <access_token>`` header.
    """
    # ── Blocklist the access token ────────────────────────────
    raw_access = request.headers.get("Authorization", "")
    if raw_access.lower().startswith("bearer "):
        access_token_str = raw_access.split(" ", 1)[1]
        try:
            logout_token(access_token_str)
        except HTTPException:
            pass  # already invalid — still proceed with logout

    # ── Blocklist the refresh token (if present) ──────────────
    refresh_token_str: str | None = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token_str:
        try:
            logout_token(refresh_token_str)
        except HTTPException:
            pass  # expired / already blocked — cookie will still be cleared

    # ── Clear the cookie ──────────────────────────────────────
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )

    return {"message": "logged out"}
